import math
import statistics

import pytest

from indicators import sma, ema, rsi, macd, daily_returns, volatility


def test_sma_basic():
    assert sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_not_enough_data():
    assert sma([1, 2], 3) == [None, None]


def test_sma_rejects_bad_period():
    with pytest.raises(ValueError):
        sma([1, 2, 3], 0)


def test_ema_seeded_with_sma():
    # k = 2/(3+1) = 0.5, seed = sma(1,2,3) = 2.0
    # ema3 = 4*0.5 + 2.0*0.5 = 3.0 ; ema4 = 5*0.5 + 3.0*0.5 = 4.0
    assert ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_rejects_bad_period():
    with pytest.raises(ValueError):
        ema([1, 2, 3], -1)


def test_rsi_known_values():
    # closes 100,102,101,103 with period 2:
    # changes: +2, -1, +2  ->  gains 2,0,2 ; losses 0,1,0
    # first:    avg_gain = 1.0, avg_loss = 0.5, RS = 2 -> 100 - 100/3
    # smoothed: avg_gain = 1.5, avg_loss = 0.25, RS = 6 -> 100 - 100/7
    got = rsi([100, 102, 101, 103], 2)
    assert got[0] is None and got[1] is None
    assert got[2] == pytest.approx(66.6667, abs=1e-3)
    assert got[3] == pytest.approx(85.7143, abs=1e-3)


def test_rsi_all_gains_is_100():
    assert rsi([1, 2, 3, 4, 5], 2)[-1] == 100.0


def test_rsi_needs_enough_prices():
    assert rsi([100, 101, 102], 5) == [None, None, None]


def test_daily_returns():
    got = daily_returns([100, 110, 99])
    assert got[0] is None
    assert got[1] == pytest.approx(0.1)
    assert got[2] == pytest.approx(-0.1)


def test_volatility_matches_manual_calc():
    closes = [100, 102, 101, 105, 103, 107, 106]
    rets = [c / p - 1 for c, p in zip(closes[1:], closes[:-1])]
    expected = statistics.stdev(rets) * math.sqrt(252)
    assert volatility(closes, n=20) == pytest.approx(expected)


def test_volatility_too_few_bars():
    assert volatility([100], n=20) is None      # no returns at all
    assert volatility([100, 101], n=20) is None  # only one return, can't stddev it


def test_macd_flat_trend():
    # straight line 1..10, fast=2 slow=3 signal=2: both EMAs lag the same
    # way, so the line is a constant 0.5 once the slow EMA starts
    line, sig, hist = macd(list(range(1, 11)), fast=2, slow=3, signal=2)
    assert line == [None, None] + [0.5] * 8
    # the signal needs `signal` line values before its first value, so it
    # starts one bar after the line
    assert sig == [None, None, None] + [0.5] * 7
    assert hist == [None, None, None] + [0.0] * 7


def test_macd_known_values():
    # closes 100,102,101,103,105,104 with fast=2 slow=3 signal=2,
    # worked out by hand from the ema() definition above
    line, sig, hist = macd([100, 102, 101, 103, 105, 104], fast=2, slow=3, signal=2)
    assert line[0] is None and line[1] is None
    assert line[2:] == pytest.approx([0.0, 0.3333, 0.6111, 0.2870], abs=1e-3)
    assert sig[:3] == [None, None, None]
    assert sig[3:] == pytest.approx([0.1667, 0.4630, 0.3457], abs=1e-3)
    assert hist[:3] == [None, None, None]
    assert hist[3:] == pytest.approx([0.1667, 0.1481, -0.0587], abs=1e-3)


def test_macd_not_enough_data():
    # fewer bars than the slow period: nothing to compute yet
    line, sig, hist = macd([100, 101, 102], fast=2, slow=5, signal=2)
    assert line == [None, None, None]
    assert sig == [None, None, None]
    assert hist == [None, None, None]


def test_macd_rejects_bad_period():
    with pytest.raises(ValueError):
        macd([1, 2, 3], fast=0, slow=3, signal=2)
    with pytest.raises(ValueError):
        macd([1, 2, 3], fast=2, slow=3, signal=-1)
