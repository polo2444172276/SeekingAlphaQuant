"""Build point-in-time top-100 S&P 500 earnings-call turns with CEO flags.

Sources:
  hf   - zcyeee/sp500-earnings-call-turns (MIT), calls 2005-10 .. 2025-05
  fool - Motley Fool transcript pages, calls after the HF cutoff
Output: {S}/out/turns/year=YYYY.parquet  (one row per speaker turn)
        {S}/out/calls.parquet             (one row per call)
usage: python build.py <workdir>
"""
import datetime as dt, glob, json, os, re, sys
from collections import defaultdict

import duckdb, pyarrow as pa, pyarrow.parquet as pq, requests

S = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ceo_detect as cd, fool_parse as fp, universe as uv

TOP = uv.topn(S, 100)
HF_END = "2025-05-16"


def rank_for(sym, date):
    k = uv.prev_quarter_key(date)
    return TOP.get(k, {}).get(sym), k


con = duckdb.connect()
con.sql("SET memory_limit='4GB'; SET threads=2")
hf = f"{S}/hf/data/*.parquet"

# symbols that were ever in a top-100 quarter
ever = set().union(*[set(v) for v in TOP.values()])
print("symbols ever top-100:", len(ever), flush=True)

calls_out, turns_by_year = [], defaultdict(list)
TURN_SCHEMA = pa.schema([("source", pa.string()), ("symbol", pa.string()), ("call_date", pa.string()), ("mcap_rank", pa.int32()),
                         ("turn", pa.int32()), ("speaker", pa.string()), ("role", pa.string()), ("section", pa.string()),
                         ("title", pa.string()), ("role_src", pa.string()), ("is_ceo", pa.bool_()), ("text", pa.string())])
os.makedirs(f"{S}/out/turns", exist_ok=True)
writers, n_turn_rows = {}, [0]


def flush(force=False):
    for y, rows in list(turns_by_year.items()):
        if rows and (force or len(rows) >= 20000):
            if y not in writers:
                writers[y] = pq.ParquetWriter(f"{S}/out/turns/year={y}.parquet", TURN_SCHEMA, compression="zstd")
            writers[y].write_table(pa.Table.from_pylist(rows, schema=TURN_SCHEMA))
            n_turn_rows[0] += len(rows)
            turns_by_year[y] = []
ceo_cache = {}  # symbol -> current CEO name (FMP)


def current_ceo(sym):
    if sym not in ceo_cache:
        try:
            ke = requests.get("https://financialmodelingprep.com/stable/key-executives", params={"symbol": sym}, timeout=30).json()
            ceo_cache[sym] = next((x["name"] for x in ke if re.search(r"Chief Executive|\bCEO\b", x.get("title") or "")), None) if isinstance(ke, list) else None
        except Exception:
            ceo_cache[sym] = None
    return ceo_cache[sym]


def emit(sym, calls):
    """calls: list of dicts with full turns, sorted by date (one symbol, all sources)."""
    cd.apply_current(calls, current_ceo(sym), None)
    cd.propagate(calls)
    for c in calls:
        rank, qk = rank_for(sym, c["date"])
        if rank is None:
            continue
        ceo_last = cd.last(c["ceo"]) if c["ceo"] else None
        calls_out.append(dict(source=c["source"], symbol=sym, call_date=c["date"][:10], call_time=c["date"][11:19] or None,
                              fiscal_year=c.get("fy"), fiscal_quarter=c.get("fq"), cik=c.get("cik"), company=c.get("company"),
                              mcap_rank=rank, rank_quarter=qk, ceo_name=c["ceo"], ceo_src=c["ceo_src"],
                              n_turns=len(c["turns"]), url=c.get("url")))
        y = c["date"][:4]
        for t in c["turns"]:
            if t.get("role") == "header":
                continue
            turns_by_year[y].append(dict(
                source=c["source"], symbol=sym, call_date=c["date"][:10], mcap_rank=rank, turn=t.get("i"),
                speaker=t.get("speaker"), role=t.get("role"), section=t.get("section"),
                title=t.get("title") or t.get("affiliation"), role_src=t.get("role_src"),
                is_ceo=bool(ceo_last and t.get("role") == "management" and cd.last(t.get("speaker")) == ceo_last),
                text=t.get("text") or ""))


