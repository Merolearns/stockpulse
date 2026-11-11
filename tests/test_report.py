import argparse

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


def test_report_rejects_nonpositive_days(tmp_path, capsys):
    db = _seed(tmp_path, [100] * 30)
    for days in (0, -5):
        args = argparse.Namespace(symbol="aapl", db=db, days=days)
        assert stockpulse.cmd_report(args) == 1
        assert "--days must be at least 1" in capsys.readouterr().err


def test_report_honors_days(tmp_path, capsys):
    db = _seed(tmp_path, [100 + i for i in range(30)])
    args = argparse.Namespace(symbol="aapl", db=db, days=5)
    assert stockpulse.cmd_report(args) == 0
    out = capsys.readouterr().out
    # only the last 5 bars
    assert "2026-10-30" in out
    assert "2026-10-26" in out
    assert "2026-10-25" not in out


def test_report_writes_html(tmp_path, capsys):
    db = _seed(tmp_path, [100 + i for i in range(30)])
    out = tmp_path / "report.html"
    args = argparse.Namespace(symbol="aapl", db=db, days=5, html=str(out))
    assert stockpulse.cmd_report(args) == 0
    page = out.read_text()
    assert "AAPL" in page
    assert "2026-10-30" in page
    assert "<th>sma20</th>" in page
    assert "last close: 129.00" in page
    assert f"wrote 5 rows to {out}" in capsys.readouterr().out


def test_report_html_missing_dir(tmp_path, capsys):
    db = _seed(tmp_path, [100] * 30)
    bad = tmp_path / "nope" / "report.html"
    args = argparse.Namespace(symbol="aapl", db=db, days=5, html=str(bad))
    assert stockpulse.cmd_report(args) == 1
    err = capsys.readouterr().err
    assert f"error: can't write {bad}" in err
    assert "Traceback" not in err
