#!/usr/bin/env python3
"""stockpulse — a small CLI for tracking daily stock prices."""

import argparse
import csv
import html
import sqlite3
import sys

from db import DEFAULT_DB, connect, get_prices
from downloader import fetch, DownloadError, normalize_symbol
from indicators import sma, ema, rsi, macd, daily_returns, volatility


def _db_error(path, e):
    print(f"error: can't open database {path or DEFAULT_DB}: {e}", file=sys.stderr)
    return 1


def cmd_fetch(args):
    try:
        sym, n = fetch(args.symbol, args.db)
    except DownloadError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except sqlite3.OperationalError as e:
        return _db_error(args.db, e)
    print(f"{sym}: stored {n} daily bars")
    return 0


def _fmt(v, width=8):
    return f"{v:>{width}.2f}" if v is not None else " " * width


def report_data(conn, symbol, days):
    """Indicator report for a symbol, or None when the db has no bars for it.

    Returns the rows, the per-bar indicator columns, and the plain-English
    summary notes — the same numbers cmd_report prints and _html_report
    renders, computed once here so both stay in sync.
    """
    rows = get_prices(conn, symbol, days=days)
    if not rows:
        return None

    closes = [r["close"] for r in rows]
    s20, s50 = sma(closes, 20), sma(closes, 50)
    e12 = ema(closes, 12)
    r14 = rsi(closes, 14)
    m_line, m_sig, m_hist = macd(closes)

    rets = daily_returns(closes)
    vol = volatility(closes, 20)

    notes = [f"last close: {closes[-1]:.2f}"]
    if rets[-1] is not None:
        notes.append(f"last daily return: {rets[-1]:+.2%}")
    if vol is not None:
        notes.append(f"20d annualized volatility: {vol:.2%}")
    if s50[-1] is not None:
        trend = "above" if closes[-1] > s50[-1] else "below"
        notes.append(f"price is {trend} its 50-day average ({s50[-1]:.2f})")
    if r14[-1] is not None:
        if r14[-1] > 70:
            notes.append(f"rsi14 at {r14[-1]:.1f} — overbought territory")
        elif r14[-1] < 30:
            notes.append(f"rsi14 at {r14[-1]:.1f} — oversold territory")
    if m_hist[-1] is not None:
        # histogram above zero means the MACD line sits above its signal
        notes.append(f"macd histogram at {m_hist[-1]:+.2f}")

    return {
        "symbol": symbol,
        "rows": rows,
        "closes": closes,
        "sma20": s20,
        "sma50": s50,
        "ema12": e12,
        "rsi14": r14,
        "macd": m_line,
        "macd_signal": m_sig,
        "macd_hist": m_hist,
        "notes": notes,
    }


def cmd_report(args):
    if args.days < 1:
        # sqlite treats a negative LIMIT as "no limit", so without this
        # --days 0/-5 silently prints the whole history (or "no data")
        print("error: --days must be at least 1", file=sys.stderr)
        return 1
    sym = normalize_symbol(args.symbol)
    try:
        conn = connect(args.db)
    except sqlite3.OperationalError as e:
        return _db_error(args.db, e)
    data = report_data(conn, sym, args.days)
    conn.close()
    if data is None:
        print(f"no data for {args.symbol} — run `fetch {args.symbol}` first")
        return 1

    rows = data["rows"]
    print(f"{args.symbol.upper()} — daily bars ending {rows[-1]['date']}")
    print(f"{'date':<12}{'close':>8}{'sma20':>8}{'sma50':>8}{'ema12':>8}{'rsi14':>8}")
    for i, r in enumerate(rows):
        print(
            f"{r['date']:<12}"
            f"{_fmt(data['closes'][i])}{_fmt(data['sma20'][i])}{_fmt(data['sma50'][i])}"
            f"{_fmt(data['ema12'][i])}{_fmt(data['rsi14'][i])}"
        )

    print()
    print("\n".join(data["notes"]))

    out = getattr(args, "html", None)  # older callers build Namespaces without it
    if out:
        try:
            f = open(out, "w", encoding="utf-8")
        except OSError as e:
            print(f"error: can't write {out}: {e.strerror or e}", file=sys.stderr)
            return 1
        with f:
            f.write(
                _html_report(
                    args.symbol.upper(),
                    rows,
                    [data["closes"], data["sma20"], data["sma50"],
                     data["ema12"], data["rsi14"]],
                    data["notes"],
                )
            )
        print(f"wrote {len(rows)} rows to {out}")
    return 0


