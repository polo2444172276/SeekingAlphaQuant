"""Collect transcript links from each ticker's Motley Fool quote page (catches slugs without the ticker).
Then download any not yet fetched, saving as <TICKER>__<slug>__<YYYY-MM-DD>.html.
usage: python fool_quote_links.py <scratchpad> <tickers.json>"""
import glob, json, os, re, sys, time, requests

S, tick_file = sys.argv[1], sys.argv[2]
tickers = json.load(open(tick_file))
UA = "Mozilla/5.0 (compatible; research-script; personal research)"
sess = requests.Session(); sess.headers["User-Agent"] = UA
have = {os.path.basename(f).split("__")[-2] for f in glob.glob(f"{S}/fool/pages/*.html")}
links = {}
for t in tickers:
    prof = requests.get("https://financialmodelingprep.com/stable/profile", params={"symbol": t}, timeout=30).json()
    ex = (prof[0].get("exchange") or "").lower() if isinstance(prof, list) and prof else ""
    ex = "nasdaq" if "nasdaq" in ex else "nyse"
    for exch in (ex, "nyse" if ex == "nasdaq" else "nasdaq"):
        r = sess.get(f"https://www.fool.com/quote/{exch}/{t.lower().replace('-', '.')}/", timeout=60)
        time.sleep(1.5)
        if r.status_code == 200:
            for u in set(re.findall(r'earnings/call-transcripts/(\d{4}/\d\d/\d\d)/([a-z0-9\-.]+)/', r.text)):
                if u[0] >= "2025/05":
                    links[(t, u[0], u[1])] = 1
            break
print("quote-page links:", len(links), flush=True)
n = 0
for t, d, slug in links:
    if slug in have:
        continue
    f = f"{S}/fool/pages/{t}__{slug}__{d.replace('/', '-')}.html"
    if os.path.exists(f):
        continue
    for k in range(4):
        try:
            r = sess.get(f"https://www.fool.com/earnings/call-transcripts/{d}/{slug}/", timeout=60)
            if r.status_code == 200:
                open(f, "w").write(r.text); break
            if r.status_code in (404, 410):
                break
        except Exception:
            pass
        time.sleep(10 * (k + 1))
    n += 1
    time.sleep(1.5)
print("downloaded extra:", n, flush=True)
