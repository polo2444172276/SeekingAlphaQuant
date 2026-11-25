# Earnings-call transcripts: point-in-time top-100 S&P 500

Speaker-level earnings-call transcripts for the 100 largest S&P 500 companies, where
"largest" is decided **as of the quarter-end before each call** (no look-ahead in the universe).

Stored in Supabase Storage, bucket `market-data` (catalogued in `data_files`):

| path | rows | contents |
|---|---|---|
| `us/sp500_top100/earnings_calls/calls.parquet` | 1 per call | symbol, call_date, fiscal_year/quarter, cik, mcap_rank, rank_quarter, ceo_name, ceo_src, source, url |
| `us/sp500_top100/earnings_calls/turns/year=YYYY.parquet` | 1 per speaker turn | symbol, call_date, mcap_rank, turn, speaker, role (management/analyst/operator/unknown), section (prepared/qa), title, role_src, **is_ceo**, text |

Coverage as of the 2026-11-25 build: 7,197 calls, 569,781 turns, 2005-10 to 2026-11.

## Sources
- **2005-10 .. 2025-05-15**: Hugging Face `zcyeee/sp500-earnings-call-turns` (MIT; speaker turns and roles
  from that dataset; misfiled calls with `company_check = not_this_company`, `tiny_content`, `no_speaker_labels` dropped).
- **after 2025-05-15**: Motley Fool transcript pages (www.fool.com, robots.txt allows `/earnings/call-transcripts/`;
  Content-Signal `ai-input=yes`, `ai-train=no` — use for analysis, not model training). Parsed by `fool_parse.py`.
  Call date comes from the page's Date block, not the URL (the URL date is the publication date; back-filled
  transcripts can be published months later).

## Known gaps / caveats
- Fool does not publish every call. Top-100 companies with a call in the window: ~99/100 per quarter through 2024,
  ~86-92 in 2025-Q4..2026-Q3 rank quarters, but only ~56 for calls held Jul-Dec 2025 (rank quarters 2025-Q2/Q3).
- Market caps: FMP `historical-market-capitalization` at quarter-ends. 15 delisted symbols have no FMP history and
  can never rank (none were top-100 mega caps). Second share classes (GOOG, FOX, NWS, ...) dropped.
- S&P 500 membership is checked only from 2018-11 (Supabase `index_membership`); before that the universe is every
  symbol in the HF dataset (all were S&P 500 members at some point).
- CEO identification (`ceo_src`): `title` (participant list / affiliation), `intro` (IR opening names the CEO),
  `roster`, `carry` (same person as the previous call's CEO), `fmp_current` (FMP current CEO, only after the last
  call that named someone else). `fmp_current` uses information from a later date: drop it for strict
  point-in-time studies. (A nearest-call `propagated` rule was tried and removed: it labelled future CEOs as CEO
  on calls where they spoke as COO/CFO/IR, e.g. Tim Cook in 2009-2011.)
  Some calls have no CEO on the line (e.g. pre-2016 Exxon, Ballmer-era Microsoft): `ceo_name` is null there.

## Rebuild
```
W=<workdir>
python fetch_mcap.py $W                   # quarter-end market caps -> $W/mcap/*.json (needs $W/hf/data shards)
python fool_fetch.py $W tickers.json      # pages listed in Fool's monthly sitemaps
python fool_quote_links.py $W tickers.json  # plus links on each ticker's Fool quote page
python build.py $W                        # -> $W/out/calls.parquet, $W/out/turns/year=YYYY.parquet
python upload.py $W                       # -> Storage + data_files
```
`$W/sp500_membership.json` is an export of `index_membership` joined to `securities.symbol`.