_CSS = """body{font-family:system-ui,sans-serif;margin:2rem;color:#222}
table{border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{padding:.25rem .75rem;text-align:right;border-bottom:1px solid #ddd}
th:first-child,td:first-child{text-align:left}"""


def _html_report(symbol, rows, cols, notes):
    sym = html.escape(symbol)
    head = "".join(
        f"<th>{h}</th>" for h in ("date", "close", "sma20", "sma50", "ema12", "rsi14")
    )
    body = "\n".join(
        f"<tr><td>{html.escape(r['date'])}</td>"
        + "".join(f"<td>{_fmt(c[i]).strip()}</td>" for c in cols)
        + "</tr>"
        for i, r in enumerate(rows)
    )
    items = "".join(f"<li>{html.escape(n)}</li>" for n in notes)
    return (
        '<!doctype html>\n<html><head><meta charset="utf-8">'
        f"<title>{sym} report</title><style>{_CSS}</style></head><body>\n"
        f"<h1>{sym} — daily bars ending {html.escape(rows[-1]['date'])}</h1>\n"
        f"<table><thead><tr>{head}</tr></thead><tbody>\n{body}\n</tbody></table>\n"
        f"<ul>{items}</ul>\n</body></html>\n"
    )


def _cell(v):
    # only None (not enough data) becomes an empty cell — a real 0.0,
    # like rsi14 after a sustained slide, must survive as 0.0
    return "" if v is None else v


def cmd_export(args):
    sym = normalize_symbol(args.symbol)
    try:
        conn = connect(args.db)
    except sqlite3.OperationalError as e:
        return _db_error(args.db, e)
    rows = get_prices(conn, sym)
    conn.close()
    if not rows:
        print(f"no data for {args.symbol} — run `fetch {args.symbol}` first")
        return 1

    closes = [r["close"] for r in rows]
    s20, s50 = sma(closes, 20), sma(closes, 50)
    e12 = ema(closes, 12)
    r14 = rsi(closes, 14)
    m_line, m_sig, m_hist = macd(closes)

    try:
        f = open(args.out, "w", newline="")
    except OSError as e:
        # a missing parent dir used to die with a bare traceback
        print(f"error: can't write {args.out}: {e.strerror or e}", file=sys.stderr)
        return 1
    with f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume",
                    "sma20", "sma50", "ema12", "rsi14",
                    "macd", "macd_signal", "macd_hist"])
        for i, r in enumerate(rows):
            w.writerow([r["date"], r["open"], r["high"], r["low"],
                        r["close"], r["volume"],
                        _cell(s20[i]), _cell(s50[i]),
                        _cell(e12[i]), _cell(r14[i]),
                        _cell(m_line[i]), _cell(m_sig[i]), _cell(m_hist[i])])
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="track daily stock prices")
    p.add_argument("--db", default=None, help="sqlite db path (default: ./stockpulse.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # --db is repeated on each subcommand (with SUPPRESS so it doesn't
    # clobber the global one) because I always type it after the subcommand.
    f = sub.add_parser("fetch", help="download daily bars from stooq")
    f.add_argument("--db", default=argparse.SUPPRESS)
    f.add_argument("symbol", help="ticker, e.g. aapl or aapl.us")
    f.set_defaults(func=cmd_fetch)

    r = sub.add_parser("report", help="print an indicator report")
    r.add_argument("--db", default=argparse.SUPPRESS)
    r.add_argument("symbol")
    r.add_argument("--days", type=int, default=30, help="days to show (default 30)")
    r.add_argument(
        "--html", metavar="PATH", help="also write a self-contained html report to PATH"
    )
    r.set_defaults(func=cmd_report)

    e = sub.add_parser("export", help="export bars + indicators to csv")
    e.add_argument("--db", default=argparse.SUPPRESS)
    e.add_argument("symbol")
    e.add_argument("--out", required=True, help="output csv path")
    e.set_defaults(func=cmd_export)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
