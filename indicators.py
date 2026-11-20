"""Hand-rolled technical indicators.

Pure Python on purpose — no numpy/pandas here. The point of this module
was to learn the math by implementing it directly instead of calling a lib.

Convention: every function returns a list the same length as its input,
with None in the leading slots where there isn't enough data yet.
"""

import math
import statistics


def sma(values, n):
    """Simple moving average. First n-1 entries are None (not enough data)."""
    if n <= 0:
        raise ValueError("n must be positive")
    out = [None] * len(values)
    window_sum = 0.0
    for i, v in enumerate(values):
        window_sum += v
        if i >= n:
            window_sum -= values[i - n]
        if i >= n - 1:
            out[i] = window_sum / n
    return out


def ema(values, n):
    """Exponential moving average, seeded with the SMA of the first n values."""
    if n <= 0:
        raise ValueError("n must be positive")
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values, n=14):
    """RSI with Wilder's smoothing. Needs n+1 prices before the first value."""
    if n <= 0:
        raise ValueError("n must be positive")
    out = [None] * len(values)
    if len(values) < n + 1:
        return out

    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n

    def _rsi(g, l):
        if l == 0:
            # No losses over the window. Flat prices technically make this
            # undefined; 100 is the common convention and fine for a screener.
            return 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[n] = _rsi(avg_gain, avg_loss)
    for i in range(n + 1, len(values)):
        # Wilder's smoothing: the new bar only gets 1/n weight.
        avg_gain = (avg_gain * (n - 1) + gains[i - 1]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i - 1]) / n
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def macd(values, fast=12, slow=26, signal=9):
    """MACD line, signal line, and histogram.

    The line is fast EMA minus slow EMA; the signal is an EMA of the
    line. Returns three lists the same length as the input, None where
    there isn't enough data yet — the line starts once the slow EMA
    does, the signal `signal - 1` bars after that.
    """
    if fast <= 0 or slow <= 0 or signal <= 0:
        raise ValueError("periods must be positive")
    fast_ema, slow_ema = ema(values, fast), ema(values, slow)
    line = [None] * len(values)
    for i, (f, s) in enumerate(zip(fast_ema, slow_ema)):
        if f is not None and s is not None:
            line[i] = f - s
    compact = [v for v in line if v is not None]
    sig = [None] * len(values)
    if compact:
        # ema() seeds with the SMA of the first `signal` line values,
        # so map its output back onto the original positions
        seeded = ema(compact, signal)
        first = len(values) - len(compact)
        for j, v in enumerate(seeded):
            sig[first + j] = v
    hist = [
        (l - s) if l is not None and s is not None else None
        for l, s in zip(line, sig)
    ]
    return line, sig, hist


def daily_returns(closes):
    out = [None] * len(closes)
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        out[i] = (closes[i] - prev) / prev if prev else None
    return out


def volatility(closes, n=20, trading_days=252):
    """Annualized stddev of daily returns over the last n trading days."""
    rets = [r for r in daily_returns(closes)[-n:] if r is not None]
    if len(rets) < 2:
        return None
    return statistics.stdev(rets) * math.sqrt(trading_days)
