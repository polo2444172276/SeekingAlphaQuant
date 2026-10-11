"""Self-hosted Factor Ledger dashboard.

Reads the most recent data/snapshots/<date>.csv directly off disk — no
Claude Artifact / db dependency. Protected with HTTP Basic Auth; put this
behind Caddy (or similar) for TLS since Basic Auth is plaintext-on-the-wire
otherwise.
"""

import csv
import glob
import hmac
import json
import os

import markdown
from dotenv import load_dotenv
from flask import Flask, Response, abort, render_template, request

from seekingalpha_quant.config import (
    FACTOR_METRICS,
    SMALLCAP_MAX_COVERAGE,
    SMALLCAP_MIN_DOLLAR_VOLUME,
)

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "data", "snapshots")
SMALLCAP_SNAPSHOT_DIR = os.path.join(BASE_DIR, "data", "snapshots_smallcap")
ANALYSIS_DIR = os.path.join(BASE_DIR, "data", "fundamental_analysis")
VOLATILITY_PATH = os.path.join(BASE_DIR, "data", "volatility", "history.csv")
SENTIMENT_PATH = os.path.join(BASE_DIR, "data", "sentiment", "latest.json")

VOLATILITY_METRICS = [
    {"col": "vix", "label": "VIX", "desc": "CBOE Volatility Index (S&P 500 30-day implied vol)"},
    {"col": "move", "label": "MOVE", "desc": "ICE BofA MOVE Index (Treasury rates implied vol)"},
    {"col": "skew", "label": "SKEW", "desc": "CBOE SKEW Index (tail-risk / put-call skew proxy)"},
]

DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

SCORE_COLS = [
    "valuation_score", "growth_score", "profitability_score",
    "momentum_score", "eps_revisions_score", "sector_specific_score", "overall_score",
]
GRADE_COLS = [
    "valuation_grade", "growth_grade", "profitability_grade",
    "momentum_grade", "eps_revisions_grade", "sector_specific_grade",
]

FACTOR_ORDER = ["valuation", "growth", "profitability", "momentum", "eps_revisions", "sector_specific"]
FACTOR_LABELS = {
    "valuation": "Valuation",
    "growth": "Growth",
    "profitability": "Profitability",
    "momentum": "Momentum",
    "eps_revisions": "EPS Rev",
    "sector_specific": "Sector",
}
METRIC_LABELS = {
    "pe_ratio": "P/E", "pb_ratio": "P/B", "ps_ratio": "P/S", "pcf_ratio": "P/CF",
    "peg_ratio": "PEG", "ev_to_sales": "EV/Sales", "ev_to_ebitda": "EV/EBITDA",
    "revenue_growth_yoy": "Rev YoY", "revenue_growth_3y": "Rev 3Y",
    "revenue_growth_5y": "Rev 5Y", "eps_growth_yoy": "EPS YoY",
    "eps_growth_3y": "EPS 3Y", "eps_growth_5y": "EPS 5Y",
    "ebitda_growth_yoy": "EBITDA YoY",
    "gross_margin": "Gross Mgn", "operating_margin": "Op Mgn",
    "net_margin": "Net Mgn", "ebitda_margin": "EBITDA Mgn",
    "roe": "ROE", "roa": "ROA", "roic": "ROIC",
    "return_1m": "1M", "return_3m": "3M", "return_6m": "6M",
    "return_9m": "9M", "return_ytd": "YTD", "return_12m": "12M",
    "net_upgrades_1m": "Net Upg 1M", "net_upgrades_3m": "Net Upg 3M",
    "rule_of_40": "Rule of 40", "nim_proxy": "NIM (proxy)",
    "ffo_margin": "FFO Margin", "rd_intensity": "R&D Intensity",
    "inventory_turnover": "Inv. Turnover",
}
# How to format each raw metric's value; anything not listed here defaults
# to a plain 2-decimal ratio (valuation multiples).
PERCENT_METRICS = {
    "revenue_growth_yoy", "revenue_growth_3y", "revenue_growth_5y",
    "eps_growth_yoy", "eps_growth_3y", "eps_growth_5y", "ebitda_growth_yoy",
    "gross_margin", "operating_margin", "net_margin", "ebitda_margin",
    "roe", "roa", "roic",
    "return_1m", "return_3m", "return_6m", "return_9m", "return_ytd", "return_12m",
    "nim_proxy", "ffo_margin", "rd_intensity",
}
COUNT_METRICS = {"net_upgrades_1m", "net_upgrades_3m"}

SECTOR_RETURN_METRICS = ["return_1w", "return_1m", "return_12m"]


def _build_factor_defs():
    defs = []
    for key in FACTOR_ORDER:
        metrics = [
            {"col": col, "label": METRIC_LABELS.get(col, col)}
            for col in FACTOR_METRICS[key]
        ]
        defs.append({
            "key": key,
            "label": FACTOR_LABELS[key],
            "grade_col": f"{key}_grade",
            "metrics": metrics,
        })
    return defs


FACTOR_DEFS = _build_factor_defs()
ALL_METRIC_COLS = [m["col"] for f in FACTOR_DEFS for m in f["metrics"]]

