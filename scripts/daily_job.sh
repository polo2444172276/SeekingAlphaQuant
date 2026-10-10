#!/bin/bash
set -e
cd /home/guolunli/SeekingAlphaQuant
source /home/guolunli/.claude_env  # CLAUDE_CODE_OAUTH_TOKEN, for run_fundamental_analysis.py's headless `claude -p` calls

echo "=== $(date -u) : starting daily job ==="

python3 scripts/run_snapshot.py
TODAY=$(date -u +%Y-%m-%d)
CSV_PATH="data/snapshots/${TODAY}.csv"

if [ ! -f "$CSV_PATH" ]; then
  echo "ERROR: expected CSV not found at $CSV_PATH"
  exit 1
fi

python3 scripts/run_smallcap_snapshot.py
SMALLCAP_CSV_PATH="data/snapshots_smallcap/${TODAY}.csv"

if [ ! -f "$SMALLCAP_CSV_PATH" ]; then
  echo "ERROR: expected CSV not found at $SMALLCAP_CSV_PATH"
  exit 1
fi

# Not fatal to the rest of the job -- a Claude CLI hiccup here shouldn't
# block the cache cleanup below or mark snapshot data as missing.
python3 scripts/run_fundamental_analysis.py || echo "WARNING: run_fundamental_analysis.py failed, continuing"

# Snapshot data stays local (data/snapshots/ is gitignored) -- the dashboard
# reads it straight off disk, no need to push it anywhere.

# Price-history cache keys include today's date (via the lookback window),
# so a new entry is written every day and old ones are never reused --
# unbounded growth (~60MB/day at 503 tickers) if never pruned.
find .cache -name "*.json" -mtime +2 -delete

echo "=== $(date -u) : done ==="
