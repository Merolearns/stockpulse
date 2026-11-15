"""stockpulse web dashboard: browse tracked symbols and their indicator
reports in the browser instead of the terminal.

Same data and math as the CLI — the report page reuses stockpulse's
_html_report, so the numbers never drift from `report aapl --html`.

Run with: python web.py  (then open http://127.0.0.1:5000)
"""

import os
import sqlite3

from flask import Flask, request

from db import DEFAULT_DB, connect, get_prices
from downloader import normalize_symbol
from stockpulse import _html_report, report_data

app = Flask(__name__)


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


_INDEX_CSS = """body{font-family:system-ui,sans-serif;margin:2rem;color:#222}
table{border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:.25rem .75rem;text-align:right;border-bottom:1px solid #ddd}
th:first-child,td:first-child{text-align:left}
a{color:#2b5fab}
p.hint{color:#666}"""


def _index_page(tracked):
    if not tracked:
        body = (
            "<p>No symbols tracked yet.</p>"
            "<p class='hint'>Run <code>python stockpulse.py fetch aapl</code> "
            "to add one, then reload this page.</p>"
        )
    else:
        rows = "\n".join(
            f"<tr><td><a href='/report/{t['symbol']}'>{t['symbol'].upper()}</a></td>"
            f"<td>{t['bars']}</td><td>{t['last_date']}</td>"
            f"<td>{t['last_close']:.2f}</td></tr>"
            for t in tracked
        )
        body = (
            "<table><thead><tr><th>symbol</th><th>bars</th>"
            "<th>last bar</th><th>last close</th></tr></thead>"
            f"<tbody>\n{rows}\n</tbody></table>"
            "<p class='hint'>Click a symbol for its indicator report. "
            "Add more with <code>python stockpulse.py fetch &lt;symbol&gt;</code>.</p>"
        )
    return (
        "<!doctype html>\n<html><head><meta charset='utf-8'>"
        f"<title>stockpulse</title><style>{_INDEX_CSS}</style></head><body>\n"
        f"<h1>stockpulse</h1>\n{body}\n</body></html>\n"
    )


@app.route("/", methods=["GET"])
def index():
    conn = connect(_db_path())
    try:
        tracked = _tracked_symbols(conn)
    finally:
        conn.close()
    return _index_page(tracked)


@app.route("/report/<symbol>", methods=["GET"])
def report(symbol):
    try:
        days = int(request.args.get("days", 30))
    except ValueError:
        return "days must be a whole number", 400
    if days < 1:
        return "days must be at least 1", 400

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
    return _html_report(
        symbol.upper(),
        data["rows"],
        [data["closes"], data["sma20"], data["sma50"],
         data["ema12"], data["rsi14"]],
        data["notes"],
    )


if __name__ == "__main__":
    app.run(debug=True)
