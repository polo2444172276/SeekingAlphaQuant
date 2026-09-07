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
  (`seekingalpha_quant/config.py`), FMP client with disk caching
  (`seekingalpha_quant/data/fmp_client.py`), live data ingestion
  (`seekingalpha_quant/data/fundamentals.py`, `prices.py`, `estimates.py`),
  and `scripts/run_snapshot.py` — a daily current-state snapshot (not yet
  point-in-time/backtestable) for a hand-maintained watchlist
  (`seekingalpha_quant/data/universe.py`, currently 30 large-caps). Verified
  end-to-end against live FMP data. All logic also covered by `pytest
  tests/` against in-memory fixtures — no API key required to run those.
- **Known FMP plan gap**: the free tier 402s roughly a third of large-cap
  symbols across every fundamentals/price endpoint (not a rate limit — an
  inconsistent per-symbol allowlist); a paid Starter-tier key restored
  access to all 30 tracked tickers. `fmp_client.py` caches a 402 response
  itself (not just successes) so re-running doesn't keep re-probing a
  symbol already known to be blocked under the plan in use — clear
  `.cache/` after a plan upgrade to re-probe.
- **Not yet built**: point-in-time S&P 500 universe reconstruction (the
  official constituents endpoint 402s even on Starter — needs a higher
  tier, or a non-FMP source), the backtest engine, and
  `scripts/run_backtest.py`.

## Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```
