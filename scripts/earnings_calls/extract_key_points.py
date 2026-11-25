"""Rule-based per-call cache: forward-looking statements, numeric targets and topic tags from each call,
plus any scored predictions from analysis_results (ceo_forecast_scorecard). Free to compute, so it covers
every call; the LLM summaries (summarize.py -> transcript_summaries) can be added on top later.

Output: bucket market-data  us/sp500_top100/earnings_calls/key_points/year=YYYY.parquet  (+ data_files rows)
One row per call. Statements come from the CEO when the CEO speaks, otherwise from the other executives
(speaker and role are kept per statement).

usage: python extract_key_points.py <workdir>     # needs <workdir>/out/turns/*.parquet and out/calls.parquet
"""
import hashlib, io, json, os, re, sys
from collections import defaultdict
from datetime import datetime, timezone

import duckdb, pyarrow as pa, pyarrow.parquet as pq

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from seekingalpha_quant.data import supabase_db as db

VERSION = "extract-v1"
PREFIX = "us/sp500_top100/earnings_calls/key_points"

FWD = re.compile(r"\b(expect|anticipat|outlook|forecast|predict|going forward|next year|next quarter|over the next|"
                 r"in the coming|long[- ]term|believe .{0,40}will|we see .{0,30}(continu|improv|slow|weak|strong)|"
                 r"will (continue|remain|be)|headwind|tailwind|recover|guidance|target)", re.I)
MKT = re.compile(r"\b(econom|macro|gdp|recession|demand|consumer|market|industry|oil|crude|commodit|china|chinese|"
                 r"emerging|europe|dollar|currenc|fx|interest rate|rates|fed\b|inflation|deflation|growth|spending|"
                 r"capex|cycle|volatil|uncertain|pricing|prices|housing|employment|jobs|wage|election|regulat|tax|"
                 r"tariff|ai\b|artificial intelligence|cloud|data center)\b", re.I)
YEAR_NUM_T = re.compile(r"(20\d\d|next year|next few years|through the end of the decade|by the end of)", re.I)
YEAR_NUM_N = re.compile(r"\d+(\.\d+)?\s?(%|percent|basis points|billion|million)|\$\d")
NOISE = re.compile(r"(forward-looking statements|safe harbor|risk factors|non-gaap|reconciliation)", re.I)
TOPICS = {
    "strong dollar / fx": r"strong(er)? dollar|currency|foreign exchange|exchange rate|constant currency",
    "china": r"\bchina\b|chinese",
    "oil / energy prices": r"oil price|price of oil|crude|barrel|natural gas price|energy prices",
    "macro / growth": r"\bmacro|economic (environment|growth|backdrop|conditions)|\beconomy\b|\bgdp\b|recession|slowdown",
    "interest rates / fed": r"interest rate|rate environment|rising rates|federal reserve|\bthe fed\b|rate hike|higher rates|low rates",
    "credit / losses": r"charge-off|credit (cost|quality|loss)|loan loss|delinquen|provision",
    "housing": r"housing|home prices|mortgage",
    "consumer demand": r"consumer (spending|confidence|demand)|consumers|traffic|comparable (store )?sales",
    "inflation / pricing": r"inflation|deflation|pricing power|price increases|commodity cost",
    "emerging markets": r"emerging market|brazil|russia|india|latin america",
    "digital / mobile": r"digital|mobile|e-commerce|ecommerce|online",
    "cloud / software": r"\bcloud\b|software|\bsaas\b",
    "ai": r"artificial intelligence|machine learning|\bai\b|generative|\bagents?\b|\bgpu",
    "m&a": r"acquisition|merger|combined company|synerg",
    "cost cuts": r"cost (savings|reduction|cuts)|productivity|restructur",
    "buybacks / dividends": r"buyback|repurchase|dividend",
    "regulation / policy": r"regulat|legislat|washington|congress|tax reform|policy",
    "tariffs / trade": r"tariff|trade war|export control",
    "drug pricing": r"drug pric|biosimilar|medicare|reimbursement",
    "supply chain": r"supply chain|shortage|logistics",
}
TOPIC_RX = {k: re.compile(v, re.I) for k, v in TOPICS.items()}


