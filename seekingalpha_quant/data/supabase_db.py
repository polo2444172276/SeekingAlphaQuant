"""Minimal client for the shared Supabase project (REST Data API + Storage).

Auth: in Claude Code cloud sessions on the SeekingAlphaQuant environment the
network proxy injects the project's secret key as the `apikey` header, so the
code sends a placeholder. Elsewhere (e.g. your laptop) set SUPABASE_SECRET_KEY.
The project URL comes from SUPABASE_URL.
"""

import os
import time

import requests

URL = os.environ.get("SUPABASE_URL", "https://rvqvhoypbqiyrnfatqna.supabase.co").rstrip("/")
KEY = os.environ.get("SUPABASE_SECRET_KEY", "proxy-injected")
BUCKET = "market-data"

_session = requests.Session()
_session.headers.update({"apikey": KEY})


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


def download(path):
    return _req("GET", f"/storage/v1/object/{BUCKET}/{path}").content


def security_ids(market="US"):
    """{symbol: id} for one market."""
    return {r["symbol"]: r["id"] for r in select("securities", {"market": f"eq.{market}", "select": "id,symbol"})}
