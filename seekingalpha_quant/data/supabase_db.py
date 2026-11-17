"""Minimal client for the shared Supabase project (REST Data API + Storage).

Auth: in Claude Code cloud sessions on the SeekingAlphaQuant environment the
network proxy injects the project's secret key as the `apikey` header, so the
code sends a placeholder. Elsewhere (e.g. your laptop) set SUPABASE_SECRET_KEY.
The project URL comes from SUPABASE_URL.

Audit trail: every request carries x-session-id / x-session-url / x-client /
x-change-note headers. A trigger in the database writes one row per write
statement into `data_change_log` (who, when, which table, how many rows, key
ranges). Say why you are writing with `change_note("...")`:

    with db.change_note("backfill SOXX history for webinar fact-check"):
        db.upsert("prices_daily", rows, on_conflict="security_id,date")
"""

import contextlib
import getpass
import json
import os
import socket
import subprocess
import sys
import time

import requests

URL = os.environ.get("SUPABASE_URL", "https://rvqvhoypbqiyrnfatqna.supabase.co").rstrip("/")
KEY = os.environ.get("SUPABASE_SECRET_KEY", "proxy-injected")
BUCKET = "market-data"

_session = requests.Session()
_session.headers.update({"apikey": KEY})


def _ascii(v):
    """JSON-escape to ASCII so non-ASCII text survives an HTTP header (decoded in SQL)."""
    return json.dumps(str(v), ensure_ascii=True)[1:-1]


def _identity():
    """(session_id, session_url) of whoever is running this code."""
    sid = os.environ.get("SA_SESSION_ID")
    if sid:
        return sid, os.environ.get("SA_SESSION_URL")
    remote = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
    if remote.startswith("cse_"):
        sid = "session_" + remote[4:]
        return sid, f"https://claude.ai/code/{sid}"
    if remote:
        return remote, None
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "unknown"
    return f"local:{user}@{socket.gethostname()}", None


def _client():
    script = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] not in ("", "-c", "-") else "interactive"
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        ref = subprocess.run(["git", "-C", here, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", here, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        if ref:
            script += f"@{ref}{'+dirty' if dirty else ''}"
    except Exception:  # noqa: BLE001
        pass
    return script


SESSION_ID, SESSION_URL = _identity()
_session.headers.update({"x-session-id": _ascii(SESSION_ID), "x-client": _ascii(_client())})
if SESSION_URL:
    _session.headers["x-session-url"] = _ascii(SESSION_URL)


@contextlib.contextmanager
def change_note(text):
    """Attach a reason to every write made inside the block (lands in data_change_log.note)."""
    prev = _session.headers.get("x-change-note")
    _session.headers["x-change-note"] = _ascii(text)
    try:
        yield
    finally:
        if prev is None:
            _session.headers.pop("x-change-note", None)
        else:
            _session.headers["x-change-note"] = prev


def log_change(table_name, operation, row_count, summary=None):
    """Write an audit row by hand (used for Storage uploads, which no DB trigger sees)."""
    h = _session.headers
    dec = lambda k: json.loads(f'"{h[k]}"') if k in h else None  # noqa: E731
    row = {"session_id": SESSION_ID, "session_url": SESSION_URL, "client": dec("x-client"),
           "note": dec("x-change-note"), "table_name": table_name, "operation": operation,
           "row_count": row_count, "summary": summary}
    try:
        _req("POST", "/rest/v1/data_change_log", json=[row], headers={"Prefer": "return=minimal"})
    except RuntimeError as e:  # table not created yet: don't break the upload
        print(f"warning: could not write data_change_log ({e})", file=sys.stderr)


def _req(method, path, retries=4, **kw):
    for attempt in range(retries):
        r = _session.request(method, f"{URL}{path}", timeout=120, **kw)
        if r.status_code < 500 and r.status_code != 429:
            break
        time.sleep(2 ** attempt)
    if r.status_code >= 300:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r


def select(table, params=None, page_size=1000):
    """All rows matching PostgREST query params (e.g. {'symbol': 'eq.AAPL'})."""
    params = dict(params or {})
    params.setdefault("select", "*")
    out, start = [], 0
    while True:
        r = _req("GET", f"/rest/v1/{table}", params=params,
                 headers={"Range-Unit": "items", "Range": f"{start}-{start + page_size - 1}"})
        rows = r.json()
        out.extend(rows)
        if len(rows) < page_size:
            return out
        start += page_size


def upsert(table, rows, on_conflict=None, batch=1000, returning=False):
    """Insert rows, merging on the given conflict columns. Returns rows if asked."""
    prefer = ["resolution=merge-duplicates", "return=representation" if returning else "return=minimal"]
    params = {"on_conflict": on_conflict} if on_conflict else None
    out = []
    for i in range(0, len(rows), batch):
        r = _req("POST", f"/rest/v1/{table}", params=params, json=rows[i:i + batch],
                 headers={"Prefer": ",".join(prefer)})
        if returning:
            out.extend(r.json())
    return out


def insert(table, rows, batch=1000):
    for i in range(0, len(rows), batch):
        _req("POST", f"/rest/v1/{table}", json=rows[i:i + batch], headers={"Prefer": "return=minimal"})


def delete(table, params):
    """Delete rows matching params; params must be non-empty."""
    if not params:
        raise ValueError("refusing to delete without a filter")
    _req("DELETE", f"/rest/v1/{table}", params=params)


def upload(path, data, content_type="application/octet-stream"):
    """Upload (overwrite) an object in the market-data bucket."""
    _req("POST", f"/storage/v1/object/{BUCKET}/{path}", data=data,
         headers={"Content-Type": content_type, "x-upsert": "true"})
    log_change(f"storage:{BUCKET}", "UPLOAD", 1, {"path": path, "bytes": len(data)})


def download(path):
    return _req("GET", f"/storage/v1/object/{BUCKET}/{path}").content


def security_ids(market="US"):
    """{symbol: id} for one market."""
    return {r["symbol"]: r["id"] for r in select("securities", {"market": f"eq.{market}", "select": "id,symbol"})}
