# SeekingAlphaQuantReplicate

A Python replica of Seeking Alpha's Quant Rating methodology for the S&P
500, built as a point-in-time historical backtesting system (not just a
live snapshot tool).

Five factor grades — Valuation, Growth, Profitability, Momentum, EPS
Revisions — are computed by ranking each stock's underlying metrics against
its GICS sector peers, then combined into an overall Strong Sell → Strong
Buy rating. See `/Users/guolunli/.claude/plans/moonlit-prancing-pie.md` for
the full design doc and phasing.

## Known deviation from the real methodology

Seeking Alpha's EPS Revisions factor needs historical point-in-time
consensus-estimate snapshots, which the chosen data provider (Financial
Modeling Prep) doesn't offer, and true sell-side revision-history vendors
(Zacks/Nasdaq Data Link, Intrinio's Zacks bundle, Estimize) were
deliberately not integrated. `factors/eps_revisions.py` proxies this factor
with net analyst upgrades minus downgrades instead — directionally useful,
not a faithful replica. Exact SA factor weights and percentile-to-grade
cutoffs are also not public; `config.py` uses documented, configurable
approximations.

The historical backfill (`seekingalpha_quant/backtest/`, see below) adds
its own documented approximations on top of the above, since FMP's Starter
plan doesn't expose pre-computed historical ratios at any point-in-time
resolution:
- **All Valuation/Growth ratios are computed by hand** from raw quarterly
  financial statements + historical market cap
  (`backtest/fundamentals_pit.py`), not pulled pre-computed — there's no
  guarantee they exactly match FMP's own (undocumented) `ratios-ttm`
  formulas used by the live daily snapshot, though a spot-check against
  NVDA's current live-vs-backfilled numbers landed within a few percent.
- **Growth is rolling-TTM, not fixed-fiscal-year**: `revenue_growth_yoy`
  compares the trailing 4 quarters to the trailing 4 quarters one year
  prior; the live daily snapshot instead compares this fiscal year to last
  fiscal year (FMP's `financial-growth` endpoint, annual period). Both are
  legitimate "YoY growth" measures, but they can diverge meaningfully for
  a fast-decelerating/accelerating grower — confirmed this analytically
  live for NVDA (rolling-TTM read ~83% vs. the live snapshot's fixed-FY
  ~65% on the same day).
- **ROIC has no public FMP formula to match**, live or historical; the
  backfill approximates it as after-tax operating income (using each
  ticker's own trailing effective tax rate) over invested capital
  (debt + equity − cash).
- **Sector is each ticker's *current* FMP sector classification, applied
  to all of its history** — no attempt to track historical GICS
  reclassifications.
- **Point-in-time knowability** is gated on each filing's `acceptedDate`
  (when it actually became public), not its fiscal period-end date, to
  avoid lookahead bias — confirmed live that `acceptedDate` is populated
  back to 2019 for the tickers checked; a missing value falls back to
  period-end + 45 days.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in FMP_API_KEY once you have one
```

## Status

- **Done**: factor scoring math (`seekingalpha_quant/factors/`), overall
  rating combination (`seekingalpha_quant/scoring/combine.py`), config
  (`seekingalpha_quant/config.py`), FMP client with disk caching and
  client-side rate limiting (`seekingalpha_quant/data/fmp_client.py`), live
  data ingestion (`seekingalpha_quant/data/fundamentals.py`, `prices.py`,
  `estimates.py`), and `scripts/run_snapshot.py` — a daily current-state
  snapshot (not yet point-in-time/backtestable) for the full S&P 500
  (`seekingalpha_quant/data/universe.py`, reads
  `data/sp500_constituents.csv`, refreshed via
  `scripts/update_universe.py`). Verified end-to-end against live FMP data
  for all 503 constituents (zero 402s under the Starter plan). All logic
  also covered by `pytest tests/` against in-memory fixtures — no API key
  required to run those.
- **Known FMP plan gap**: the free tier 402s roughly a third of large-cap
  symbols across every fundamentals/price endpoint (not a rate limit — an
  inconsistent per-symbol allowlist); a paid Starter-tier key restored
  access to every S&P 500 constituent tried so far. `fmp_client.py` caches
  a 402 response itself (not just successes) so re-running doesn't keep
  re-probing a symbol already known to be blocked under the plan in use —
  clear `.cache/` after a plan upgrade to re-probe. Separately, the
  official `sp500-constituent` endpoint 402s even on Starter, so the
  ticker/sector *list* itself comes from a free non-FMP source instead
  (`scripts/update_universe.py`) — only the per-ticker fundamentals/price
  data comes from FMP.
- **Also done**: point-in-time historical backfill since 2019
  (`seekingalpha_quant/backtest/`, run via `scripts/run_backtest.py`).
  Valuation/Growth/Profitability/EPS Revisions are reconstructed at
  quarterly resolution (gated on each filing's real `acceptedDate` to
  avoid lookahead bias); Momentum, and therefore the combined overall
  score, is recomputed daily and combined with whichever quarter's
  fundamentals were most recently *known* as of that day (carried forward,
  not recomputed daily). Point-in-time S&P 500 membership (avoiding
  survivorship bias) comes from a free community-maintained changes log
  (`scripts/update_membership_history.py` →
  `data/sp500_membership_changes.csv`), not FMP (no point-in-time
  constituents endpoint at any tier tried). Output is two Parquet files
  under `data/history/` (gitignored, like `data/snapshots/` — generated
  data isn't committed). No dashboard/chart integration yet — data only.

## Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```
