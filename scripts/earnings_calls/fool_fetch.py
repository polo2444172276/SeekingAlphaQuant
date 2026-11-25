"""Download Motley Fool transcript pages for the given tickers (politely: ~1 request / 1.5 s).
usage: python fool_fetch.py <scratchpad> <tickers.json>"""
import json, os, re, sys, time, requests

S, tick_file = sys.argv[1], sys.argv[2]
want = set(json.load(open(tick_file)))
UA = "Mozilla/5.0 (compatible; research-script; personal research)"
out_dir = f"{S}/fool/pages"
os.makedirs(out_dir, exist_ok=True)


def ticker_of(url):
    slug = url.rstrip("/").split("/")[-1]
    m = re.search(r"-([a-z.]{1,6})-(?:q[1-4]|fy|h[12])-", slug)
    return m.group(1).upper().replace(".", "-") if m else None


urls = [l.strip() for l in open(f"{S}/fool/all_urls.txt") if l.strip()]
todo = [(ticker_of(u), u) for u in urls if ticker_of(u) in want]
print("to fetch:", len(todo), flush=True)
sess = requests.Session()
sess.headers["User-Agent"] = UA
n = 0
for t, u in todo:
    name = u.rstrip("/").split("/")[-1] + "__" + "-".join(u.split("/")[2:5]) + ".html"
    f = f"{out_dir}/{name}"
    if os.path.exists(f) and os.path.getsize(f) > 10000:
        continue
    for k in range(4):
        try:
            r = sess.get("https://www.fool.com/" + u, timeout=60)
            if r.status_code == 200:
                open(f, "w").write(r.text)
                break
            if r.status_code in (404, 410):
                break
            time.sleep(10 * (k + 1))
        except Exception:
            time.sleep(10 * (k + 1))
    n += 1
    if n % 50 == 0:
        print(n, flush=True)
    time.sleep(1.5)
print("done", n, flush=True)
