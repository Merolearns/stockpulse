import argparse
import csv

from db import connect, init_db, upsert_prices

import stockpulse


def _seed(tmp_path, closes, symbol="aapl.us"):
    db = tmp_path / "test.db"
    conn = connect(str(db))
    init_db(conn)
    rows = [
        {"date": f"2026-10-{i + 1:02d}", "open": c, "high": c + 1,
         "low": c - 1, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ]
    upsert_prices(conn, symbol, rows)
    conn.close()
    return str(db)


def test_export_keeps_real_zero_rsi(tmp_path):
    # 20 straight down-days -> rsi14 is genuinely 0.0; the old
    # `or ""` fallback used to export it as an empty cell
    closes = [120 - i for i in range(20)]
    db = _seed(tmp_path, closes)
    out = tmp_path / "out.csv"
    args = argparse.Namespace(symbol="aapl", db=db, out=str(out))
    assert stockpulse.cmd_export(args) == 0

    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert rows[-1]["rsi14"] == "0.0"
    # indicators without enough data are still empty cells
    assert rows[0]["sma50"] == ""
    assert rows[0]["rsi14"] == ""


def test_export_no_data_is_error(tmp_path, capsys):
    db = _seed(tmp_path, [])
    out = tmp_path / "out.csv"
    args = argparse.Namespace(symbol="aapl", db=db, out=str(out))
    assert stockpulse.cmd_export(args) == 1
    assert "no data for aapl" in capsys.readouterr().out


def test_export_unwritable_out_is_error(tmp_path, capsys):
    # --out inside a directory that doesn't exist used to die with
    # a bare traceback instead of a clean error
    db = _seed(tmp_path, [100, 101, 102])
    out = tmp_path / "nope" / "out.csv"
    args = argparse.Namespace(symbol="aapl", db=db, out=str(out))
    assert stockpulse.cmd_export(args) == 1
    err = capsys.readouterr().err
    assert "can't write" in err and "out.csv" in err
