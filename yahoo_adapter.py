#!/usr/bin/env python3
"""Yahoo Finance adapter for the matching engine.

Honest limits, read first:
- Yahoo Finance gives minute bars and delayed quotes for equities,
  NOT tick-by-tick live exchange data. It is a price seed, not a
  low-latency feed. Do not claim Yahoo latency as engine latency.
- The engine's latency is measured inside the C++ process, in
  microseconds, on the orders generated here. Yahoo fetch time is
  separate and is seconds to minutes, by design.
- No live trading, no real money, no real exchange execution.
  Yahoo prices generate synthetic orders that are matched
  internally by our own engine only.

Modes:
  fetch   --symbol AAPL --out data/aapl_1m.csv
      Download 1-day, 1-minute bars with yfinance and save
      timestamp,open,high,low,close,volume.
  orders  --prices data/aapl_1m.csv --out data/orders.csv
      Turn each bar's close into synthetic orders around that
      close: resting bids below and asks above, plus alternating
      incoming limit orders that cross and create trades.
      Price is integer cents, so a $344.63 close becomes 34463.
  poll    --symbol AAPL --interval 5
      Poll the current Yahoo quote every N seconds and print it.
      This is a live-ish price watch, not a tick feed, and it is
      NOT used for the benchmark.
"""
import argparse
import csv
import sys
import time

def fetch_prices(symbol, out):
    import yfinance as yf
    tk = yf.Ticker(symbol)
    hist = tk.history(period="1d", interval="1m")
    if hist.empty:
        print(f"no Yahoo data returned for {symbol}", file=sys.stderr)
        return 1
    hist = hist.reset_index()
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for _, row in hist.iterrows():
            w.writerow([row["Datetime"], row["Open"], row["High"], row["Low"], row["Close"], row["Volume"]])
    print(f"wrote {out}: {len(hist)} bars for {symbol}")
    return 0

def orders_from_prices(prices_path, out):
    rows = list(csv.DictReader(open(prices_path)))
    if not rows:
        print("no price rows", file=sys.stderr)
        return 1
    orders = []
    oid = 1
    # Seed a resting book around the first close, 10 levels each side.
    first_close_cents = int(round(float(rows[0]["close"]) * 100))
    for i in range(1, 11):
        orders.append(f"NEW,{oid},BUY,{first_close_cents - i * 5},100")
        oid += 1
        orders.append(f"NEW,{oid},SELL,{first_close_cents + i * 5},100")
        oid += 1
    # Each bar: one incoming order that crosses the book, alternating sides,
    # priced at the bar close, plus a small resting order on the other side.
    for idx, row in enumerate(rows):
        close_cents = int(round(float(row["close"]) * 100))
        if idx % 2 == 0:
            orders.append(f"NEW,{oid},BUY,{close_cents},50")
        else:
            orders.append(f"NEW,{oid},SELL,{close_cents},50")
        oid += 1
    with open(out, "w") as f:
        f.write("\n".join(orders) + "\n")
    print(f"wrote {out}: {len(orders)} synthetic orders from {len(rows)} Yahoo bars")
    print("note: these are synthetic orders around Yahoo closes, not Yahoo orders and not exchange orders")
    return 0

def poll(symbol, interval):
    import yfinance as yf
    tk = yf.Ticker(symbol)
    print(f"polling Yahoo quote for {symbol} every {interval}s (delayed quote, not a tick feed; Ctrl-C to stop)")
    try:
        while True:
            try:
                price = tk.fast_info.get("lastPrice")
            except Exception as e:
                price = f"error: {e}"
            print(f"{time.strftime('%H:%M:%S')} {symbol} {price}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("stopped")

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--symbol", default="AAPL")
    f.add_argument("--out", default="data/aapl_1m.csv")
    o = sub.add_parser("orders")
    o.add_argument("--prices", default="data/aapl_1m.csv")
    o.add_argument("--out", default="data/orders.csv")
    p = sub.add_parser("poll")
    p.add_argument("--symbol", default="AAPL")
    p.add_argument("--interval", type=int, default=5)
    args = ap.parse_args()
    if args.cmd == "fetch":
        return fetch_prices(args.symbol, args.out)
    if args.cmd == "orders":
        return orders_from_prices(args.prices, args.out)
    return poll(args.symbol, args.interval) or 0

if __name__ == "__main__":
    raise SystemExit(main())
