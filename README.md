# stockpulse

A small command-line stock tracker I built to learn how technical indicators
actually work under the hood. It pulls daily OHLC data from Stooq's free CSV
endpoint, stores it in SQLite, and computes SMA, EMA, RSI, and volatility —
all in plain Python, no pandas in the math path. I implemented the formulas
by hand (Wilder's smoothing for RSI and everything) mostly as an exercise.

This is a personal learning project. It is not a trading tool and nothing
here is financial advice.

## Setup

```bash
pip install -r requirements.txt
```

Python 3.10+ should be fine.

## Usage

Download daily bars for a ticker (defaults to US listings, so `aapl` works):

```bash
python stockpulse.py fetch aapl
```

Print a report of the last 30 days with indicators:

```bash
python stockpulse.py report aapl --days 30
```

Export full history plus indicators to CSV:

```bash
python stockpulse.py export aapl --out aapl_indicators.csv
```

All data lives in `stockpulse.db` next to the script. Use `--db /path/to/file.db`
with any command to point at a different database.

## Example output

```
$ python stockpulse.py report aapl --days 5
AAPL — daily bars ending 2026-10-02
date           close   sma20   sma50   ema12   rsi14
2026-09-28    251.30  248.12  240.55  249.01   58.40
2026-09-29    253.75  248.66  240.98  249.60   61.20
2026-09-30    250.10  248.81  241.22  249.66   52.90
2026-10-01    255.40  249.33  241.71  250.40   63.80
2026-10-02    257.95  249.95  242.20  251.38   67.10

last close: 257.95
last daily return: +1.00%
20d annualized volatility: 24.31%
price is above its 50-day average (242.20)
```

(The numbers above are illustrative — run it yourself for live data.)

## How it's organized

- `stockpulse.py` — CLI entry point (argparse): `fetch`, `report`, `export`
- `downloader.py` — fetches Stooq CSV, handles HTTP errors / empty responses
- `db.py` — sqlite3 schema and helpers (upsert by symbol+date)
- `indicators.py` — sma/ema/rsi/daily_returns/volatility, all hand-rolled
- `tests/test_indicators.py` — pytest tests with hand-computed expected values

## Tests

```bash
pytest
```

## Honest notes / what's missing

- Stooq's bot protection sometimes blocks requests from datacenter/server IPs
  (you'll get a "no data" error). From a normal home connection it works fine —
  that's where I actually run this.
- `pandas` is in requirements.txt but nothing actually imports it yet — I kept
  the indicators pure-Python as the whole point of the exercise. It may earn
  its keep if I add a plotting script later.
- No split/dividend adjustment detection beyond what Stooq already does.
- Single SQLite file, no concurrency handling — fine for one person, not for
  anything shared.
- Things I'd add next: more indicators (MACD, Bollinger bands), a watchlist
  mode that refreshes a set of tickers, and simple matplotlib charts.
