import asyncio
import os
import logging
import aiohttp
import json
import numpy as np
from binance.enums import *
from fastapi import FastAPI
import uvicorn
import time
from binance.async_client import AsyncClient
from tasks.task import publish_message_task
from scheme import SSignal
from constants.constants import constants
from config import settings

# ==================================================================================================
#                                         КОНФИГУРАЦИЯ
# ==================================================================================================
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# API keys are now loaded from settings. Make sure config.py is set up correctly.
API_KEY = settings.BINANCE_API_KEY.get_secret_value()
API_SECRET = settings.BINANCE_SECRET_KEY.get_secret_value()

TESTNET_API_URL = "https://testnet.binancefuture.com"
TESTNET_WS_URL = "wss://stream.binancefuture.com/ws/btcusdt@trade"

SYMBOL = "BTCUSDT"

# PARAMETERS FOR THE BOT
# No one can guarantee 93% profit. This algorithm is designed to improve chances of profitability
# by managing risk and adapting to market conditions.
QTY_BASE = 0.006 # Base volume to be rounded to the correct precision
TIMEOUT = 1
MAX_OPEN_ORDERS = 25
# PROPORTION OF ATR TO USE FOR DYNAMIC SPREAD. Higher value = wider spread.
ATR_SPREAD_MULTIPLIER = 1.5 
TRAILING_STOP_PERCENT = 0.5  # 0.5% trailing stop-loss
PROFIT_TARGET_USD = 15.0 # Take-Profit target   
STOP_LOSS_USD = 2.0    # <-- ИЗМЕНЕНО: Более агрессивный стоп-лосс
NEW_ORDER_PLACEMENT_INTERVAL = 5

# PARAMETERS FOR ANALYSIS
KLINES_INTERVAL = KLINE_INTERVAL_1MINUTE  # Interval for candlestick data
SHORT_MA_PERIOD = 20  # Period for the fast moving average
LONG_MA_PERIOD = 50   # Period for the slow moving average
RSI_PERIOD = 14       # Period for RSI calculation
ATR_PERIOD = 14       # Period for ATR calculation
MOMENTUM_PERIOD = 10  # NEW: Period for momentum calculation
ANALYSIS_INTERVAL = 10 

# ==================================================================================================
#                                         GLOBAL STATE
# ==================================================================================================
async_client = None
current_price = None
is_bot_running = False
open_orders = {}
last_order_placement_time = 0
ma_signal = None  
rsi_signal = None 
volume_signal = None 
momentum_signal = None # NEW: Global variable for momentum signal
atr_value = None # Global variable for ATR

# Variables to store precision and step size info from the exchange
tick_size = None
price_precision = None
step_size = None
qty_precision = None


# ==================================================================================================
#                                       MARKET ANALYSIS MODULE
# ==================================================================================================
async def market_analyzer_loop():
    """
    Periodically collects data and analyzes the market using MA, RSI, Volume, and ATR.
    """
    global ma_signal, rsi_signal, volume_signal, atr_value, momentum_signal
    while True:
        if is_bot_running:
            try:
                # Get more klines for reliable MA, RSI, and ATR calculation
                klines = await async_client.futures_klines(
                    symbol=SYMBOL, 
                    interval=KLINES_INTERVAL, 
                    limit=max(LONG_MA_PERIOD, RSI_PERIOD, ATR_PERIOD, MOMENTUM_PERIOD) + 1
                )
                
                # Extract prices and volumes
                close_prices = np.array([float(kline[4]) for kline in klines])
                highs = np.array([float(kline[2]) for kline in klines])
                lows = np.array([float(kline[3]) for kline in klines])
                volumes = np.array([float(kline[5]) for kline in klines])

                # --- Moving Average Analysis ---
                short_ma = np.mean(close_prices[-SHORT_MA_PERIOD:])
                long_ma = np.mean(close_prices[-LONG_MA_PERIOD:])
                if short_ma > long_ma:
                    ma_signal = "BUY"
                elif short_ma < long_ma:
                    ma_signal = "SELL"
                else:
                    ma_signal = None
                
                # --- RSI Analysis ---
                price_changes = np.diff(close_prices)
                gains = price_changes[price_changes > 0]
                losses = -price_changes[price_changes < 0]

                avg_gain = np.mean(gains[-RSI_PERIOD:]) if len(gains) >= RSI_PERIOD else 0
                avg_loss = np.mean(losses[-RSI_PERIOD:]) if len(losses) >= RSI_PERIOD else 0
                
                rs = avg_gain / avg_loss if avg_loss != 0 else 0
                rsi = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100
                
                if rsi < 30:
                    rsi_signal = "BUY" 
                elif rsi > 70:
                    rsi_signal = "SELL"
                else:
                    rsi_signal = None
                
                # --- Volume Analysis ---
                avg_volume = np.mean(volumes)
                current_volume = volumes[-1]
                if current_volume > avg_volume:
                    volume_signal = "CONFIRM"
                else:
                    volume_signal = None
                
                # --- Momentum Analysis (NEW) ---
                # Check for enough data points before calculating
                if len(close_prices) > MOMENTUM_PERIOD:
                    # Calculate momentum as the difference between the current price and the price N periods ago
                    momentum_value = close_prices[-1] - close_prices[-MOMENTUM_PERIOD]
                    if momentum_value > 0:
                        momentum_signal = "BUY"
                    elif momentum_value < 0:
                        momentum_signal = "SELL"
                    else:
                        momentum_signal = None
                else:
                    momentum_signal = None
                
                # --- ATR Analysis (for Dynamic Spreads) ---
                true_ranges = [
                    max(highs[i] - lows[i], abs(highs[i] - close_prices[i-1]), abs(lows[i] - close_prices[i-1]))
                    for i in range(1, len(klines))
                ]
                atr_value = np.mean(true_ranges[-ATR_PERIOD:])
                
                logging.info(f"Analysis: MA: {ma_signal}, RSI: {rsi_signal}, Volume: {volume_signal}, Momentum: {momentum_signal}, ATR: {atr_value}")

            except Exception as e:
                logging.error(f"Failed to perform market analysis: {e}")

        await asyncio.sleep(ANALYSIS_INTERVAL)


