import argparse

import db as db_module
import downloader
import stockpulse


def _assert_clean_error(err, path):
    assert err.startswith("error: can't open database")
    assert str(path) in err
    assert "Traceback" not in err


def test_fetch_missing_db_dir_is_error(tmp_path, capsys, monkeypatch):
    # the download succeeds; only opening the db fails
    rows = [
        {"date": "2026-10-01", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    ]
    monkeypatch.setattr(downloader, "fetch_csv", lambda s: ("aapl.us", rows))
    db = tmp_path / "nope" / "test.db"
    args = argparse.Namespace(symbol="aapl", db=str(db))
    assert stockpulse.cmd_fetch(args) == 1
    _assert_clean_error(capsys.readouterr().err, db)


def test_report_missing_db_dir_is_error(tmp_path, capsys):
    db = tmp_path / "nope" / "test.db"
    args = argparse.Namespace(symbol="aapl", db=str(db), days=30)
    assert stockpulse.cmd_report(args) == 1
    _assert_clean_error(capsys.readouterr().err, db)


def test_export_missing_db_dir_is_error(tmp_path, capsys):
    db = tmp_path / "nope" / "test.db"
    out = tmp_path / "out.csv"
    args = argparse.Namespace(symbol="aapl", db=str(db), out=str(out))
    assert stockpulse.cmd_export(args) == 1
    _assert_clean_error(capsys.readouterr().err, db)
    assert not out.exists()


def test_error_names_default_db_when_no_flag(tmp_path, capsys, monkeypatch):
    default = tmp_path / "nope" / "stockpulse.db"
    monkeypatch.setattr(db_module, "DEFAULT_DB", default)
    monkeypatch.setattr(stockpulse, "DEFAULT_DB", default)
    args = argparse.Namespace(symbol="aapl", db=None, days=30)
    assert stockpulse.cmd_report(args) == 1
    _assert_clean_error(capsys.readouterr().err, default)
