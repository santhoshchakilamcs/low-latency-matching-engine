# Low-Latency Matching Engine, with Yahoo Finance

A C++ matching engine for a trading SDE demo. Price-time priority,
limit and market orders, cancels, and an internal latency benchmark.
No live trading, no real money, no real exchange execution.

## Yahoo Finance, honestly
Yahoo Finance gives minute bars and delayed quotes for equities,
NOT tick-by-tick live exchange data. It is used here as a price
seed, not as a low-latency feed:
- `yahoo_adapter.py fetch` downloads 1-day, 1-minute AAPL bars
  with yfinance and saves them to `data/aapl_1m.csv`.
- `yahoo_adapter.py orders` turns each bar close into synthetic
  orders around that close: resting bids below, asks above, and
  alternating incoming orders that cross and create trades.
- Those synthetic orders are matched internally by our engine
  only. They are not Yahoo orders and not exchange orders.
- `yahoo_adapter.py poll` watches a delayed Yahoo quote every
  few seconds. That is a price watch, not a tick feed, and it is
  NOT used for the benchmark.

Engine latency is measured inside the C++ process, order in to
trade out, with steady_clock. Yahoo fetch time is separate and
is not counted, because Yahoo is minute-level and delayed.

## Streamlit website
`streamlit_app.py` is a browser version of the same price-time
priority engine, in Python, so you can test it without compiling
C++. It lets you fetch Yahoo 1-minute bars, run a replay, place
orders by hand, cancel orders, and see the book depth and trades.
Python demo time is milliseconds, not the C++ microseconds below.

Run locally:
```
.venv/bin/streamlit run streamlit_app.py
# open http://localhost:8501
```
Deploy as a public website, free, from GitHub:
1. Push this repo to GitHub.
2. Go to share.streamlit.io, connect the repo, pick
   `streamlit_app.py` as the main file, and Deploy.
3. Streamlit Cloud gives you a public website URL.
No AWS, no API key, and no server of your own is needed.
`requirements.txt` (streamlit, yfinance, pandas) is what
Streamlit Cloud installs.

## Build and run
```
g++ -O3 -std=c++17 -o engine src/engine.cpp
.venv/bin/python yahoo_adapter.py fetch --symbol AAPL --out data/aapl_1m.csv
.venv/bin/python yahoo_adapter.py orders --prices data/aapl_1m.csv --out data/orders.csv
./engine --orders data/orders.csv --bench
```
Order file format, one per line:
```
NEW,<id>,BUY|SELL,<price_cents>,<qty>
NEW,<id>,BUY|SELL,MARKET,<qty>
CANCEL,<id>
```
Trade output is `TRADE,<buy_id>,<sell_id>,<price_cents>,<qty>`.
Trades execute at the resting (maker) order price, which is the
standard price-time matching rule used here. Final book is
`BOOK,<best_bid>,<best_bid_qty>,<best_ask>,<best_ask_qty>`.

Unit check: buy 100 at 100.00, sell 50 at 99.50, sell 60 at 100.00
gives two trades at 100.00 (the maker price) for 50 each, and a
final book of bid empty, ask 100.00 for 10.

## Verified benchmarks, Oct 31, 2026, on this machine
Yahoo AAPL replay:
- 390 one-minute bars, Oct 30, 2026, turned into 410 synthetic orders
- 171 trades, 81 resting orders, final book 34468 bid / 34478 ask
- Latency: p50 441 ns, p99 1,963 ns, max 12,829 ns
- Throughput: 792,399 orders per second

Synthetic 100,000 random orders:
- 39,174 trades, 21,652 resting orders
- Latency: p50 460 ns, p99 1,202 ns, max 1,027,482 ns (one outlier,
  likely OS or I/O jitter, not steady-state matching)
- Throughput: 787,851 orders per second

Latency includes the trade print inside the timed section, so
these are conservative, not cherry-picked, numbers.

## Design, and its limits
- Integer cents and integer quantities, no floating point in the
  hot path.
- `std::map` price levels with a `deque` per level: highest bid
  first, lowest ask first, FIFO at a price, which is time priority.
- An id index supports cancels.
- Limits to be honest about in an interview: `std::map` is log
  time per level, not a flat array book, and there is no lock-free
  ring buffer or network layer yet. The next steps, in order,
  would be a flat array book with intrusive order lists, a
  single-producer single-consumer lock-free ring for incoming
  orders, and a binary wire protocol instead of CSV.

## Files
- `src/engine.cpp` — the matching engine, single file, C++17.
- `yahoo_adapter.py` — Yahoo fetch, synthetic order generation, quote poll.
- `data/aapl_1m.csv` — Yahoo AAPL 1-minute bars used in the verified run.
- `data/orders.csv` — synthetic orders generated from those bars.
- `streamlit_app.py` — browser version of the engine, for the website.
- `requirements.txt` — streamlit, yfinance, pandas. The C++ engine
  itself needs no Python and no API key.