# ---------- Fool pages (parsed once, grouped by ticker) ----------
fool = defaultdict(list)
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
for f in sorted(glob.glob(f"{S}/fool/pages/*__*.html")):
    parts = os.path.basename(f)[:-5].split("__")
    given = parts[0] if len(parts) == 3 else None
    slug, ymd = parts[-2], parts[-1]
    m = re.search(r"-(?:([a-z.]{1,6})-)?(q[1-4]|fy|h[12])-(\d{4})-", slug)
    if not m or not (given or m.group(1)):
        continue
    sym = given or m.group(1).upper().replace(".", "-")
    if any(c["url"].endswith("/" + slug + "/") for c in fool[sym]):
        continue
    r = fp.parse(open(f, errors="ignore").read())
    if len(r["turns"]) < 5:
        continue
    # call date from the page's Date block; pages without one are skipped (URL date is the publication date,
    # which for back-filled transcripts can be months after the call)
    md = re.search(r"([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),\s+(\d{4})", r["date_text"] or "")
    if md and md.group(1).lower()[:3] in MON:
        d = f"{md.group(3)}-{MON[md.group(1).lower()[:3]]:02d}-{int(md.group(2)):02d}"
    elif ymd < "2025-09-01":
        d = ymd  # early template without a Date block; published the same day as the call
    else:
        continue
    if d < HF_END:
        continue
    q = m.group(2)
    fool[sym].append(dict(source="fool", date=d, fy=int(m.group(3)), fq=int(q[1]) if q[0] == "q" else None,
                          turns=r["turns"], url="https://www.fool.com/earnings/call-transcripts/" + ymd.replace("-", "/") + "/" + slug + "/"))

def dedupe(calls):
    """one call per (date) and per (fiscal year, quarter); HF rows sort first and win."""
    seen_d, seen_q, out = set(), set(), []
    for c in calls:
        q = (c.get("fy"), c.get("fq")) if c.get("fq") else None
        if c["date"][:10] in seen_d or (q and q in seen_q):
            continue
        seen_d.add(c["date"][:10])
        if q:
            seen_q.add(q)
        out.append(c)
    return out


# ---------- HF dataset, per symbol ----------
syms = sorted(ever)
for n, sym in enumerate(syms):
    rows = con.execute(f"""select date, fiscal_year, fiscal_quarter, cik, ticker_company_name, content, turns, company_check, flags
                           from read_parquet('{hf}') where symbol = ? order by date""", [sym]).fetchall()
    calls = []
    for date, fy, fq, cik, name, content, turns, check, flags in rows:
        if check == "not_this_company" or "tiny_content" in (flags or []) or "no_speaker_labels" in (flags or []):
            continue
        prev = next((c["ceo"] for c in reversed(calls) if c["ceo"]), None)
        ceo, src = cd.detect(turns, (content or "")[:4000], prev, name or "")
        calls.append(dict(source="hf", date=date, fy=fy, fq=fq, cik=cik, company=name, turns=turns, ceo=ceo, ceo_src=src,
                          mgmt={cd.last(t["speaker"]): t["speaker"] for t in turns if t["role"] == "management" and t["speaker"]}))
    company = calls[-1]["company"] if calls else None
    for c in sorted(fool.pop(sym, []), key=lambda c: c["date"]):
        prev = next((x["ceo"] for x in reversed(calls) if x["ceo"]), None)
        ceo, src = cd.detect(c["turns"], "", prev, company or "")
        c.update(ceo=ceo, ceo_src=src, company=company,
                 mgmt={cd.last(t["speaker"]): t["speaker"] for t in c["turns"] if t["role"] == "management"})
        calls.append(c)
    calls.sort(key=lambda c: (c["date"], c["source"] != "hf"))
    calls = dedupe(calls)
    emit(sym, calls)
    flush()
    if n % 25 == 0:
        print(n, sym, len(calls_out), flush=True)

# Fool-only tickers (joined the S&P 500 / top 100 after the HF cutoff)
for sym, L in fool.items():
    L = dedupe(sorted(L, key=lambda c: c["date"]))
    calls = []
    for c in L:
        prev = next((x["ceo"] for x in reversed(calls) if x["ceo"]), None)
        ceo, src = cd.detect(c["turns"], "", prev, "")
        c.update(ceo=ceo, ceo_src=src, mgmt={cd.last(t["speaker"]): t["speaker"] for t in c["turns"] if t["role"] == "management"})
        calls.append(c)
    emit(sym, calls)

flush(force=True)
for w in writers.values():
    w.close()
pq.write_table(pa.Table.from_pylist(calls_out), f"{S}/out/calls.parquet", compression="zstd")
print("calls", len(calls_out), "turn rows", n_turn_rows[0], flush=True)
