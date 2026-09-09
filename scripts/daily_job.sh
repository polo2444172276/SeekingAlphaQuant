#!/bin/bash
set -e
cd /home/guolunli/SeekingAlphaQuant

echo "=== $(date -u) : starting daily job ==="

python3 scripts/run_snapshot.py
TODAY=$(date -u +%Y-%m-%d)
CSV_PATH="data/snapshots/${TODAY}.csv"

if [ ! -f "$CSV_PATH" ]; then
  echo "ERROR: expected CSV not found at $CSV_PATH"
  exit 1
fi

# Snapshot data stays local (data/snapshots/ is gitignored) -- the dashboard
# reads it straight off disk, no need to push it anywhere.

# Price-history cache keys include today's date (via the lookback window),
# so a new entry is written every day and old ones are never reused --
# unbounded growth (~60MB/day at 503 tickers) if never pruned.
find .cache -name "*.json" -mtime +2 -delete

echo "=== $(date -u) : done ==="