app = Flask(__name__)


def check_auth(username, password):
    if not DASHBOARD_PASSWORD:
        return False
    return hmac.compare_digest(username, DASHBOARD_USER) and hmac.compare_digest(
        password, DASHBOARD_PASSWORD
    )


def authenticate():
    return Response(
        "Authentication required", 401,
        {"WWW-Authenticate": 'Basic realm="Factor Ledger"'},
    )


def requires_auth(view):
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return view(*args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


def _parse_score(value):
    if value is None or value == "":
        return None
    return round(float(value), 1)


def _format_metric(col, value):
    if value is None or value == "":
        return None
    v = float(value)
    if col in COUNT_METRICS:
        return f"{int(round(v)):+d}"
    if col in PERCENT_METRICS:
        return f"{v * 100:.1f}%"
    return f"{v:.2f}"


def _coerce_float(value):
    if value is None or value == "":
        return None
    return float(value)


def latest_snapshot(snapshot_dir):
    files = sorted(glob.glob(os.path.join(snapshot_dir, "*.csv")))
    if not files:
        return None, []
    path = files[-1]
    date = os.path.splitext(os.path.basename(path))[0]
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    has_screen_cols = rows and "analyst_coverage" in rows[0]
    for row in rows:
        for col in SCORE_COLS:
            row[col] = _parse_score(row.get(col))
        for col in GRADE_COLS + ["overall_rating"]:
            row[col] = row.get(col) or None
        for col in ALL_METRIC_COLS:
            row[col] = _format_metric(col, row.get(col))
        if has_screen_cols:
            coverage = _coerce_float(row.get("analyst_coverage"))
            dollar_vol = _coerce_float(row.get("avg_dollar_volume"))
            row["off_radar"] = (
                coverage is not None and dollar_vol is not None
                and coverage <= SMALLCAP_MAX_COVERAGE
                and dollar_vol >= SMALLCAP_MIN_DOLLAR_VOLUME
            )
            row["analyst_coverage"] = None if coverage is None else int(coverage)
            row["avg_dollar_volume"] = (
                None if dollar_vol is None else f"${dollar_vol / 1_000_000:.1f}M"
            )
    # Tickers with unresolved data (e.g. sector missing under the current
    # FMP plan) score None -- sort them after every real rating instead of
    # crashing the comparison.
    rows.sort(key=lambda r: (r["overall_score"] is None, -(r["overall_score"] or 0)))
    return date, rows, has_screen_cols


def sector_performance(snapshot_dir):
    """Equal-weighted average trailing return per sector, from the latest
    snapshot in `snapshot_dir`. Averages only over tickers that actually
    have a value for that window (new listings etc. are skipped, not
    treated as 0)."""
    files = sorted(glob.glob(os.path.join(snapshot_dir, "*.csv")))
    if not files:
        return None, []
    path = files[-1]
    date = os.path.splitext(os.path.basename(path))[0]
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    by_sector = {}
    for row in rows:
        sector = row.get("sector")
        if not sector:
            continue
        bucket = by_sector.setdefault(sector, {"count": 0, "sums": {}, "counts": {}})
        bucket["count"] += 1
        for m in SECTOR_RETURN_METRICS:
            v = _coerce_float(row.get(m))
            if v is not None:
                bucket["sums"][m] = bucket["sums"].get(m, 0.0) + v
                bucket["counts"][m] = bucket["counts"].get(m, 0) + 1

    sectors = []
    for sector, bucket in by_sector.items():
        entry = {"sector": sector, "num_tickers": bucket["count"]}
        for m in SECTOR_RETURN_METRICS:
            c = bucket["counts"].get(m, 0)
            avg = (bucket["sums"][m] / c) if c else None
            entry[m] = avg
            entry[f"{m}_fmt"] = f"{avg * 100:+.1f}%" if avg is not None else "—"
        sectors.append(entry)
    sectors.sort(key=lambda r: (r["return_1m"] is None, -(r["return_1m"] or 0)))
    return date, sectors


@app.route("/")
@requires_auth
def dashboard():
    date, rows, has_screen_cols = latest_snapshot(SNAPSHOT_DIR)
    return render_template(
        "dashboard.html", date=date, rows=rows, factor_defs=FACTOR_DEFS,
        active="sp500", title="Factor Ledger — S&P 500", has_screen_cols=has_screen_cols,
        max_coverage=SMALLCAP_MAX_COVERAGE, min_dollar_volume=SMALLCAP_MIN_DOLLAR_VOLUME,
    )


@app.route("/smallcap")
@requires_auth
def smallcap_dashboard():
    date, rows, has_screen_cols = latest_snapshot(SMALLCAP_SNAPSHOT_DIR)
    return render_template(
        "dashboard.html", date=date, rows=rows, factor_defs=FACTOR_DEFS,
        active="smallcap", title="Factor Ledger — Small Cap", has_screen_cols=has_screen_cols,
        max_coverage=SMALLCAP_MAX_COVERAGE, min_dollar_volume=SMALLCAP_MIN_DOLLAR_VOLUME,
    )


def _pct_change(values, periods_back):
    if len(values) <= periods_back:
        return None
    start, end = values[-1 - periods_back], values[-1]
    if start is None or end is None:
        return None
    return end / start - 1


def _sparkline_points(values, width=280, height=40, pad=4):
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(values)
    step = (width - 2 * pad) / (n - 1)
    points = []
    for i, v in enumerate(values):
        if v is None:
            continue
        x = pad + i * step
        y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def volatility_snapshot():
    if not os.path.exists(VOLATILITY_PATH):
        return None, []
    with open(VOLATILITY_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return None, []
    date = rows[-1]["date"]

    metrics = []
    for m in VOLATILITY_METRICS:
        col = m["col"]
        values = [_coerce_float(r.get(col)) for r in rows]
        latest = values[-1]
        chg_1d = _pct_change(values, 1)
        chg_1w = _pct_change(values, 5)
        chg_1m = _pct_change(values, 21)
        metrics.append({
            "col": col,
            "label": m["label"],
            "desc": m["desc"],
            "latest": round(latest, 2) if latest is not None else None,
            "chg_1d": chg_1d,
            "chg_1d_fmt": f"{chg_1d * 100:+.1f}%" if chg_1d is not None else "—",
            "chg_1w": chg_1w,
            "chg_1w_fmt": f"{chg_1w * 100:+.1f}%" if chg_1w is not None else "—",
            "chg_1m": chg_1m,
            "chg_1m_fmt": f"{chg_1m * 100:+.1f}%" if chg_1m is not None else "—",
            "spark_points": _sparkline_points(values[-90:]),
        })
    return date, metrics


@app.route("/volatility")
@requires_auth
def volatility_dashboard():
    date, metrics = volatility_snapshot()
    return render_template(
        "volatility.html", date=date, metrics=metrics,
        active="volatility", title="Factor Ledger — Volatility",
    )


RATING_ORDER = ["extreme fear", "fear", "neutral", "greed", "extreme greed"]


def _rating_class(rating):
    return (rating or "").replace(" ", "-")


@app.route("/sentiment")
@requires_auth
def sentiment_dashboard():
    if not os.path.exists(SENTIMENT_PATH):
        return render_template(
            "sentiment.html", date=None, overall=None, components=[],
            active="sentiment", title="Factor Ledger — Sentiment",
        )
    with open(SENTIMENT_PATH) as f:
        snapshot = json.load(f)

    overall = snapshot["overall"]
    hist_scores = [p["score"] for p in overall["historical"]]
    overall["spark_points"] = _sparkline_points(hist_scores[-180:])
    overall["rating_class"] = _rating_class(overall["rating"])
    overall["chg_1d"] = round(overall["score"] - overall["previous_close"], 1)
    overall["chg_1w"] = round(overall["score"] - overall["previous_1_week"], 1)
    overall["chg_1m"] = round(overall["score"] - overall["previous_1_month"], 1)

    components = snapshot["components"]
    for c in components:
        c["rating_class"] = _rating_class(c["rating"])

    return render_template(
        "sentiment.html", date=snapshot["date"], overall=overall, components=components,
        active="sentiment", title="Factor Ledger — Sentiment",
    )


@app.route("/sectors")
@requires_auth
def sectors_dashboard():
    date, sectors = sector_performance(SNAPSHOT_DIR)
    return render_template(
        "sectors.html", date=date, sectors=sectors,
        active="sectors", title="Factor Ledger — Sector Performance",
    )


def _load_all_analyses():
    records = []
    for path in sorted(glob.glob(os.path.join(ANALYSIS_DIR, "*.json"))):
        with open(path) as f:
            records.append(json.load(f))
    return records


@app.route("/analysis")
@requires_auth
def analysis_list():
    _, smallcap_rows, _ = latest_snapshot(SMALLCAP_SNAPSHOT_DIR)
    by_ticker = {row["ticker"]: row for row in smallcap_rows}

    items = []
    for record in _load_all_analyses():
        ticker = record["ticker"]
        if not record["analyses"]:
            continue
        latest = record["analyses"][-1]
        row = by_ticker.get(ticker, {})
        items.append({
            "ticker": ticker,
            "sector": row.get("sector"),
            "overall_score": row.get("overall_score"),
            "overall_rating": row.get("overall_rating"),
            "latest_date": latest["date"],
            "num_analyses": len(record["analyses"]),
        })
    items.sort(key=lambda r: r["latest_date"], reverse=True)

    return render_template(
        "analysis_list.html", items=items, active="analysis",
        title="Factor Ledger — 基本面研报",
    )


@app.route("/analysis/<ticker>")
@requires_auth
def analysis_detail(ticker):
    path = os.path.join(ANALYSIS_DIR, f"{ticker.upper()}.json")
    if not os.path.exists(path):
        abort(404)
    with open(path) as f:
        record = json.load(f)

    entries = [
        {"date": a["date"], "html": markdown.markdown(a["content"])}
        for a in reversed(record["analyses"])
    ]

    return render_template(
        "analysis_detail.html", ticker=record["ticker"], entries=entries,
        active="analysis", title=f"Factor Ledger — {record['ticker']}",
    )


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
