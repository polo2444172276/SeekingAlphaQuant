"""Parquet read/write helpers for the historical backfill output.

data/history/ is gitignored (same policy as data/snapshots/, per explicit
"don't store data in git" instruction) -- these are generated artifacts,
not source data.
"""

import os

import pandas as pd

HISTORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "history",
)
QUARTERLY_PATH = os.path.join(HISTORY_DIR, "quarterly_fundamentals.parquet")
DAILY_PATH = os.path.join(HISTORY_DIR, "daily_history.parquet")


def save_quarterly(df):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    df.to_parquet(QUARTERLY_PATH, engine="pyarrow", index=False)


def load_quarterly():
    return pd.read_parquet(QUARTERLY_PATH, engine="pyarrow")


def save_daily(df):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    df.to_parquet(DAILY_PATH, engine="pyarrow", index=False)


def load_daily():
    return pd.read_parquet(DAILY_PATH, engine="pyarrow")
