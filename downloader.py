"""Download daily OHLC bars from Stooq's free CSV endpoint."""

import csv
import warnings

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


SPLIT_GAP_THRESHOLD = 0.5  # an overnight move bigger than this smells like a split


def find_suspicious_gaps(rows, threshold=SPLIT_GAP_THRESHOLD):
    """Return (date, prev_close, close) for overnight moves bigger than
    `threshold`. Stooq adjusts history for splits, so these are rare —
    usually a split that slipped through, or a bad tick. `rows` must be
    oldest first."""
    gaps = []
    prev = None
    for row in rows:
        close = row["close"]
        if prev and close:  # skip zeros to avoid dividing by zero
            if abs(close - prev) / prev > threshold:
                gaps.append((row["date"], prev, close))
        prev = close
    return gaps


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
    for date, prev_close, close in find_suspicious_gaps(rows):
        warnings.warn(
            f"{sym}: {date} closed at {close:.2f} after {prev_close:.2f} "
            "— possible stock split or bad tick",
            stacklevel=2,
        )
    return sym, rows


def fetch(symbol, db_path=None):
    """Download daily bars and store them. Returns (symbol, row count)."""
    sym, rows = fetch_csv(symbol)
    conn = connect(db_path)
    init_db(conn)
    upsert_prices(conn, sym, rows)
    conn.close()
    return sym, len(rows)
