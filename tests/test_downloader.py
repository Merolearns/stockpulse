import pytest

from downloader import normalize_symbol, find_suspicious_gaps


def _rows(*closes):
    return [
        {"date": f"2026-10-{i + 1:02d}", "close": c, "open": c,
         "high": c, "low": c, "volume": 1000}
        for i, c in enumerate(closes)
    ]


def test_normalize_symbol_defaults_to_us():
    assert normalize_symbol("AAPL") == "aapl.us"
    assert normalize_symbol(" aapl.us ") == "aapl.us"
    assert normalize_symbol("7203.t") == "7203.t"


def test_no_gaps_for_normal_data():
    assert find_suspicious_gaps(_rows(100, 101, 99, 100.5)) == []


def test_flags_split_like_gap():
    # a 4-for-1 split shows up as a ~75% overnight drop
    gaps = find_suspicious_gaps(_rows(100, 99, 25))
    assert len(gaps) == 1
    date, prev_close, close = gaps[0]
    assert date == "2026-10-03"
    assert (prev_close, close) == (99, 25)


def test_flags_suspicious_jump_too():
    gaps = find_suspicious_gaps(_rows(10, 10, 21))
    assert len(gaps) == 1
    assert gaps[0] == ("2026-10-03", 10, 21)


def test_small_moves_not_flagged():
    assert find_suspicious_gaps(_rows(100, 90, 84)) == []  # 10% then ~7%


def test_threshold_is_configurable():
    assert find_suspicious_gaps(_rows(100, 120), threshold=0.1) == [
        ("2026-10-02", 100, 120)
    ]


def test_zero_close_skipped_not_crash():
    assert find_suspicious_gaps(_rows(0, 100)) == []
    assert find_suspicious_gaps(_rows(100, 0)) == []


def test_fetch_csv_returns_oldest_first(monkeypatch):
    # Stooq serves newest first — fetch_csv promises oldest first, and
    # the split warning names the wrong date if the order isn't flipped
    import downloader

    stooq_csv = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-10-03,25,25,25,25,1000\n"
        "2026-10-02,99,99,99,99,1000\n"
        "2026-10-01,100,100,100,100,1000\n"
    )

    class FakeResp:
        text = stooq_csv

        def raise_for_status(self):
            pass

    monkeypatch.setattr(downloader.requests, "get", lambda *a, **k: FakeResp())
    with pytest.warns(UserWarning, match="2026-10-03 closed at 25.00 after 99.00"):
        sym, rows = downloader.fetch_csv("aapl")
    assert sym == "aapl.us"
    assert [r["date"] for r in rows] == ["2026-10-01", "2026-10-02", "2026-10-03"]
