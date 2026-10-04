"""Download daily OHLC bars from Stooq's free CSV endpoint."""

import csv

import requests

from db import connect, init_db, upsert_prices

STOOQ_URL = "https://stooq.com/q/d/l/"
TIMEOUT = 20
HEADERS = {
    "User-Agent": "stockpulse/0.1 (+personal learning project)",
    "Accept": "text/csv,text/plain,*/*",
}


class DownloadError(Exception):
    pass


def normalize_symbol(symbol):
    s = symbol.strip().lower()
    if "." not in s:
        s += ".us"  # default to US listings
    return s


def fetch_csv(symbol):
    """Download raw daily bars. Returns (symbol, rows), oldest first."""
    sym = normalize_symbol(symbol)
    try:
        resp = requests.get(STOOQ_URL, params={"s": sym, "i": "d"},
                            headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise DownloadError(f"couldn't download {sym}: {e}") from e

    text = resp.text.strip()
    if text.startswith("Exceeded"):
        raise DownloadError("stooq rate limit hit — wait a bit and retry")
    if not text or text.startswith("<"):
        # Stooq sometimes answers bots with an HTML challenge/404 page
        # instead of CSV. Nothing wrong with the request itself.
        raise DownloadError(f"no data for {sym} (check the ticker)")

    # TODO: handle stock splits. Stooq adjusts history so usually this is
    # fine, but a huge overnight gap vs the previous close means a split
    # (or a bad tick) — worth flagging instead of silently swallowing.
    rows = []
    reader = csv.DictReader(text.splitlines())
    for row in reader:
        try:
            rows.append({
                "date": row["Date"],
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(float(row["Volume"])),
            })
        except (KeyError, ValueError):
            continue  # skip malformed rows rather than dying on one bad line
    if not rows:
        raise DownloadError(f"no usable rows for {sym}")
    return sym, rows


def fetch(symbol, db_path=None):
    """Download daily bars and store them. Returns (symbol, row count)."""
    sym, rows = fetch_csv(symbol)
    conn = connect(db_path)
    init_db(conn)
    upsert_prices(conn, sym, rows)
    conn.close()
    return sym, len(rows)
