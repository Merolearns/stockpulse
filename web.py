"""stockpulse web dashboard: browse tracked symbols and their indicator
reports in the browser instead of the terminal.

Same data and math as the CLI — the report page reuses stockpulse's
report_data(), so the numbers never drift from `report aapl`.

Run with: python web.py  (then open http://127.0.0.1:5000)
"""

import os
import sqlite3

from flask import Flask, redirect, render_template, request, url_for

from db import DEFAULT_DB, connect, get_prices
from downloader import DownloadError, fetch, normalize_symbol
from indicators import daily_returns, volatility
from stockpulse import report_data

app = Flask(__name__)

DAYS_OPTIONS = (30, 60, 90)

# a report page renders every bar as a table row and a chart point, so
# cap the window at a year — ?days=100000 used to dump the whole history
DAYS_MAX = 365


def _db_path():
    # env override so tests can point at a throwaway db without touching
    # the real stockpulse.db
    return os.environ.get("STOCKPULSE_DB") or DEFAULT_DB


def _tracked_symbols(conn):
    """One row per symbol: bars stored, last date, last close."""
    try:
        symbols = [
            r["symbol"]
            for r in conn.execute(
                "SELECT DISTINCT symbol FROM prices ORDER BY symbol"
            ).fetchall()
        ]
    except sqlite3.OperationalError:
        return []  # fresh db with no table yet — nothing tracked
    tracked = []
    for sym in symbols:
        rows = get_prices(conn, sym)
        tracked.append(
            {
                "symbol": sym,
                "bars": len(rows),
                "last_date": rows[-1]["date"],
                "last_close": rows[-1]["close"],
            }
        )
    return tracked


def _fmt(v):
    return f"{v:.2f}" if v is not None else "—"


def _stat_cards(data):
    """The five numbers at the top of the report page, from report_data()."""
    closes = data["closes"]
    rets = daily_returns(closes)
    vol = volatility(closes, 20)
    rsi_last = data["rsi14"][-1]
    sma50_last = data["sma50"][-1]
    if rsi_last is None:
        rsi_label = None
    elif rsi_last > 70:
        rsi_label = "overbought"
    elif rsi_last < 30:
        rsi_label = "oversold"
    else:
        rsi_label = "neutral"
    if sma50_last is None:
        vs_avg = None
    else:
        trend = "above" if closes[-1] > sma50_last else "below"
        vs_avg = f"{trend} {sma50_last:.2f}"
    return {
        "last_close": _fmt(closes[-1]),
        "last_return": f"{rets[-1]:+.2%}" if rets[-1] is not None else "—",
        "volatility": f"{vol:.2%}" if vol is not None else "—",
        "rsi": _fmt(rsi_last),
        "rsi_label": rsi_label,
        "vs_avg": vs_avg,
    }


def _price_chart(rows, closes, sma20, sma50):
    """Inline SVG line chart: closes plus SMA20/SMA50. No JS, no libs."""
    width, height = 880, 300
    pad_l, pad_r, pad_t, pad_b = 56, 12, 12, 28
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    series = [
        (closes, "close-line"),
        (sma20, "sma20-line"),
        (sma50, "sma50-line"),
    ]
    values = [v for s, _ in series for v in s if v is not None]
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        hi = lo + 1
    span = hi - lo
    lo -= span * 0.05
    hi += span * 0.05

    def x(i):
        if len(closes) == 1:
            return pad_l + plot_w / 2
        return pad_l + plot_w * i / (len(closes) - 1)

    def y(v):
        return pad_t + plot_h * (1 - (v - lo) / (hi - lo))

    def polyline(vals):
        pts = " ".join(
            f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals) if v is not None
        )
        return pts

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Price chart">'
    ]
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_t + plot_h * frac
        val = hi - (hi - lo) * frac
        parts.append(
            f'<line class="gridline" x1="{pad_l}" y1="{gy:.1f}" '
            f'x2="{width - pad_r}" y2="{gy:.1f}"/>'
        )
        parts.append(
            f'<text class="axis-label" x="{pad_l - 8}" y="{gy + 4:.1f}" '
            f'text-anchor="end">{val:.2f}</text>'
        )
    for vals, cls in series:
        pts = polyline(vals)
        if pts:
            parts.append(f'<polyline class="{cls}" points="{pts}"/>')
    parts.append(
        f'<text class="axis-label" x="{pad_l}" y="{height - 8}">'
        f"{rows[0]['date']}</text>"
    )
    parts.append(
        f'<text class="axis-label" x="{width - pad_r}" y="{height - 8}" '
        f'text-anchor="end">{rows[-1]["date"]}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


@app.route("/", methods=["GET"])
def index():
    conn = connect(_db_path())
    try:
        tracked = _tracked_symbols(conn)
    finally:
        conn.close()
    return render_template("index.html", tracked=tracked, error=None)


@app.route("/fetch", methods=["POST"])
def fetch_symbol():
    raw = request.form.get("ticker", "")
    if not raw.strip():
        conn = connect(_db_path())
        try:
            tracked = _tracked_symbols(conn)
        finally:
            conn.close()
        return render_template(
            "index.html",
            tracked=tracked,
            error="Enter a ticker symbol first — e.g. aapl.",
        )
    try:
        sym, _n = fetch(raw, _db_path())
    except DownloadError as e:
        conn = connect(_db_path())
        try:
            tracked = _tracked_symbols(conn)
        finally:
            conn.close()
        return render_template("index.html", tracked=tracked, error=str(e))
    return redirect(url_for("report", symbol=sym))


@app.route("/report/<symbol>", methods=["GET"])
def report(symbol):
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return "days must be a whole number", 400
    if days < 1:
        return "days must be at least 1", 400
    if days > DAYS_MAX:
        return f"days must be at most {DAYS_MAX}", 400

    conn = connect(_db_path())
    try:
        data = report_data(conn, normalize_symbol(symbol), days)
    except sqlite3.OperationalError:
        data = None  # fresh db with no table yet — same as "no data"
    finally:
        conn.close()
    if data is None:
        return (
            f"no data for {symbol} — run "
            f"`python stockpulse.py fetch {symbol}` first",
            404,
        )
    rows = data["rows"]
    table = [
        {
            "date": r["date"],
            "close": _fmt(data["closes"][i]),
            "sma20": _fmt(data["sma20"][i]),
            "sma50": _fmt(data["sma50"][i]),
            "ema12": _fmt(data["ema12"][i]),
            "rsi14": _fmt(data["rsi14"][i]),
            "macd": _fmt(data["macd"][i]),
            "macd_signal": _fmt(data["macd_signal"][i]),
            "macd_hist": _fmt(data["macd_hist"][i]),
        }
        for i, r in enumerate(rows)
    ]
    return render_template(
        "report.html",
        symbol=symbol.upper(),
        last_date=rows[-1]["date"],
        days=days,
        days_options=DAYS_OPTIONS,
        stats=_stat_cards(data),
        chart=_price_chart(rows, data["closes"], data["sma20"], data["sma50"]),
        table=table,
        notes=data["notes"],
    )


if __name__ == "__main__":
    app.run(debug=True)
