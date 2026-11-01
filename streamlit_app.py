"""Streamlit website for the low-latency matching engine.

Run locally:
    streamlit run streamlit_app.py

Deploy as a website (free, from GitHub):
    1. Push this repo to GitHub.
    2. Go to share.streamlit.io, connect the repo, pick
       streamlit_app.py as the main file, and Deploy.
    3. Streamlit Cloud gives you a public website URL.
    No AWS, no API key, and no server of your own is needed.

What this app is, and is not:
- It is a Python version of the same price-time priority engine
  in src/engine.cpp, so you can test it in a browser.
- Yahoo Finance is a price seed only: minute bars, delayed, not
  tick data. Yahoo closes generate synthetic orders, which are
  matched internally here. No live trading, no real money, no
  real exchange execution.
- Python demo latency will be milliseconds, not the C++ engine's
  microseconds. The C++ benchmark numbers are shown separately
  and are not claimed for this Python demo.
"""
import time
from collections import deque

import streamlit as st

# ---------- Python matching engine, mirroring src/engine.cpp ----------

class Book:
    def __init__(self):
        self.bids = {}  # price_cents -> deque of (id, qty)
        self.asks = {}
        self.index = {}  # id -> (side, price)
        self.trades = []

    def add(self, oid, side, price_cents, qty, is_market=False):
        trades = []
        if side == "BUY":
            while qty > 0 and self.asks:
                ask_price = min(self.asks)
                if not is_market and ask_price > price_cents:
                    break
                q = self.asks[ask_price]
                rid, rqty = q[0]
                fill = min(qty, rqty)
                trades.append({"buy_id": oid, "sell_id": rid, "price_cents": ask_price, "qty": fill})
                qty -= fill
                rqty -= fill
                if rqty == 0:
                    q.popleft()
                    self.index.pop(rid, None)
                    if not q:
                        del self.asks[ask_price]
                else:
                    q[0] = (rid, rqty)
            if qty > 0 and not is_market:
                self.bids.setdefault(price_cents, deque()).append((oid, qty))
                self.index[oid] = ("BUY", price_cents)
        else:
            while qty > 0 and self.bids:
                bid_price = max(self.bids)
                if not is_market and bid_price < price_cents:
                    break
                q = self.bids[bid_price]
                rid, rqty = q[0]
                fill = min(qty, rqty)
                trades.append({"buy_id": rid, "sell_id": oid, "price_cents": bid_price, "qty": fill})
                qty -= fill
                rqty -= fill
                if rqty == 0:
                    q.popleft()
                    self.index.pop(rid, None)
                    if not q:
                        del self.bids[bid_price]
                else:
                    q[0] = (rid, rqty)
            if qty > 0 and not is_market:
                self.asks.setdefault(price_cents, deque()).append((oid, qty))
                self.index[oid] = ("SELL", price_cents)
        self.trades.extend(trades)
        return trades

    def cancel(self, oid):
        if oid not in self.index:
            return False
        side, price = self.index.pop(oid)
        book = self.bids if side == "BUY" else self.asks
        if price in book:
            book[price] = deque([o for o in book[price] if o[0] != oid])
            if not book[price]:
                del book[price]
        return True

    def best(self):
        bp = max(self.bids) if self.bids else None
        ap = min(self.asks) if self.asks else None
        bq = sum(q for _, q in self.bids[bp]) if bp is not None else 0
        aq = sum(q for _, q in self.asks[ap]) if ap is not None else 0
        return bp, bq, ap, aq

    def depth(self, side, n=10):
        book = self.bids if side == "BUY" else self.asks
        prices = sorted(book, reverse=(side == "BUY"))[:n]
        return [{"price": p / 100, "qty": sum(q for _, q in book[p])} for p in prices]


def orders_from_closes(closes):
    """Same synthetic order generation as yahoo_adapter.py."""
    orders = []
    oid = 1
    first = int(round(closes[0] * 100))
    for i in range(1, 11):
        orders.append((oid, "BUY", first - i * 5, 100, False)); oid += 1
        orders.append((oid, "SELL", first + i * 5, 100, False)); oid += 1
    for idx, close in enumerate(closes):
        cents = int(round(close * 100))
        side = "BUY" if idx % 2 == 0 else "SELL"
        orders.append((oid, side, cents, 50, False)); oid += 1
    return orders


# ---------- Streamlit UI ----------

