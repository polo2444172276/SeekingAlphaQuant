"""Daily job: have Claude write a fundamental research note on the top 10
"off the radar" small-cap candidates (low analyst coverage + decent
liquidity -- same screen as scripts/run_smallcap_snapshot.py, config.
SMALLCAP_MAX_COVERAGE / SMALLCAP_MIN_DOLLAR_VOLUME).

Each ticker is re-analyzed at most once every REANALYSIS_DAYS, so a name
that stays in the top 10 for a week doesn't burn a fresh LLM call every
day. Results accumulate in data/fundamental_analysis/<TICKER>.json (one
file per ticker, a list of dated analyses) -- the dashboard's Analysis tab
reads straight from there.

Uses the `claude` CLI in headless mode (`claude -p`), authenticated via
CLAUDE_CODE_OAUTH_TOKEN (see /home/guolunli/.claude_env) -- plain text
generation, no Artifact tool needed, so this works fine under cron.

Usage:
    python scripts/run_fundamental_analysis.py
"""

import csv
import datetime as dt
import glob
import json
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seekingalpha_quant.config import SMALLCAP_MAX_COVERAGE, SMALLCAP_MIN_DOLLAR_VOLUME
from seekingalpha_quant.data.fmp_client import FMPClient, SymbolNotEntitled

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "snapshots_smallcap")
ANALYSIS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "fundamental_analysis"))
TOP_N = 10
REANALYSIS_DAYS = 7


def latest_snapshot_path():
    files = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "*.csv")))
    return files[-1] if files else None


def _is_off_radar(row):
    try:
        coverage = float(row["analyst_coverage"])
        dollar_vol = float(row["avg_dollar_volume"])
    except (TypeError, ValueError, KeyError):
        return False
    return coverage <= SMALLCAP_MAX_COVERAGE and dollar_vol >= SMALLCAP_MIN_DOLLAR_VOLUME


def load_candidates():
    path = latest_snapshot_path()
    if not path:
        return []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    candidates = [r for r in rows if r.get("overall_score") and _is_off_radar(r)]
    candidates.sort(key=lambda r: float(r["overall_score"]), reverse=True)
    return candidates[:TOP_N]


def analysis_path(ticker):
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    return os.path.join(ANALYSIS_DIR, f"{ticker}.json")


def load_existing(ticker):
    path = analysis_path(ticker)
    if not os.path.exists(path):
        return {"ticker": ticker, "analyses": []}
    with open(path) as f:
        return json.load(f)


def needs_analysis(record):
    if not record["analyses"]:
        return True
    last_date = dt.date.fromisoformat(record["analyses"][-1]["date"])
    return (dt.date.today() - last_date).days >= REANALYSIS_DAYS


def build_prompt(ticker, row, profile):
    name = profile.get("companyName") or ticker
    description = (profile.get("description") or "")[:1500]
    metrics_lines = [
        f"- 综合评分: {row.get('overall_score')} ({row.get('overall_rating')})",
        f"- 估值 (Valuation) grade: {row.get('valuation_grade')} "
        f"(P/E {row.get('pe_ratio')}, P/B {row.get('pb_ratio')}, P/S {row.get('ps_ratio')})",
        f"- 成长 (Growth) grade: {row.get('growth_grade')} "
        f"(营收YoY {row.get('revenue_growth_yoy')}, EPS YoY {row.get('eps_growth_yoy')})",
        f"- 盈利能力 (Profitability) grade: {row.get('profitability_grade')} "
        f"(ROE {row.get('roe')}, ROIC {row.get('roic')}, 净利率 {row.get('net_margin')})",
        f"- 动量 (Momentum) grade: {row.get('momentum_grade')} "
        f"(1月 {row.get('return_1m')}, 3月 {row.get('return_3m')}, 12月 {row.get('return_12m')})",
        f"- EPS预期修正 grade: {row.get('eps_revisions_grade')} "
        f"(近1月净上调家数 {row.get('net_upgrades_1m')}, 近3月 {row.get('net_upgrades_3m')})",
        f"- 分析师覆盖: {row.get('analyst_coverage')} 家, 日均成交额 ${row.get('avg_dollar_volume')}",
        f"- 行业: {row.get('sector')}",
    ]
    return (
        f"你是一位基本面分析师。下面是股票 {ticker}({name}) 的量化因子打分和公司简介,"
        "请写一份中文基本面研报,控制在500-800字,结构包含:公司业务简介、主要财务/估值亮点、"
        "增长与盈利能力解读、潜在风险、总体结论。不构成投资建议,只做研究参考。\n\n"
        f"公司简介:{description or '(无简介数据)'}\n\n"
        "量化因子数据:\n" + "\n".join(metrics_lines)
    )


def run_claude(prompt):
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p exited {result.returncode}: {result.stderr[:500]}")
    return result.stdout.strip()


def main():
    candidates = load_candidates()
    if not candidates:
        print("No off-radar candidates found in latest smallcap snapshot.", file=sys.stderr)
        return

    client = FMPClient()
    for row in candidates:
        ticker = row["ticker"]
        record = load_existing(ticker)
        if not needs_analysis(record):
            print(f"[skip] {ticker}: analyzed within the last {REANALYSIS_DAYS} days", file=sys.stderr)
            continue

        try:
            profile_rows = client.get("/stable/profile", {"symbol": ticker}, daily_cache=True)
            profile = profile_rows[0] if profile_rows else {}
        except SymbolNotEntitled:
            profile = {}

        prompt = build_prompt(ticker, row, profile)
        try:
            content = run_claude(prompt)
        except Exception as exc:
            print(f"[error] {ticker}: {exc}", file=sys.stderr)
            continue

        record["analyses"].append({"date": dt.date.today().isoformat(), "content": content})
        with open(analysis_path(ticker), "w") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        print(f"[ok] {ticker}: analysis saved ({len(content)} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
