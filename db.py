"""sqlite3 storage for stockpulse."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    PRIMARY KEY (symbol, date)
);
"""

DEFAULT_DB = Path(__file__).resolve().parent / "stockpulse.db"


def connect(path=None):
    conn = sqlite3.connect(path or DEFAULT_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)


def upsert_prices(conn, symbol, rows):
    """rows: list of dicts with date/open/high/low/close/volume keys."""
    conn.executemany(
        """INSERT INTO prices (symbol, date, open, high, low, close, volume)
           VALUES (:symbol, :date, :open, :high, :low, :close, :volume)
           ON CONFLICT (symbol, date) DO UPDATE SET
               open=excluded.open, high=excluded.high, low=excluded.low,
               close=excluded.close, volume=excluded.volume""",
        [dict(r, symbol=symbol) for r in rows],
    )
    conn.commit()


def get_prices(conn, symbol, days=None):
    """Oldest -> newest. days=None returns the full history."""
    if days is None:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM prices "
            "WHERE symbol = ? ORDER BY date",
            (symbol,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM prices "
            "WHERE symbol = ? ORDER BY date DESC LIMIT ?",
            (symbol, days),
        ).fetchall()
        rows = rows[::-1]
    return [dict(r) for r in rows]