async def monitor_open_position():
    """
    Непрерывно мониторит открытую позицию и закрывает её,
    если достигается стоп-лосс или тейк-профит.
    """
    global is_bot_running, last_order_placement_time
    logging.info("Starting continuous monitoring of open position...")
    while is_bot_running:
        try:
            positions = await async_client.futures_position_information(symbol=SYMBOL)
            has_open_position = any(float(p['positionAmt']) != 0 for p in positions)
            
            if not has_open_position:
                logging.info("Position closed, stopping monitor.")
                return

            for position in positions:
                position_amount = float(position.get('positionAmt', 0))
                if position_amount != 0:
                    unrealized_pnl = float(position.get('unrealizedPnl', 0))

                    if unrealized_pnl >= PROFIT_TARGET_USD:
                        logging.info(f"Take-Profit triggered! PnL: {unrealized_pnl}. Closing position immediately!")
                        side_to_close = SIDE_SELL if position_amount > 0 else SIDE_BUY
                        await async_client.futures_create_order(
                            symbol=SYMBOL,
                            side=side_to_close,
                            type=ORDER_TYPE_MARKET,
                            quantity=abs(position_amount)
                        )
                        logging.info("Position closed by Take-Profit.")
                        last_order_placement_time = 0
                        return
                    
                    elif unrealized_pnl <= -STOP_LOSS_USD:
                        logging.warning(f"Stop-Loss triggered! PnL: {unrealized_pnl}. Closing position to protect capital!")
                        side_to_close = SIDE_SELL if position_amount > 0 else SIDE_BUY
                        await async_client.futures_create_order(
                            symbol=SYMBOL,
                            side=side_to_close,
                            type=ORDER_TYPE_MARKET,
                            quantity=abs(position_amount)
                        )
                        logging.info("Position closed by Stop-Loss.")
                        last_order_placement_time = 0
                        return
        except Exception as e:
            logging.error(f"Error while monitoring position: {e}")
        
        await asyncio.sleep(0.5) # Проверяем PnL каждые полсекунды


def make_predictive_decision():
    """
    Принимает "умное" решение, анализируя все индикаторы для получения консенсуса.
    Теперь достаточно совпадения двух из трёх сигналов.
    """
    global ma_signal, rsi_signal, momentum_signal
    
    buy_signals = 0
    sell_signals = 0
    
    if ma_signal == "BUY":
        buy_signals += 1
    elif ma_signal == "SELL":
        sell_signals += 1
        
    if rsi_signal == "BUY":
        buy_signals += 1
    elif rsi_signal == "SELL":
        sell_signals += 1
        
    if momentum_signal == "BUY":
        buy_signals += 1
    elif momentum_signal == "SELL":
        sell_signals += 1
        
    # Решение принимается, если есть хотя бы 2 совпадения
    if buy_signals >= 2:
        logging.info("Strong BUY signal from majority of indicators.")
        return "BUY"
    
    if sell_signals >= 2:
        logging.info("Strong SELL signal from majority of indicators.")
        return "SELL"
    
    # Если нет сильного согласованного сигнала, не делаем ничего
    return None


