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
