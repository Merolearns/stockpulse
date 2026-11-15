"""Tests for web.py — Flask test client against a seeded throwaway db."""

import os

import pytest

from db import connect, init_db, upsert_prices

import web


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


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKPULSE_DB", _seed(tmp_path, [100 + i for i in range(30)]))
    web.app.config["TESTING"] = True
    return web.app.test_client()


def test_index_lists_tracked_symbol(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "AAPL.US" in html
    assert "30" in html  # bars stored
    assert "2026-10-30" in html  # last bar
    assert "129.00" in html  # last close
    assert "/report/aapl.us" in html


def test_index_empty_db_says_nothing_tracked(tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKPULSE_DB", str(tmp_path / "empty.db"))
    web.app.config["TESTING"] = True
    resp = web.app.test_client().get("/")
    assert resp.status_code == 200
    assert "No symbols tracked yet" in resp.get_data(as_text=True)


def test_report_page_matches_cli_numbers(client):
    resp = client.get("/report/aapl")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "AAPL" in html
    assert "2026-10-30" in html
    assert "<th>sma20</th>" in html
    assert "last close: 129.00" in html


def test_report_honors_days(client):
    html = client.get("/report/aapl?days=5").get_data(as_text=True)
    assert "2026-10-30" in html
    assert "2026-10-26" in html
    assert "2026-10-25" not in html


def test_report_unknown_symbol_404(client):
    resp = client.get("/report/msft")
    assert resp.status_code == 404
    assert "no data for msft" in resp.get_data(as_text=True)


def test_report_bad_days_400(client):
    assert client.get("/report/aapl?days=0").status_code == 400
    assert client.get("/report/aapl?days=abc").status_code == 400
