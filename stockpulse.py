#!/usr/bin/env python3
"""stockpulse — a small CLI for tracking daily stock prices."""

import argparse
import csv
import sqlite3
import sys

from db import DEFAULT_DB, connect, get_prices
from downloader import fetch, DownloadError, normalize_symbol
from indicators import sma, ema, rsi, daily_returns, volatility


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
    rows = get_prices(conn, sym, days=args.days)
    conn.close()
    if not rows:
        print(f"no data for {args.symbol} — run `fetch {args.symbol}` first")
        return 1

    closes = [r["close"] for r in rows]
    s20, s50 = sma(closes, 20), sma(closes, 50)
    e12 = ema(closes, 12)
    r14 = rsi(closes, 14)

    print(f"{args.symbol.upper()} — daily bars ending {rows[-1]['date']}")
    print(f"{'date':<12}{'close':>8}{'sma20':>8}{'sma50':>8}{'ema12':>8}{'rsi14':>8}")
    for i, r in enumerate(rows):
        print(
            f"{r['date']:<12}"
            f"{_fmt(closes[i])}{_fmt(s20[i])}{_fmt(s50[i])}"
            f"{_fmt(e12[i])}{_fmt(r14[i])}"
        )

    rets = daily_returns(closes)
    vol = volatility(closes, 20)

    print()
    print(f"last close: {closes[-1]:.2f}")
    if rets[-1] is not None:
        print(f"last daily return: {rets[-1]:+.2%}")
    if vol is not None:
        print(f"20d annualized volatility: {vol:.2%}")
    if s50[-1] is not None:
        trend = "above" if closes[-1] > s50[-1] else "below"
        print(f"price is {trend} its 50-day average ({s50[-1]:.2f})")
    if r14[-1] is not None:
        if r14[-1] > 70:
            print(f"rsi14 at {r14[-1]:.1f} — overbought territory")
        elif r14[-1] < 30:
            print(f"rsi14 at {r14[-1]:.1f} — oversold territory")
    return 0


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

    try:
        f = open(args.out, "w", newline="")
    except OSError as e:
        # a missing parent dir used to die with a bare traceback
        print(f"error: can't write {args.out}: {e.strerror or e}", file=sys.stderr)
        return 1
    with f:
        w = csv.writer(f)
        w.writerow(["date", "open", "high", "low", "close", "volume",
                    "sma20", "sma50", "ema12", "rsi14"])
        for i, r in enumerate(rows):
            w.writerow([r["date"], r["open"], r["high"], r["low"],
                        r["close"], r["volume"],
                        _cell(s20[i]), _cell(s50[i]),
                        _cell(e12[i]), _cell(r14[i])])
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
