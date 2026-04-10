import time
import uuid
import schedule
import json
import yfinance as yf
import pandas as pd

from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator, MACD

from config import API_KEY, SECRET_KEY

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus


symbol = "AAPL"
sleep_seconds = 15

# Paper=True is the safe setting for simulated trading
trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

# Strategy / risk settings
ORDER_DOLLARS = 1000
RSI_BUY = 55
RSI_SELL = 45
COOLDOWN_SECONDS = 300
last_trade_time = 0


def load_settings():
    try:
        with open("settings.json", "r") as f:
            return json.load(f)
    except Exception:
        return {"stop_loss": 0.03, "take_profit": 0.06}


def get_data():
    try:
        df = yf.download(symbol, period="60d", interval="5m", progress=False)
        if df is None or df.empty:
            print("No market data received")
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        df.columns = [str(col).lower() for col in df.columns]
        return df
    except Exception as e:
        print(f"Data error: {e}")
        return None


def calculate_indicators(data: pd.DataFrame) -> pd.DataFrame:
    data["rsi"] = RSIIndicator(close=data["close"], window=14).rsi()
    data["ma_short"] = SMAIndicator(close=data["close"], window=9).sma_indicator()
    data["ma_long"] = SMAIndicator(close=data["close"], window=21).sma_indicator()
    data["ma_trend"] = SMAIndicator(close=data["close"], window=50).sma_indicator()

    macd = MACD(close=data["close"])
    data["macd"] = macd.macd()
    data["macd_signal"] = macd.macd_signal()
    return data


def strategy(row) -> str:
    # Strong uptrend buy
    if (
        row["ma_short"] > row["ma_long"]
        and row["ma_long"] > row["ma_trend"]
        and row["rsi"] > RSI_BUY
    ):
        return "BUY"

    # Strong downtrend sell / exit
    if (
        row["ma_short"] < row["ma_long"]
        and row["ma_long"] < row["ma_trend"]
        and row["rsi"] < RSI_SELL
    ):
        return "SELL"

    return "HOLD"


def has_open_position() -> bool:
    try:
        positions = trading_client.get_all_positions()
        return any(p.symbol == symbol for p in positions)
    except Exception as e:
        print(f"Position check error: {e}")
        return False


def get_position_qty():
    try:
        positions = trading_client.get_all_positions()
        for p in positions:
            if p.symbol == symbol:
                return float(p.qty)
    except Exception:
        pass
    return 0.0


def recent_open_order_exists() -> bool:
    try:
        req = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        orders = trading_client.get_orders(filter=req)
        return any(o.symbol == symbol for o in orders)
    except Exception as e:
        print(f"Order check error: {e}")
        return False


def submit_buy_with_bracket(price: float):
    settings = load_settings()
    stop_loss_pct = float(settings.get("stop_loss", 0.03))
    take_profit_pct = float(settings.get("take_profit", 0.06))

    qty = round(ORDER_DOLLARS / price, 4)
    if qty <= 0:
        print("Qty too small; skipping")
        return

    tp_price = round(price * (1 + take_profit_pct), 2)
    sl_price = round(price * (1 - stop_loss_pct), 2)

    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        order_class=OrderClass.BRACKET,
        take_profit=TakeProfitRequest(limit_price=tp_price),
        stop_loss=StopLossRequest(stop_price=sl_price),
        client_order_id=f"bot-{uuid.uuid4().hex[:18]}",
    )

    result = trading_client.submit_order(order_data=order)
    print(f"BUY submitted: qty={qty}, tp={tp_price}, sl={sl_price}, order_id={result.id}")


def submit_market_sell():
    qty = get_position_qty()
    if qty <= 0:
        print("No position to sell")
        return

    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        client_order_id=f"bot-{uuid.uuid4().hex[:18]}",
    )

    result = trading_client.submit_order(order_data=order)
    print(f"SELL submitted: qty={qty}, order_id={result.id}")


def run_bot():
    global last_trade_time

    data = get_data()
    if data is None or data.empty:
        print("Skipping cycle: no data")
        return

    data = calculate_indicators(data)
    latest = data.iloc[-1]

    if pd.isna(latest["rsi"]) or pd.isna(latest["ma_trend"]):
        print("Skipping cycle: indicators not ready")
        return

    price = float(latest["close"])
    signal = strategy(latest)

    print(
        f"Price={price:.2f} | RSI={latest['rsi']:.2f} | "
        f"MA9={latest['ma_short']:.2f} | MA21={latest['ma_long']:.2f} | "
        f"MA50={latest['ma_trend']:.2f} | Signal={signal}"
    )

    if time.time() - last_trade_time < COOLDOWN_SECONDS:
        print("Cooldown active")
        return

    if recent_open_order_exists():
        print("Open order already exists; skipping")
        return

    in_position = has_open_position()

    if signal == "BUY" and not in_position:
        submit_buy_with_bracket(price)
        last_trade_time = time.time()

    elif signal == "SELL" and in_position:
        submit_market_sell()
        last_trade_time = time.time()

    else:
        print("No trade executed")


def job():
    print("\nRunning bot...")
    run_bot()


schedule.every(sleep_seconds).seconds.do(job)

print("Paper bot started...")
try:
    while True:
        schedule.run_pending()
        time.sleep(1)
except KeyboardInterrupt:
    print("Bot stopped")