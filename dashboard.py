import streamlit as st
import yfinance as yf
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, MACD
import subprocess
import json

# =========================
# ✅ Page Config
# =========================
st.set_page_config(page_title="Trading Bot Dashboard", layout="centered")

st.title("🤖 Trading Bot Dashboard")

symbol = "AAPL"

# =========================
# 🧠 Session State
# =========================
if "bot_process" not in st.session_state:
    st.session_state.bot_process = None

# =========================
# 📊 Position Fetch (IMPROVED)
# =========================
def get_position_info():
    try:
        import alpaca_trade_api as tradeapi
        from config import API_KEY, SECRET_KEY, BASE_URL

        client = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)
        position = client.get_position(symbol)

        return {
            "entry_price": float(position.avg_entry_price),
            "qty": float(position.qty),
            "current_price": float(position.current_price),
            "unrealized_pl": float(position.unrealized_pl),
            "unrealized_plpc": float(position.unrealized_plpc) * 100
        }

    except Exception:
        return None


# =========================
# 📊 Market Data
# =========================
def get_data():
    df = yf.download(symbol, interval="1m", period="1d")

    if df.empty:
        st.error("No data received from Yahoo Finance")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    df.columns = [str(col).lower() for col in df.columns]

    return df


def calculate_indicators(data):
    data['rsi'] = RSIIndicator(close=data['close'], window=14).rsi()
    data['ma_short'] = SMAIndicator(close=data['close'], window=9).sma_indicator()
    data['ma_long'] = SMAIndicator(close=data['close'], window=21).sma_indicator()

    macd = MACD(close=data['close'])
    data['macd'] = macd.macd()
    data['macd_signal'] = macd.macd_signal()

    return data


# =========================
# ⚙️ Risk Management
# =========================
st.subheader("⚙️ Risk Management")

stop_loss_percent = st.slider("Stop Loss (%)", 1, 20, 5)
take_profit_percent = st.slider("Take Profit (%)", 1, 20, 6)

config_data = {
    "stop_loss": stop_loss_percent / 100,
    "take_profit": take_profit_percent / 100
}

with open("settings.json", "w") as f:
    json.dump(config_data, f)


# =========================
# 🤖 Bot Controls
# =========================
st.subheader("🤖 Bot Controls")

col1, col2 = st.columns(2)

with col1:
    if st.button("▶️ Run Trading Bot"):
        if st.session_state.bot_process is None:
            process = subprocess.Popen(["python", "bot.py"])
            st.session_state.bot_process = process
            st.success("Bot started 🚀")
        else:
            st.warning("Bot already running")

with col2:
    if st.button("🛑 Stop Trading Bot"):
        if st.session_state.bot_process is not None:
            st.session_state.bot_process.terminate()
            st.session_state.bot_process = None
            st.success("Bot stopped 🛑")
        else:
            st.warning("Bot is not running")

# =========================
# 🟢 Bot Status
# =========================
if st.session_state.bot_process is not None:
    st.success("🟢 Bot Running")
else:
    st.error("🔴 Bot Stopped")


# =========================
# 📈 Dashboard Data
# =========================
data = get_data()

if data is not None:
    data = calculate_indicators(data)

    latest = data.iloc[-1]
    price = latest['close']
    rsi = latest['rsi']

    # 🔹 Market Metrics
    st.subheader("📊 Market Overview")

    col1, col2 = st.columns(2)
    col1.metric("💰 Price", f"${price:.2f}")
    col2.metric("📊 RSI", f"{rsi:.2f}")

    # 🔹 Signal
    if rsi < 30:
        st.success("🟢 BUY SIGNAL")
    elif rsi > 70:
        st.error("🔴 SELL SIGNAL")
    else:
        st.warning("🟡 HOLD")

    # =========================
    # 📦 Position Section
    # =========================
    st.subheader("📦 Position Status")

    position = get_position_info()

    if position:
        entry_price = position["entry_price"]
        qty = position["qty"]
        current_price = position["current_price"]
        pnl = position["unrealized_pl"]
        pnl_percent = position["unrealized_plpc"]

        st.success("📦 Holding Position")

        col1, col2 = st.columns(2)

        with col1:
            st.metric("📍 Entry Price", f"${entry_price:.2f}")
            st.metric("📊 Quantity", f"{qty}")

        with col2:
            st.metric("💰 Current Price", f"${current_price:.2f}")

            if pnl >= 0:
                st.success(f"💵 Profit: ${pnl:.2f} (+{pnl_percent:.2f}%)")
            else:
                st.error(f"💵 Loss: ${pnl:.2f} ({pnl_percent:.2f}%)")

    else:
        st.warning("💰 No active position")

    # =========================
    # 📉 Chart
    # =========================
    try:
        if 'datetime' in data.columns:
            data = data.set_index('datetime')
        elif 'date' in data.columns:
            data = data.set_index('date')

        st.line_chart(data['close'])

    except Exception as e:
        st.error(f"Chart error: {e}")


# =========================
# 🔄 Refresh
# =========================
if st.button("🔄 Refresh"):
    st.rerun()