st.set_page_config(page_title="Low-Latency Matching Engine", layout="wide")
st.title("Low-Latency Matching Engine")
st.write("Test the matching engine in your browser. Yahoo Finance is a price seed only: minute bars, delayed, not tick data. "
         "Yahoo closes generate synthetic orders, matched internally here. No live trading, no real money, no exchange execution.")

if "book" not in st.session_state:
    st.session_state.book = Book()
    st.session_state.next_id = 1
    st.session_state.last_trades = []

book = st.session_state.book
bp, bq, ap, aq = book.best()
st.metric("Best bid", f"${bp/100:.2f} x {bq}" if bp is not None else "none")
st.metric("Best ask", f"${ap/100:.2f} x {aq}" if ap is not None else "none")
st.metric("Resting orders", len(book.index))
st.metric("Total trades in this session", len(book.trades))

st.header("1. Yahoo Finance replay")
symbol = st.text_input("Yahoo symbol", value="AAPL")
if st.button("Fetch Yahoo 1-minute bars and run replay"):
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="1d", interval="1m")
        if hist.empty:
            st.error(f"No Yahoo data returned for {symbol}. Try again later, Yahoo rate limits are common.")
        else:
            st.write(f"Fetched {len(hist)} one-minute bars for {symbol}.")
            st.line_chart(hist["Close"])
            closes = [float(x) for x in hist["Close"].tolist()]
            orders = orders_from_closes(closes)
            t0 = time.perf_counter()
            for oid, side, price, qty, is_market in orders:
                book.add(oid, side, price, qty, is_market)
            dt_ms = (time.perf_counter() - t0) * 1000
            st.session_state.next_id = max([o[0] for o in orders], default=0) + 1
            st.success(f"Replay done: {len(orders)} synthetic orders, {len(book.trades)} total trades in session, "
                       f"in {dt_ms:.1f} ms in this Python demo. "
                       f"This is Python demo time, not the C++ engine time below.")
    except Exception as e:
        st.error(f"Yahoo fetch failed: {e}")

st.header("2. Place an order by hand")
col1, col2, col3, col4 = st.columns(4)
with col1:
    side = st.selectbox("Side", ["BUY", "SELL"])
with col2:
    is_market = st.checkbox("Market order", value=False)
with col3:
    price_dollars = st.number_input("Limit price ($)", min_value=0.0, value=100.00, step=0.01, disabled=is_market)
with col4:
    qty = st.number_input("Quantity", min_value=1, value=50, step=1)
if st.button("Place order"):
    oid = st.session_state.next_id
    st.session_state.next_id += 1
    price_cents = 0 if is_market else int(round(price_dollars * 100))
    trades = book.add(oid, side, price_cents, qty, is_market)
    st.session_state.last_trades = trades
    if trades:
        st.write(f"Order {oid} created {len(trades)} trade(s):")
        st.table(trades)
    else:
        st.write(f"Order {oid} is resting in the book, no trade yet.")

cancel_id = st.number_input("Cancel order id", min_value=1, value=1, step=1)
if st.button("Cancel order"):
    if book.cancel(int(cancel_id)):
        st.success(f"Cancelled order {int(cancel_id)}.")
    else:
        st.warning(f"Order {int(cancel_id)} not found in the book.")
if st.button("Reset book"):
    st.session_state.book = Book()
    st.session_state.next_id = 1
    st.rerun()

st.header("3. Order book depth")
col_b, col_a = st.columns(2)
with col_b:
    st.subheader("Bids")
    st.table(book.depth("BUY"))
with col_a:
    st.subheader("Asks")
    st.table(book.depth("SELL"))

st.header("4. Trades")
if book.trades:
    st.table([{"buy_id": t["buy_id"], "sell_id": t["sell_id"], "price": t["price_cents"] / 100, "qty": t["qty"]} for t in book.trades[-100:]])
else:
    st.write("No trades yet. Run a Yahoo replay or place an order that crosses the book.")

st.header("5. C++ engine benchmark, for reference")
st.write("These are the verified C++ numbers from Oct 31, 2026, not Python demo numbers:")
st.write("- Yahoo AAPL replay: 410 synthetic orders, 171 trades, p50 441 ns, p99 1,963 ns, 792,399 orders per second")
st.write("- Synthetic 100,000 orders: 39,174 trades, p50 460 ns, p99 1,202 ns, 787,851 orders per second")
st.write("Deploy this website from GitHub with Streamlit Cloud: push the repo, go to share.streamlit.io, "
         "connect the repo, pick streamlit_app.py, and Deploy. Streamlit Cloud will give you a public URL.")