# ==================================================================================================
#                                         TRADING LOGIC MODULE
# ==================================================================================================
async def trading_logic_loop():
    """
    Основной цикл торговой логики.
    """
    global current_price, open_orders, last_order_placement_time, ma_signal, atr_value

    if not current_price or not qty_precision or not step_size or atr_value is None:
        return

    try:
        positions = await async_client.futures_position_information(symbol=SYMBOL)
        has_open_position = any(float(p['positionAmt']) != 0 for p in positions)
        
        # --- ROBUST PRECISION LOGIC ---
        num_steps = round(QTY_BASE / step_size)
        final_qty = num_steps * step_size
        qty_str = f"{final_qty:.{qty_precision}f}"

        if has_open_position:
            # ЛОГИКА 1: УПРАВЛЕНИЕ ОТКРЫТОЙ ПОЗИЦИЕЙ
            # Мы отменяем все открытые ордера, чтобы они не мешали.
            await async_client.futures_cancel_all_open_orders(symbol=SYMBOL)
            open_orders.clear()
            # Запускаем мониторинг позиции
            asyncio.create_task(monitor_open_position())
        else:
            # ЛОГИКА 2: РАЗМЕЩЕНИЕ НОВЫХ ОРДЕРОВ
            if time.time() - last_order_placement_time >= NEW_ORDER_PLACEMENT_INTERVAL:
                await check_and_cancel_orders()

                if len(open_orders) < MAX_OPEN_ORDERS:
                    # --- NEW Dynamic Spread Calculation ---
                    dynamic_spread_usd = atr_value * ATR_SPREAD_MULTIPLIER
                    
                    # НОВОЕ: Используем нашу "умную" функцию для принятия решения
                    decision = make_predictive_decision()
                    
                    if decision == "BUY":
                        bid_price = current_price - dynamic_spread_usd
                        bid_price_str = f"{bid_price:.{price_precision}f}"
                        order_buy = await async_client.futures_create_order(
                            symbol=SYMBOL,
                            side=SIDE_BUY,
                            type=ORDER_TYPE_LIMIT,
                            timeInForce=TIME_IN_FORCE_GTC,
                            quantity=qty_str,
                            price=bid_price_str,
                        )
                        open_orders[order_buy["orderId"]] = "BUY"
                        logging.info(f"Predictive BUY Decision! Placed BUY order at {bid_price_str} with QTY {qty_str}. Dynamic Spread: {dynamic_spread_usd}")
                    
                    elif decision == "SELL":
                        ask_price = current_price + dynamic_spread_usd
                        ask_price_str = f"{ask_price:.{price_precision}f}"
                        order_sell = await async_client.futures_create_order(
                            symbol=SYMBOL,
                            side=SIDE_SELL,
                            type=ORDER_TYPE_LIMIT,
                            timeInForce=TIME_IN_FORCE_GTC,
                            quantity=qty_str,
                            price=ask_price_str,
                        )
                        open_orders[order_sell["orderId"]] = "SELL"
                        logging.info(f"Predictive SELL Decision! Placed SELL order at {ask_price_str} with QTY {qty_str}. Dynamic Spread: {dynamic_spread_usd}")
                    
                    last_order_placement_time = time.time()
    
    except Exception as e:
        logging.error(f"Fatal error in trading logic: {e}")


# ==================================================================================================
#                                         DATA COLLECTOR MODULE
# ==================================================================================================
async def data_collector():
    global current_price, is_bot_running

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(TESTNET_WS_URL) as ws:
            logging.info("Connected to Binance Testnet WebSocket.")
            async for msg in ws:
                if not is_bot_running:
                    continue
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    trade_data = data
                    current_price = float(trade_data["p"])


# ==================================================================================================
#                                           MAIN BOT LOOP
# ==================================================================================================
async def main_loop():
    """
    Главный цикл бота.
    """
    while True:
        if is_bot_running and current_price:
            await trading_logic_loop()
        await asyncio.sleep(TIMEOUT)


