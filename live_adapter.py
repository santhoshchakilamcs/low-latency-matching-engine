#!/usr/bin/env python3
"""Live price watch, second mode only. NOT trading, NOT a feed for the benchmark.

This is a public websocket price watch for Binance or Coinbase.
It prints prices and, optionally, saves them to a CSV. It places
no orders, sends no trades to the matching engine, and its timing
is never counted in the C++ engine benchmark.

- Binance: wss://stream.binance.com:9443/ws/<symbol>@trade
  (symbol lowercased, e.g. btcusdt). Public stream, no API key.
- Coinbase: wss://ws-feed.exchange.coinbase.com, subscribe to
  ticker for e.g. BTC-USD. Public stream, no API key.

Replay stays the default mode for this repo: see
yahoo_adapter.py, which turns Yahoo minute bars into synthetic
orders matched internally by the C++ engine. Live prices here
are a watch only. If you want to feed a live price into the
engine, you must generate synthetic orders around it yourself,
exactly as yahoo_adapter.py does, and label them synthetic.

Usage:
  python3 live_adapter.py --source binance --symbol BTCUSDT --count 10
  python3 live_adapter.py --source coinbase --symbol BTC-USD --count 10
  python3 live_adapter.py --source binance --symbol BTCUSDT --count 20 --out data/live_prices.csv

Requires the `websockets` package (already a Streamlit dependency
in this repo's venv). No API key is needed, and none is used.
"""
import argparse
import asyncio
import csv
import json
import sys
import time


def parse_args():
    p = argparse.ArgumentParser(description="Public websocket price watch, no trading.")
    p.add_argument("--source", choices=["binance", "coinbase"], default="binance")
    p.add_argument("--symbol", default="BTCUSDT",
                   help="Binance: BTCUSDT. Coinbase: BTC-USD.")
    p.add_argument("--count", type=int, default=10,
                   help="How many price messages to print, then stop.")
    p.add_argument("--out", default=None,
                   help="Optional CSV file for timestamp,source,symbol,price.")
    return p.parse_args()


async def run_binance(symbol, count, out):
    import websockets
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@trade"
    writer = None
    if out:
        writer = csv.writer(open(out, "w", newline=""))
        writer.writerow(["timestamp", "source", "symbol", "price"])
    seen = 0
    async with websockets.connect(url, open_timeout=15) as ws:
        async for msg in ws:
            data = json.loads(msg)
            price = data.get("p")
            if price is None:
                continue
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} binance {symbol} {price}", flush=True)
            if writer:
                writer.writerow([time.time(), "binance", symbol, price])
            seen += 1
            if seen >= count:
                break


async def run_coinbase(symbol, count, out):
    import websockets
    url = "wss://ws-feed.exchange.coinbase.com"
    writer = None
    if out:
        writer = csv.writer(open(out, "w", newline=""))
        writer.writerow(["timestamp", "source", "symbol", "price"])
    seen = 0
    async with websockets.connect(url, open_timeout=15) as ws:
        await ws.send(json.dumps({
            "type": "subscribe",
            "product_ids": [symbol],
            "channels": ["ticker"],
        }))
        async for msg in ws:
            data = json.loads(msg)
            if data.get("type") != "ticker":
                continue
            price = data.get("price")
            if price is None:
                continue
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} coinbase {symbol} {price}", flush=True)
            if writer:
                writer.writerow([time.time(), "coinbase", symbol, price])
            seen += 1
            if seen >= count:
                break


def main():
    args = parse_args()
    if args.count <= 0:
        print("count must be positive", file=sys.stderr)
        return 1
    try:
        if args.source == "binance":
            asyncio.run(run_binance(args.symbol, args.count, args.out))
        else:
            asyncio.run(run_coinbase(args.symbol, args.count, args.out))
    except ImportError:
        print("websockets is not installed: pip install websockets", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"live price watch failed (no trading was attempted): {e}", file=sys.stderr)
        return 1
    print("Live price watch done. No orders were placed, no trades were made.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
