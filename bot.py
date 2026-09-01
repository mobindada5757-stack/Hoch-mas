import os
import ccxt
import pandas as pd
import ta
import time

# ---------------------------------------------------------
# ۱. کلیدهای API صرافی Bitget (تنظیم‌شده)
# ---------------------------------------------------------
api_key = os.environ.get('BITGET_API_KEY', 'bg_61021a8850b5dfc8a931ec63b7015a4b')
secret_key = os.environ.get('BITGET_SECRET_KEY', '4c964e43ff0be1cf3f36855e85518cd7889f16fdced38a4d74ae6513d8e8546a')
passphrase = os.environ.get('BITGET_PASSPHRASE', '')  # پسورد API بیت‌جت را در صورت وجود وارد کنید

# تنظیم اتصال به صرافی Bitget
exchange = ccxt.bitget({
    'apiKey': api_key,
    'secret': secret_key,
    'password': passphrase,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',  # فیوچرز USDT-M
    }
})

# فعال‌سازی حالت دمو / تست‌نت
exchange.set_sandbox_mode(True)

# ۱۰ ارز برتر فیوچرز
symbols = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'AVAX/USDT:USDT',
    'NEAR/USDT:USDT', 'LINK/USDT:USDT', 'ADA/USDT:USDT', 'DOGE/USDT:USDT', 'DOT/USDT:USDT'
]

timeframe = '15m'
leverage = 3           # اهرم ۳x
risk_per_trade = 0.10  # ۱۰٪ سرمایه در هر معامله
stop_loss_pct = 0.035  # حد زیان اضطراری ۳.۵٪

print("ربات فیوچرز Bitget Testnet در حال راه‌اندازی...")

# تنظیم اولیه اهرم
try:
    exchange.load_markets()
    for sym in symbols:
        try:
            exchange.set_leverage(leverage, sym)
        except Exception:
            pass
except Exception as e:
    print(f"هشدار بارگذاری مارکت‌ها: {e}")

# ---------------------------------------------------------
# ۲. تابع بررسی بازار و ثبت سفارشات
# ---------------------------------------------------------
def process_symbol(symbol, free_usdt):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=60)
        if not bars or len(bars) < 50:
            return

        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # محاسبه اندیکاتورها
        df['ema_fast'] = ta.trend.ema_indicator(df['close'], window=9)
        df['ema_slow'] = ta.trend.ema_indicator(df['close'], window=21)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)

        closed = df.iloc[-2]
        prev_closed = df.iloc[-3]
        current_price = closed['close']

        # بررسی پوزیشن‌های باز
        positions = exchange.fetch_positions([symbol])
        current_position = 0
        side = None
        
        for pos in positions:
            if pos['symbol'] == symbol:
                contracts = float(pos.get('contracts', 0) or 0)
                if contracts > 0:
                    current_position = contracts
                    side = pos['side'].lower()

        # سیگنال‌های استراتژی
        long_signal = (prev_closed['ema_fast'] < prev_closed['ema_slow']) and \
                      (closed['ema_fast'] > closed['ema_slow']) and \
                      (closed['adx'] > 20) and (45 < closed['rsi'] < 70)

        short_signal = (prev_closed['ema_fast'] > prev_closed['ema_slow']) and \
                       (closed['ema_fast'] < closed['ema_slow']) and \
                       (closed['adx'] > 20) and (30 < closed['rsi'] < 55)

        # ۱. ورود به معامله
        if current_position == 0:
            trade_val = (free_usdt * risk_per_trade) * leverage
            if trade_val >= 5:
                raw_amount = trade_val / current_price
                amount = float(exchange.amount_to_precision(symbol, raw_amount))

                if long_signal:
                    sl_price = current_price * (1 - stop_loss_pct)
                    print(f"--- [ورود LONG] {symbol} | حد زیان: ${sl_price:.2f} ---")
                    exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side='buy',
                        amount=amount,
                        params={'stopLoss': exchange.price_to_precision(symbol, sl_price)}
                    )

                elif short_signal:
                    sl_price = current_price * (1 + stop_loss_pct)
                    print(f"--- [ورود SHORT] {symbol} | حد زیان: ${sl_price:.2f} ---")
                    exchange.create_order(
                        symbol=symbol,
                        type='market',
                        side='sell',
                        amount=amount,
                        params={'stopLoss': exchange.price_to_precision(symbol, sl_price)}
                    )

        # ۲. خروج از معامله
        elif current_position > 0 and side == 'long':
            if closed['ema_fast'] < closed['ema_slow'] or closed['rsi'] > 75:
                print(f"--- [بستن LONG] {symbol} ---")
                exchange.create_market_sell_order(symbol, current_position, {'reduceOnly': True})

        elif current_position > 0 and side == 'short':
            if closed['ema_fast'] > closed['ema_slow'] or closed['rsi'] < 25:
                print(f"--- [بستن SHORT] {symbol} ---")
                exchange.create_market_buy_order(symbol, current_position, {'reduceOnly': True})

    except Exception as err:
        print(f"خطا در پردازش {symbol}: {err}")

# ---------------------------------------------------------
# ۳. حلقه اجرا (هر ۱۵ دقیقه)
# ---------------------------------------------------------
while True:
    try:
        balance_data = exchange.fetch_balance()
        current_free_usdt = float(balance_data['free'].get('USDT', 0.0) or 0.0)
        print(f"بررسی بازار... موجودی حساب دمو: ${current_free_usdt:.2f}")

        for sym in symbols:
            process_symbol(sym, current_free_usdt)
            time.sleep(0.5)

    except Exception as e:
        print(f"خطا در دریافت اطلاعات: {e}")

    time.sleep(900)