async def check_and_cancel_orders():
    global open_orders

    try:
        actual_open_orders = await async_client.futures_get_open_orders(symbol=SYMBOL)
        actual_open_orders_ids = {o["orderId"] for o in actual_open_orders}

        orders_to_cancel_ids = [oid for oid in open_orders.keys() if oid not in actual_open_orders_ids]
        
        for oid in orders_to_cancel_ids:
            try:
                await async_client.futures_cancel_order(symbol=SYMBOL, orderId=oid)
                del open_orders[oid]
                logging.info(f"Canceled stale order {oid}.")
            except Exception as e:
                logging.warning(f"Order {oid} was likely filled. Ignoring cancellation error: {e}")
                del open_orders[oid]

        open_orders_temp = {}
        for order in actual_open_orders:
            side = order['side']
            if side == SIDE_BUY:
                open_orders_temp[order['orderId']] = "BUY"
            elif side == SIDE_SELL:
                open_orders_temp[order['orderId']] = "SELL"
        open_orders = open_orders_temp

    except Exception as e:
        logging.error(f"Failed to check and cancel orders: {e}")


# ==================================================================================================
#                                           API MODULE
# ==================================================================================================
app = FastAPI()


@app.on_event("startup")
async def startup_event():
    global tick_size, price_precision, step_size, qty_precision, async_client
    logging.info("Starting up API and fetching exchange info...")
    
    async_client = await AsyncClient.create(API_KEY, API_SECRET, testnet=True)

    try:
        info = await async_client.futures_exchange_info()
        for symbol_info in info["symbols"]:
            if symbol_info["symbol"] == SYMBOL:
                # Get price precision
                for filter_info in symbol_info["filters"]:
                    if filter_info["filterType"] == "PRICE_FILTER":
                        tick_size = float(filter_info["tickSize"])
                        # Using numpy to get correct precision
                        price_precision = int(round(-np.log10(tick_size)))
                        logging.info(
                            f"Fetched price precision for {SYMBOL}: {price_precision}, tick_size: {tick_size}"
                        )
                    # Get quantity precision
                    elif filter_info["filterType"] == "LOT_SIZE":
                        step_size = float(filter_info["stepSize"])
                        # Using numpy to get correct precision
                        qty_precision = int(round(-np.log10(step_size)))
                        logging.info(
                            f"Fetched quantity precision for {SYMBOL}: {qty_precision}, step_size: {step_size}"
                        )
                break
    except Exception as e:
        logging.error(f"Failed to fetch exchange info: {e}")
        return

    asyncio.create_task(data_collector())
    asyncio.create_task(main_loop())
    asyncio.create_task(market_analyzer_loop()) 


@app.post("/start_bot")
async def start_bot():
    global is_bot_running
    if not is_bot_running:
        is_bot_running = True
        return {
            "status": "Market making bot started on Testnet. We are now the market."
        }
    return {"status": "Bot is already running."}


@app.post("/stop_bot")
async def stop_bot():
    global is_bot_running
    if is_bot_running:
        is_bot_running = False
        return {"status": "Bot stopped. Awaiting new orders."}
    return {"status": "Bot is not running."}


@app.post("/close_all_positions")
async def close_all_positions():
    global is_bot_running, open_orders, last_order_placement_time
    logging.info("Received request to close all positions. Halting trading.")

    is_bot_running = False

    try:
        await async_client.futures_cancel_all_open_orders(symbol=SYMBOL)
        open_orders = {}
        last_order_placement_time = 0

        positions = await async_client.futures_position_information(symbol=SYMBOL)

        for p in positions:
            if float(p["positionAmt"]) != 0:
                side_to_close = SIDE_SELL if float(p["positionAmt"]) > 0 else SIDE_BUY
                await async_client.futures_create_order(
                    symbol=SYMBOL,
                    side=side_to_close,
                    type=ORDER_TYPE_MARKET,
                    quantity=abs(float(p["positionAmt"])),
                )
                logging.info(
                    f"Closed a position with quantity {p['positionAmt']}"
                )

        return {"status": "All positions closed and bot halted."}
    except Exception as e:
        logging.error(f"Failed to close all positions: {e}")
        return {"status": "Error closing positions. Check logs."}


@app.get("/status")
async def get_status():
    return {
        "is_running": is_bot_running,
        "current_price": current_price,
        "ma_signal": ma_signal,
        "rsi_signal": rsi_signal,
        "volume_signal": volume_signal,
        "open_orders_count": len(open_orders),
        "message": "We are making the market on Testnet, not chasing it.",
    }


if __name__ == "__main__":
    if not API_KEY or not API_SECRET:
        logging.error("API keys not set. Please set them as environment variables.")
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000)