def sentences(t):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", t) if 50 < len(x.strip()) < 450]


def main(W):
    con = duckdb.connect()
    calls = {(r[0], r[1]): r for r in con.execute(
        f"select symbol, call_date, source, mcap_rank, ceo_name, ceo_src from read_parquet('{W}/out/calls.parquet')").fetchall()}
    scored = defaultdict(list)
    for a in db.select("analysis_results", {"select": "params,result", "analysis": "eq.ceo_forecast_scorecard"}):
        y = (a["params"] or {}).get("year")
        win = (a["params"] or {}).get("window") or f"{y}-10-01..{y}-12-31"
        lo, hi = win.split("..")
        for it in a["result"]["items"]:
            for sym in it["symbol"].split("/"):
                hit = [k for k in calls if k[0] == sym and lo <= k[1] <= hi]
                for k in hit[:1]:
                    scored[k].append({"prediction": it["prediction"], "actual": it["actual"], "correct": it["correct"],
                                      "verified_with": it["source"], "scored_in": f"ceo_forecast_scorecard/{y}"})
    rows_by_year = defaultdict(list)
    rows = con.execute(f"""select symbol, call_date, turn, speaker, role, is_ceo, text
        from read_parquet('{W}/out/turns/*.parquet') where role = 'management' order by symbol, call_date, turn""").fetchall()
    by_call = defaultdict(list)
    for s, d, i, sp, role, ceo, t in rows:
        by_call[(s, d)].append((sp, ceo, t))
    for (s, d), turns in by_call.items():
        has_ceo = any(c for _, c, _ in turns)
        use = [(sp, c, t) for sp, c, t in turns if c] if has_ceo else turns
        fwd, num, seen = [], [], set()
        for sp, c, t in use:
            for x in sentences(t):
                if x in seen or NOISE.search(x):
                    continue
                if FWD.search(x) and MKT.search(x):
                    fwd.append({"speaker": sp, "is_ceo": bool(c), "text": x, "n_market_terms": len(MKT.findall(x))}); seen.add(x)
                elif YEAR_NUM_T.search(x) and YEAR_NUM_N.search(x):
                    num.append({"speaker": sp, "is_ceo": bool(c), "text": x}); seen.add(x)
        fwd.sort(key=lambda z: -z["n_market_terms"])
        alltext = " ".join(t for _, _, t in use)
        topics = sorted(k for k, rx in TOPIC_RX.items() if len(rx.findall(alltext)) >= 2)
        meta = calls.get((s, d))
        rows_by_year[d[:4]].append({
            "symbol": s, "call_date": d, "source": meta[2] if meta else None, "mcap_rank": meta[3] if meta else None,
            "ceo_name": meta[4] if meta else None, "ceo_src": meta[5] if meta else None, "ceo_present": has_ceo,
            "topics": topics, "forward_statements": json.dumps(fwd[:15]), "numeric_targets": json.dumps(num[:10]),
            "scored_predictions": json.dumps(scored.get((s, d), [])), "version": VERSION})
    with db.change_note(f"Per-call key-point cache {VERSION}: forward-looking statements, numeric targets, topic tags, scored predictions"):
        for y, rs in sorted(rows_by_year.items()):
            buf = io.BytesIO(); pq.write_table(pa.Table.from_pylist(rs), buf, compression="zstd"); data = buf.getvalue()
            path = f"{PREFIX}/year={y}.parquet"
            db.upload(path, data)
            db.upsert("data_files", [{"path": path, "market": "US", "kind": "earnings_call_key_points", "year": int(y),
                                      "rows": len(rs), "min_date": min(r["call_date"] for r in rs),
                                      "max_date": max(r["call_date"] for r in rs), "sha256": hashlib.sha256(data).hexdigest(),
                                      "updated_at": datetime.now(timezone.utc).isoformat()}], on_conflict="path")
            print(path, len(rs), f"{len(data)/1e6:.1f} MB", flush=True)
    print("calls with scored predictions:", sum(1 for v in scored.values() if v))


if __name__ == "__main__":
    main(sys.argv[1])
