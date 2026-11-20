"""Tests for web.py — Flask test client against a seeded throwaway db."""

import os
from datetime import date, timedelta

import pytest

from db import connect, init_db, upsert_prices
from downloader import DownloadError

import web


def _seed(tmp_path, closes, symbol="aapl.us"):
    db = tmp_path / "test.db"
    conn = connect(str(db))
    init_db(conn)
    start = date(2026, 10, 1)
    rows = [
        {"date": (start + timedelta(days=i)).isoformat(), "open": c,
         "high": c + 1, "low": c - 1, "close": c, "volume": 1000}
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
    assert client.get("/report/aapl?days=366").status_code == 400
    assert client.get("/report/aapl?days=365").status_code == 200


def test_index_shows_fetch_form(client):
    html = client.get("/").get_data(as_text=True)
    assert 'action="/fetch"' in html
    assert 'name="ticker"' in html
    assert "Fetch latest bars" in html


def test_fetch_success_redirects_to_report(client, monkeypatch):
    monkeypatch.setattr(web, "fetch", lambda symbol, db: ("aapl.us", 30))
    resp = client.post("/fetch", data={"ticker": "aapl"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/report/aapl.us"


def test_fetch_empty_ticker_shows_error(client):
    resp = client.post("/fetch", data={"ticker": "   "})
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Enter a ticker symbol" in html
    assert "AAPL.US" in html  # still on the index page


def test_fetch_download_error_shows_on_index(client, monkeypatch):
    def _boom(symbol, db):
        raise DownloadError("no data for zzz.us (check the ticker)")

    monkeypatch.setattr(web, "fetch", _boom)
    resp = client.post("/fetch", data={"ticker": "zzz"})
    assert resp.status_code == 200
    assert "no data for zzz.us" in resp.get_data(as_text=True)


def test_report_page_has_chart_and_stat_cards(tmp_path, monkeypatch):
    # 60 bars so SMA50 has values to draw
    monkeypatch.setenv(
        "STOCKPULSE_DB",
        _seed(tmp_path, [100 + i for i in range(60)], symbol="aapl.us"),
    )
    web.app.config["TESTING"] = True
    # days=60 so SMA50 has values to draw (the default 30-day window
    # never has enough history for a 50-day average)
    html = web.app.test_client().get("/report/aapl?days=60").get_data(as_text=True)
    assert "<svg" in html
    assert 'class="close-line"' in html
    assert 'class="sma20-line"' in html
    assert 'class="sma50-line"' in html
    assert "Last close" in html
    assert "RSI14" in html
    assert "20d annualized volatility" in html
    assert "30d" in html and "60d" in html and "90d" in html
    # MACD columns render in the indicators table
    assert "<th>macd</th>" in html
    assert "<th>signal</th>" in html
    assert "<th>hist</th>" in html
