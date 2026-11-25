"""Point-in-time top-N S&P 500 universe by quarter-end market cap (FMP historical market cap)."""
import glob, json, os, bisect
from collections import defaultdict

# second share classes: keep one listing per company
DROP_CLASSES = {"GOOG", "FOX", "NWS", "BRK-A", "UA", "DISCK", "DISCB", "LEN-B", "HEI-A", "BF-A", "ZG", "CMCSK", "VIA", "Z"}


def load_mcap(S):
    q = defaultdict(dict)  # quarter-end key (YYYY-Qn) -> {symbol: (date, mcap)}
    for f in glob.glob(f"{S}/mcap/*.json"):
        sym = os.path.basename(f)[:-5]
        if sym in DROP_CLASSES:
            continue
        for x in json.load(open(f)):
            k = f"{x['date'][:4]}-Q{(int(x['date'][5:7]) - 1) // 3 + 1}"
            q[k][sym] = (x["date"], x["marketCap"])
    return q


def load_membership(S):
    """symbol -> list of (start, end) from Supabase index_membership (covers 2018-11 onward)."""
    m = defaultdict(list)
    for r in json.load(open(f"{S}/sp500_membership.json")):
        if r["symbol"]:
            m[r["symbol"]].append((r["start_date"], r["end_date"] or "9999-12-31"))
    return m


def is_member(mem, sym, date):
    if date < "2018-11-01":
        return True  # no membership history before then: universe = all symbols in the S&P 500 transcript dataset
    if sym not in mem:
        return True  # renamed tickers (FB->META, ANTM->ELV): membership table keeps the old symbol
    return any(a <= date <= b for a, b in mem.get(sym, []))


def topn(S, n=100):
    q = load_mcap(S)
    mem = load_membership(S)
    out = {}  # quarter key -> {symbol: rank}
    for k, d in q.items():
        if k[-2:] not in ("Q1", "Q2", "Q3", "Q4"):
            continue
        rows = [(s, v[1]) for s, v in d.items() if v[1] and is_member(mem, s, v[0])]
        rows.sort(key=lambda r: -r[1])
        out[k] = {s: i + 1 for i, (s, _) in enumerate(rows[:n])}
    return out


def prev_quarter_key(date):
    """Ranking a reader could know before the call: the last quarter-end strictly before `date`."""
    y, m = int(date[:4]), int(date[5:7])
    qn = (m - 1) // 3  # current quarter index 0..3 -> previous quarter
    if qn == 0:
        return f"{y - 1}-Q4"
    return f"{y}-Q{qn}"
