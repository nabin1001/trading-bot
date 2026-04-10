import schedule
import time
import yfinance as yf
import pandas as pd
from ta.momentum import RSIIndicator
import alpaca_trade_api as tradeapi
from config import API_KEY, SECRET_KEY, BASE_URL
import json

# =========================
# ⚙️ SETTINGS
# =========================
symbol = "AAPL"
last_trade_time = 0
TRADE_COOLDOWN = 60  # seconds

# =========================
# 📥 LOAD UI SETTINGS
# =========================
def load_settings():
    try:
        with open("settings.json", "r") as f:
            return json.load(f)
    except:
        return {"stop_loss": 0.05}

settings = load_settings()
STOP_LOSS_PERCENT = settings["stop_loss"]

# =========================
# 🔹 ALPACA CLIENT
# =========================
trade_client = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)

# =========================
# 📊 DATA
# =========================
def get_data():
    try:
        df = yf.download(symbol, interval="1m", period="1d")

        if df is None or df.empty:
            print("⚠️ No data received")
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df.columns = [str(col).lower() for col in df.columns]

        return df

    except Exception as e:
        print("Data fetch error:", e)
        return None

# =========================
# 📈 RSI
# =========================
def calculate_rsi(data):
    rsi = RSIIndicator(close=data['close'], window=14)
    data['rsi'] = rsi.rsi()
    return data

# =========================
# 🎯 STRATEGY
# =========================
def strategy(data):
    latest = data.iloc[-1]
    rsi = latest['rsi']
    price = latest['close']

    print(f"Price: {price:.2f} | RSI: {rsi:.2f}")

    if rsi < 30:
        return "BUY"
    elif rsi > 70:
        return "SELL"
    else:
        return "HOLD"

# =========================
# 📦 POSITION CHECK
# =========================
def has_position():
    positions = trade_client.list_positions()
    for p in positions:
        if p.symbol == symbol:
            return True
    return False

def get_entry_price():
    try:
        position = trade_client.get_position(symbol)
        return float(position.avg_entry_price)
    except:
        return None

# =========================
# 🛑 STOP LOSS
# =========================
def check_stop_loss(current_price):
    global last_trade_time

    entry_price = get_entry_price()

    if entry_price:
        stop_price = entry_price * (1 - STOP_LOSS_PERCENT)

        print(f"Entry: {entry_price:.2f} | Stop: {stop_price:.2f}")

        if current_price <= stop_price:
            if time.time() - last_trade_time < TRADE_COOLDOWN:
                print("⏳ Cooldown active (stop loss)")
                return True

            print("🚨 STOP LOSS → SELL")

            trade_client.submit_order(
                symbol=symbol,
                qty=1,
                side='sell',
                type='market',
                time_in_force='gtc'
            )

            last_trade_time = time.time()
            return True

    return False

# =========================
# 💰 EXECUTE TRADE
# =========================
def execute_trade(signal):
    global last_trade_time

    if time.time() - last_trade_time < TRADE_COOLDOWN:
        print("⏳ Cooldown active")
        return

    try:
        if signal == "BUY" and not has_position():
            print("🟢 BUY order...")
            trade_client.submit_order(
                symbol=symbol,
                qty=1,
                side='buy',
                type='market',
                time_in_force='gtc'
            )
            last_trade_time = time.time()

        elif signal == "SELL" and has_position():
            print("🔴 SELL order...")
            trade_client.submit_order(
                symbol=symbol,
                qty=1,
                side='sell',
                type='market',
                time_in_force='gtc'
            )
            last_trade_time = time.time()

        else:
            print("No trade executed.")

    except Exception as e:
        print("Trade error:", e)

# =========================
# 🚀 BOT RUN
# =========================
def run_bot():
    data = get_data()

    if data is None or data.empty:
        print("⏳ Skipping run (no data)")
        return

    data = calculate_rsi(data)

    latest = data.iloc[-1]
    current_price = latest['close']

    # STOP LOSS
    if check_stop_loss(current_price):
        return

    signal = strategy(data)
    execute_trade(signal)

# =========================
# ⏱ SCHEDULER
# =========================
def job():
    print("\n⏱ Running bot...")
    run_bot()

schedule.every(15).seconds.do(job)

print("🚀 Bot started... running every 15 sec")

try:
    while True:
        schedule.run_pending()
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Bot stopped")