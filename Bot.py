import os
import json
import urllib.request
import urllib.parse
import math
from datetime import datetime, timezone
# =========================================================
# AYARLAR
# =========================================================
BINANCE = "https://data-api.binance.vision"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STABLECOINS = {
    "USDT", "USDC", "FDUSD", "USDE",
    "TUSD", "DAI", "RLUSD", "USD1", "USDD"
}
MAX_COINS = 100
# =========================================================
# HTTP
# =========================================================
def get(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())
# =========================================================
# TELEGRAM
# =========================================================
def get_chat_id():
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        data = get(url)
        for update in reversed(data.get("result", [])):
            message = update.get("message")
            if message and message.get("chat"):
                return str(message["chat"]["id"])
    except Exception as e:
        print("Chat ID error:", e)
    return None
def send_telegram(message):
    chat_id = get_chat_id()
    if not chat_id:
        print("Chat ID bulunamadı.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=20):
        print("Telegram mesajı gönderildi.")
# =========================================================
# KLINE
# =========================================================
def get_klines(symbol, interval, limit=150):
    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    })
    url = BINANCE + "/api/v3/klines?" + params
    data = get(url)
    close = [float(x[4]) for x in data]
    high = [float(x[2]) for x in data]
    low = [float(x[3]) for x in data]
    volume = [float(x[5]) for x in data]
    return close, high, low, volume
# =========================================================
# EMA
# =========================================================
def ema(values, period):
    if len(values) < period:
        return values[-1]
    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = (
            value * multiplier
            + result * (1 - multiplier)
        )
    return result
# =========================================================
# RSI
# =========================================================
def rsi(values, period=14):
    if len(values) <= period:
        return 50
    gains = []
    losses = []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (
            avg_gain * (period - 1)
            + gains[i]
        ) / period
        avg_loss = (
            avg_loss * (period - 1)
            + losses[i]
        ) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
# =========================================================
# STOCH RSI
# =========================================================
def stoch_rsi(values, period=14):
    rsi_values = []
    for i in range(period, len(values)):
        rsi_values.append(
            rsi(values[:i + 1], period)
        )
    if len(rsi_values) < period:
        return 50
    recent = rsi_values[-period:]
    lowest = min(recent)
    highest = max(recent)
    if highest == lowest:
        return 50
    return (
        (rsi_values[-1] - lowest)
        /
        (highest - lowest)
    ) * 100
# =========================================================
# MACD
# =========================================================
def macd(values):
    if len(values) < 35:
        return 0, 0, 0
    macd_values = []
    for i in range(26, len(values)):
        e12 = ema(values[:i + 1], 12)
        e26 = ema(values[:i + 1], 26)
        macd_values.append(e12 - e26)
    line = macd_values[-1]
    signal = ema(macd_values, 9)
    return line, signal, line - signal
# =========================================================
# BOLLINGER
# =========================================================
def bollinger(values, period=20):
    recent = values[-period:]
    middle = sum(recent) / len(recent)
    variance = sum(
        (x - middle) ** 2
        for x in recent
    ) / len(recent)
    std = math.sqrt(variance)
    return (
        middle + 2 * std,
        middle,
        middle - 2 * std
    )
# =========================================================
# OBV
# =========================================================
def obv(values, volumes):
    result = 0
    output = [0]
    for i in range(1, len(values)):
        if values[i] > values[i - 1]:
            result += volumes[i]
        elif values[i] < values[i - 1]:
            result -= volumes[i]
        output.append(result)
    return output
# =========================================================
# ATR
# =========================================================
def atr(high, low, close, period=14):
    trs = []
    start = max(1, len(close) - period)
    for i in range(start, len(close)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
        trs.append(tr)
    if not trs:
        return 0
    return sum(trs) / len(trs)
# =========================================================
# SUPERTREND
# =========================================================
def supertrend(high, low, close, period=10, multiplier=3):
    if len(close) < period + 2:
        return False
    current_atr = atr(
        high,
        low,
        close,
        period
    )
    hl2 = (
        high[-1] + low[-1]
    ) / 2
    lower_band = (
        hl2 - multiplier * current_atr
    )
    upper_band = (
        hl2 + multiplier * current_atr
    )
    if close[-1] > lower_band:
        return True
    return False
# =========================================================
# TDI
# =========================================================
def tdi(values):
    current = rsi(values, 13)
    previous = rsi(values[:-1], 13)
    signal = (
        current * 0.7
        + previous * 0.3
    )
    return current, signal
# =========================================================
# ADX + DI
# =========================================================
def adx(high, low, close, period=14):
    if len(close) < period * 2:
        return 0, 0, 0
    tr_values = []
    plus_dm = []
    minus_dm = []
    for i in range(1, len(close)):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
        tr_values.append(tr)
        plus_dm.append(
            up_move
            if up_move > down_move and up_move > 0
            else 0
        )
        minus_dm.append(
            down_move
            if down_move > up_move and down_move > 0
            else 0
        )
    if len(tr_values) < period:
        return 0, 0, 0
    atr_value = sum(
        tr_values[-period:]
    ) / period
    plus = sum(
        plus_dm[-period:]
    ) / period
    minus = sum(
        minus_dm[-period:]
    ) / period
    if atr_value == 0:
        return 0, 0, 0
    plus_di = (
        100 * plus / atr_value
    )
    minus_di = (
        100 * minus / atr_value
    )
    denominator = (
        plus_di + minus_di
    )
    if denominator == 0:
        return 0, plus_di, minus_di
    dx = (
        100
        * abs(plus_di - minus_di)
        / denominator
    )
    return dx, plus_di, minus_di
# =========================================================
# VWAP
# =========================================================
def vwap(high, low, close, volume, period=50):
    start = max(
        0,
        len(close) - period
    )
    total_volume = 0
    total_value = 0
    for i in range(start, len(close)):
        typical_price = (
            high[i]
            + low[i]
            + close[i]
        ) / 3
        total_value += (
            typical_price * volume[i]
        )
        total_volume += volume[i]
    if total_volume == 0:
        return close[-1]
    return (
        total_value
        / total_volume
    )
# =========================================================
# VOLUME ANALYSIS
# =========================================================
def volume_analysis(volumes):
    if len(volumes) < 25:
        return 1, 1
    average = (
        sum(volumes[-21:-1])
        / 20
    )
    if average <= 0:
        return 1, 1
    current_ratio = (
        volumes[-1]
        / average
    )
    previous_average = (
        sum(volumes[-6:-1])
        / 5
    )
    if previous_average <= 0:
        acceleration = 1
    else:
        acceleration = (
            volumes[-1]
            / previous_average
        )
    return current_ratio, acceleration
# =========================================================
# BREAKOUT
# =========================================================
def breakout_analysis(high, low, close, lookback=20):
    if len(close) < lookback + 2:
        return False, False
    previous_high = max(
        high[-lookback-1:-1]
    )
    previous_low = min(
        low[-lookback-1:-1]
    )
    bullish = (
        close[-1] > previous_high
    )
    bearish = (
        close[-1] < previous_low
    )
    return bullish, bearish
# =========================================================
# PRICE FORMAT
# =========================================================
def price_format(value):
    if value >= 100:
        return f"{value:.2f}"
    if value >= 1:
        return f"{value:.4f}"
    if value >= 0.01:
        return f"{value:.6f}"
    return f"{value:.10f}"
# =========================================================
# STABLECOIN
# =========================================================
def stablecoin_pair(symbol):
    base = symbol.replace("USDT", "")
    return base in STABLECOINS
# =========================================================
# ANALYZE
# =========================================================
def analyze(symbol):
    try:
        close15, high15, low15, vol15 = get_klines(
            symbol,
            "15m"
        )
        close1h, high1h, low1h, vol1h = get_klines(
            symbol,
            "1h"
        )
        close4h, high4h, low4h, vol4h = get_klines(
            symbol,
            "4h"
        )
        price = close15[-1]
        # =================================================
        # INDICATORS
        # =================================================
        rsi15 = rsi(close15)
        rsi1h = rsi(close1h)
        rsi4h = rsi(close4h)
        stoch = stoch_rsi(close15)
        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)
        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)
        macd15, signal15, hist15 = macd(close15)
        macd1h, signal1h, hist1h = macd(close1h)
        upper, middle, lower = bollinger(
            close15
        )
        obv_values = obv(
            close15,
            vol15
        )
        st15 = supertrend(
            high15,
            low15,
            close15
        )
        st1h = supertrend(
            high1h,
            low1h,
            close1h
        )
        tdi_rsi, tdi_signal = tdi(
            close15
        )
        adx15, plus_di, minus_di = adx(
            high15,
            low15,
            close15
        )
        adx1h, plus_di1h, minus_di1h = adx(
            high1h,
            low1h,
            close1h
        )
        current_vwap = vwap(
            high15,
            low15,
            close15,
            vol15
        )
        volume_ratio, volume_acceleration = (
            volume_analysis(vol15)
        )
        bullish_breakout, bearish_breakout = (
            breakout_analysis(
                high15,
                low15,
                close15
            )
        )
        current_atr = atr(
            high15,
            low15,
            close15
        )
        if current_atr <= 0:
            return None
        # =================================================
        # MOMENTUM
        # =================================================
        momentum_15m = (
            (price / close15[-5]) - 1
        ) * 100
        momentum_1h = (
            (price / close15[-21]) - 1
        ) * 100
        # =================================================
        # LONG SCORE
        # =================================================
        long_score = 0
        long_reasons = []
        long_warnings = []
        # RSI
        if 50 <= rsi15 <= 65:
            long_score += 7
            long_reasons.append("RSI ideal")
        elif 65 < rsi15 <= 70:
            long_score += 3
        elif rsi15 > 70:
            long_score -= 8
            long_warnings.append("RSI yüksek")
        elif rsi15 < 45:
            long_score -= 7
            long_warnings.append("RSI zayıf")
        if 50 <= rsi1h <= 65:
            long_score += 7
            long_reasons.append("1h RSI")
        elif 65 < rsi1h <= 70:
            long_score += 2
        elif rsi1h > 75:
            long_score -= 15
            long_warnings.append(
                "1h aşırı alım"
            )
        if 45 <= rsi4h <= 65:
            long_score += 7
            long_reasons.append("4h RSI")
        elif rsi4h > 70:
            long_score -= 7
            long_warnings.append(
                "4h RSI yüksek"
            )
        elif rsi4h < 40:
            long_score -= 15
            long_warnings.append(
                "4h RSI zayıf"
            )
        # EMA
        if price > ema9 > ema21:
            long_score += 8
            long_reasons.append(
                "EMA9/21"
            )
        if price > ema50:
            long_score += 5
            long_reasons.append(
                "EMA50"
            )
        if (
            price > ema21_4h
            and ema21_4h > ema50_4h
        ):
            long_score += 9
            long_reasons.append(
                "4h trend"
            )
        elif price > ema50_4h:
            long_score += 3
            long_reasons.append(
                "4h EMA50"
            )
        else:
            long_score -= 7
            long_warnings.append(
                "4h zayıf"
            )
        # MACD
        if (
            macd15 > signal15
            and hist15 > 0
        ):
            long_score += 6
            long_reasons.append(
                "MACD"
            )
        if (
            macd1h > signal1h
            and hist1h > 0
        ):
            long_score += 8
            long_reasons.append(
                "1h MACD"
            )
        # STOCH RSI
        if 20 <= stoch <= 80:
            long_score += 6
            long_reasons.append(
                "Stoch RSI"
            )
        elif 80 < stoch <= 90:
            long_score -= 3
            long_warnings.append(
                "Stoch RSI yüksek"
            )
        elif stoch > 90:
            long_score -= 15
            long_warnings.append(
                "Stoch RSI çok yüksek"
            )
        # BOLLINGER
        if middle < price < upper:
            long_score += 3
            long_reasons.append(
                "Bollinger"
            )
        elif price > upper:
            long_score -= 5
            long_warnings.append(
                "BB üstü"
            )
        # OBV
        if len(obv_values) >= 6:
            if (
                obv_values[-1]
                > obv_values[-5]
            ):
                long_score += 4
                long_reasons.append(
                    "OBV"
                )
        # SUPERTREND
        if st15:
            long_score += 3
            long_reasons.append(
                "Supertrend"
            )
        if st1h:
            long_score += 4
            long_reasons.append(
                "1h Supertrend"
            )
        # TDI
        if (
            tdi_rsi > tdi_signal
            and 50 < tdi_rsi < 70
        ):
            long_score += 3
            long_reasons.append(
                "TDI"
            )
        # =================================================
        # ADX
        # =================================================
        if adx15 >= 20:
            if plus_di > minus_di:
                long_score += 6
                long_reasons.append(
                    f"ADX {adx15:.0f}"
                )
            else:
                long_score -= 4
        if adx1h >= 20:
            if plus_di1h > minus_di1h:
                long_score += 6
                long_reasons.append(
                    "1h ADX"
                )
        # =================================================
        # VWAP
        # =================================================
        if price > current_vwap:
            long_score += 5
            long_reasons.append(
                "VWAP üstü"
            )
        else:
            long_score -= 3
            long_warnings.append(
                "VWAP altı"
            )
        # =================================================
        # VOLUME
        # =================================================
        if volume_ratio >= 3:
            long_score += 10
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )
        elif volume_ratio >= 2:
            long_score += 8
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )
        elif volume_ratio >= 1.5:
            long_score += 6
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )
        elif volume_ratio >= 1.2:
            long_score += 2
        else:
            long_score -= 8
            long_warnings.append(
                "Hacim düşük"
            )
        # =================================================
        # VOLUME ACCELERATION
        # =================================================
        if volume_acceleration >= 3:
            long_score += 8
            long_reasons.append(
                "Hacim ivmesi"
            )
        elif volume_acceleration >= 2:
            long_score += 5
            long_reasons.append(
                "Hacim hızlanıyor"
            )
        # =================================================
        # BREAKOUT
        # =================================================
        if bullish_breakout:
            long_score += 10
            long_reasons.append(
                "20 mum breakout"
            )
        # =================================================
        # MOMENTUM
        # =================================================
        if 0.3 <= momentum_15m <= 4:
            long_score += 5
            long_reasons.append(
                "Momentum"
            )
        elif momentum_15m < 0:
            long_score -= 8
            long_warnings.append(
                "Momentum negatif"
            )
        if momentum_1h > 0:
            long_score += 3
        # =================================================
        # SHORT SCORE
        # =================================================
        short_score = 0
        short_reasons = []
        short_warnings = []
        # RSI
        if 35 <= rsi15 <= 50:
            short_score += 7
            short_reasons.append(
                "RSI short bölgesi"
            )
        elif rsi15 < 30:
            short_score -= 10
            short_warnings.append(
                "RSI aşırı satım"
            )
        elif rsi15 > 70:
            short_score += 5
            short_reasons.append(
                "RSI yüksek"
            )
        if 35 <= rsi1h <= 50:
            short_score += 7
            short_reasons.append(
                "1h RSI"
            )
        elif rsi1h < 30:
            short_score -= 10
        if rsi4h < 50:
            short_score += 7
            short_reasons.append(
                "4h RSI zayıf"
            )
        elif rsi4h > 70:
            short_score -= 6
        # EMA
        if price < ema9 < ema21:
            short_score += 8
            short_reasons.append(
                "EMA9/21 aşağı"
            )
        if price < ema50:
            short_score += 5
            short_reasons.append(
                "EMA50 altı"
            )
        if (
            price < ema21_4h
            and ema21_4h < ema50_4h
        ):
            short_score += 9
            short_reasons.append(
                "4h downtrend"
            )
        elif price < ema50_4h:
            short_score += 3
        # MACD
        if (
            macd15 < signal15
            and hist15 < 0
        ):
            short_score += 6
            short_reasons.append(
                "MACD aşağı"
            )
        if (
            macd1h < signal1h
            and hist1h < 0
        ):
            short_score += 8
            short_reasons.append(
                "1h MACD aşağı"
            )
        # STOCH
        if 20 <= stoch <= 80:
            short_score += 5
            short_reasons.append(
                "Stoch RSI"
            )
        elif stoch < 20:
            short_score -= 8
            short_warnings.append(
                "Stoch RSI aşırı düşük"
            )
        # BB
        if lower < price < middle:
            short_score += 4
            short_reasons.append(
                "Bollinger"
            )
        elif price < lower:
            short_score -= 5
            short_warnings.append(
                "BB altı"
            )
        # OBV
        if len(obv_values) >= 6:
            if (
                obv_values[-1]
                < obv_values[-5]
            ):
                short_score += 4
                short_reasons.append(
                    "OBV düşüyor"
                )
        # Supertrend
        if not st15:
            short_score += 3
            short_reasons.append(
                "Supertrend aşağı"
            )
        if not st1h:
            short_score += 4
            short_reasons.append(
                "1h Supertrend aşağı"
            )
        # TDI
        if (
            tdi_rsi < tdi_signal
            and 30 < tdi_rsi < 50
        ):
            short_score += 3
            short_reasons.append(
                "TDI aşağı"
            )
        # ADX
        if adx15 >= 20:
            if minus_di > plus_di:
                short_score += 6
                short_reasons.append(
                    f"ADX {adx15:.0f}"
                )
        if adx1h >= 20:
            if minus_di1h > plus_di1h:
                short_score += 6
                short_reasons.append(
                    "1h ADX"
                )
        # VWAP
        if price < current_vwap:
            short_score += 5
            short_reasons.append(
                "VWAP altı"
            )
        else:
            short_score -= 3
        # Volume
        if volume_ratio >= 3:
            short_score += 10
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )
        elif volume_ratio >= 2:
            short_score += 8
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )
        elif volume_ratio >= 1.5:
            short_score += 6
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )
        # Volume acceleration
        if volume_acceleration >= 3:
            short_score += 8
            short_reasons.append(
                "Hacim ivmesi"
            )
        elif volume_acceleration >= 2:
            short_score += 5
            short_reasons.append(
                "Hacim hızlanıyor"
            )
        # Bearish breakout
        if bearish_breakout:
            short_score += 10
            short_reasons.append(
                "20 mum breakdown"
            )
        # Momentum
        if -4 <= momentum_15m <= -0.3:
            short_score += 5
            short_reasons.append(
                "Negatif momentum"
            )
        elif momentum_15m > 0:
            short_score -= 5
        # =================================================
        # HARD FILTERS
        # =================================================
        long_valid = True
        short_valid = True
        if volume_ratio < 1.2:
            long_valid = False
            short_valid = False
        if rsi1h > 78:
            long_valid = False
        if rsi1h < 22:
            short_valid = False
        if stoch > 93:
            long_valid = False
        if stoch < 7:
            short_valid = False
        # =================================================
        # NORMALIZATION
        # =================================================
        long_score = max(
            0,
            min(100, long_score)
        )
        short_score = max(
            0,
            min(100, short_score)
        )
        # =================================================
        # SIGNAL
        # =================================================
        if long_valid and long_score >= 82:
            long_signal = "🟢 GÜÇLÜ AL"
        elif long_valid and long_score >= 70:
            long_signal = "🟢 AL ADAYI"
        elif long_valid and long_score >= 62:
            long_signal = "🟡 İZLE"
        else:
            long_signal = "⚪ ZAYIF"
        if short_valid and short_score >= 82:
            short_signal = "🔴 GÜÇLÜ SAT"
        elif short_valid and short_score >= 70:
            short_signal = "🔴 SAT ADAYI"
        elif short_valid and short_score >= 62:
            short_signal = "🟡 İZLE"
        else:
            short_signal = "⚪ ZAYIF"
        # =================================================
        # ATR TARGETS
        # =================================================
        risk = current_atr * 1.5
        # LONG
        long_sl = price - risk
        long_tp1 = price + risk
        long_tp2 = price + risk * 1.5
        long_tp3 = price + risk * 2
        # SHORT
        short_sl = price + risk
        short_tp1 = price - risk
        short_tp2 = price - risk * 1.5
        short_tp3 = price - risk * 2
        # =================================================
        # PUMP RADAR
        # =================================================
        pump_score = 0
        pump_reasons = []
        # Hacim
        if volume_ratio >= 2:
            pump_score += 20
            pump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )
        elif volume_ratio >= 1.5:
            pump_score += 12
        elif volume_ratio >= 1.2:
            pump_score += 6
        # Hacim ivmesi
        if volume_acceleration >= 3:
            pump_score += 20
            pump_reasons.append(
                "Hacim patlaması"
            )
        elif volume_acceleration >= 2:
            pump_score += 12
            pump_reasons.append(
                "Hacim hızlanması"
            )
        # Momentum
        if momentum_15m >= 3:
            pump_score += 20
            pump_reasons.append(
                f"15m momentum +{momentum_15m:.1f}%"
            )
        elif momentum_15m >= 1.5:
            pump_score += 12
            pump_reasons.append(
                "Momentum artıyor"
            )
        elif momentum_15m >= 0.7:
            pump_score += 6
        # Breakout
        if bullish_breakout:
            pump_score += 20
            pump_reasons.append(
                "Breakout"
            )
        # ADX
        if adx15 >= 25:
            pump_score += 10
            pump_reasons.append(
                f"ADX {adx15:.0f}"
            )
        # VWAP
        if price > current_vwap:
            pump_score += 5
        # RSI
        # Pump başlangıcında RSI'nin
        # 50-75 arasında olması daha güzel.
        if 50 <= rsi15 <= 75:
            pump_score += 5
        pump_score = max(
            0,
            min(100, pump_score)
        )
        pump_signal = None
        if pump_score >= 70:
            pump_signal = "🚀 PUMP RADAR"
        elif pump_score >= 60:
            pump_signal = "⚡ HAREKETLENİYOR"
        # =================================================
        # RETURN
        # =================================================
        return {
            "symbol": symbol,
            "price": price,
            "long_score": long_score,
            "long_signal": long_signal,
            "long_reasons": long_reasons,
            "long_warnings": long_warnings,
            "short_score": short_score,
            "short_signal": short_signal,
            "short_reasons": short_reasons,
            "short_warnings": short_warnings,
            "pump_score": pump_score,
            "pump_signal": pump_signal,
            "pump_reasons": pump_reasons,
            "rsi15": rsi15,
            "rsi1h": rsi1h,
            "rsi4h": rsi4h,
            "stoch": stoch,
            "volume": volume_ratio,
            "volume_acceleration":
                volume_acceleration,
            "momentum":
                momentum_15m,
            "adx": adx15,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "vwap":
                current_vwap,
            "breakout":
                bullish_breakout,
            "breakdown":
                bearish_breakout,
            "long_sl": long_sl,
            "long_tp1": long_tp1,
            "long_tp2": long_tp2,
            "long_tp3": long_tp3,
            "short_sl": short_sl,
            "short_tp1": short_tp1,
            "short_tp2": short_tp2,
            "short_tp3": short_tp3
        }
    except Exception as e:
        print(
            f"{symbol} analiz hatası: {e}"
        )
        return None
# =========================================================
# MAIN
# =========================================================
def main():
    print(
        "🚀 GELİŞMİŞ BINANCE "
        "LONG + SHORT + PUMP SCANNER"
    )
    tickers = get(
        BINANCE + "/api/v3/ticker/24hr"
    )
    candidates = []
    for ticker in tickers:
        symbol = ticker["symbol"]
        if not symbol.endswith("USDT"):
            continue
        if stablecoin_pair(symbol):
            continue
        if any(
            x in symbol
            for x in [
                "UPUSDT",
                "DOWNUSDT",
                "BULLUSDT",
                "BEARUSDT"
            ]
        ):
            continue
        try:
            quote_volume = float(
                ticker["quoteVolume"]
            )
            if quote_volume < 5000000:
                continue
            candidates.append(
                (
                    symbol,
                    quote_volume
                )
            )
        except Exception:
            continue
    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )
    candidates = candidates[:MAX_COINS]
    print(
        f"{len(candidates)} coin analiz edilecek."
    )
    results = []
    for symbol, _ in candidates:
        print(
            f"Analiz: {symbol}"
        )
        result = analyze(symbol)
        if result:
            results.append(result)
    # =====================================================
    # LONG
    # =====================================================
    longs = [
        x for x in results
        if x["long_score"] >= 70
    ]
    longs.sort(
        key=lambda x: x["long_score"],
        reverse=True
    )
    longs = longs[:5]
    # =====================================================
    # SHORT
    # =====================================================
    shorts = [
        x for x in results
        if x["short_score"] >= 70
    ]
    shorts.sort(
        key=lambda x: x["short_score"],
        reverse=True
    )
    shorts = shorts[:5]
    # =====================================================
    # PUMP RADAR
    # =====================================================
    pumps = [
        x for x in results
        if x["pump_score"] >= 60
    ]
    pumps.sort(
        key=lambda x: x["pump_score"],
        reverse=True
    )
    pumps = pumps[:5]
    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )
    # =====================================================
    # MESSAGE
    # =====================================================
    message = (
        "🚨 GELİŞMİŞ BINANCE "
        "LONG + SHORT TARAMASI\n\n"
        f"🕐 {now}\n"
        "📊 15m + 1h + 4h\n"
        "🧠 RSI • Stoch RSI • MACD • EMA\n"
        "📈 BB • TDI • OBV • Supertrend\n"
        "📐 ADX • DI • VWAP\n"
        "🔥 Volume Acceleration\n"
        "💥 Breakout Detection\n"
        "🎯 ATR + R/R hedefleme\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    # =====================================================
    # LONG
    # =====================================================
    message += (
        "📈 LONG FIRSATLARI\n\n"
    )
    if not longs:
        message += (
            "🟡 Şu anda trade edilebilir "
            "LONG sinyali yok.\n\n"
        )
    else:
        for i, coin in enumerate(
            longs,
            1
        ):
            message += (
                f"🏆 {i}. "
                f"{coin['symbol']}\n"
                f"{coin['long_signal']}\n"
                f"⭐ Sinyal gücü: "
                f"{coin['long_score']}/100\n\n"
                f"💰 Giriş: "
                f"{price_format(coin['price'])}\n"
                f"RSI: "
                f"{coin['rsi15']:.1f} "
                f"| 1h: "
                f"{coin['rsi1h']:.1f} "
                f"| 4h: "
                f"{coin['rsi4h']:.1f}\n"
                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"
                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acceleration']:.1f}\n"
                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"
                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"
                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"
                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"
                f"🧠 Pozitif: "
                f"{', '.join(coin['long_reasons'][:9])}\n"
            )
            if coin["long_warnings"]:
                message += (
                    "⚠️ "
                    + ", ".join(
                        coin["long_warnings"][:4]
                    )
                    + "\n"
                )
            message += (
                f"\n🛑 SL: "
                f"{price_format(coin['long_sl'])}\n"
                f"🎯 TP1: "
                f"{price_format(coin['long_tp1'])}\n"
                f"🎯 TP2: "
                f"{price_format(coin['long_tp2'])}\n"
                f"🎯 TP3: "
                f"{price_format(coin['long_tp3'])}\n"
                "📐 R/R: 1 : 2\n\n"
            )
    message += (
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    # =====================================================
    # SHORT
    # =====================================================
    message += (
        "📉 SHORT FIRSATLARI\n\n"
    )
    if not shorts:
        message += (
            "🟡 Şu anda trade edilebilir "
            "SHORT sinyali yok.\n\n"
        )
    else:
        for i, coin in enumerate(
            shorts,
            1
        ):
            message += (
                f"🏆 {i}. "
                f"{coin['symbol']}\n"
                f"{coin['short_signal']}\n"
                f"⭐ Sinyal gücü: "
                f"{coin['short_score']}/100\n\n"
                f"💰 Giriş: "
                f"{price_format(coin['price'])}\n"
                f"RSI: "
                f"{coin['rsi15']:.1f} "
                f"| 1h: "
                f"{coin['rsi1h']:.1f} "
                f"| 4h: "
                f"{coin['rsi4h']:.1f}\n"
                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"
                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acceleration']:.1f}\n"
                f"📉 Momentum: "
                f"{coin['momentum']:+.1f}%\n"
                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"
                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"
                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"
                f"🧠 Pozitif: "
                f"{', '.join(coin['short_reasons'][:9])}\n"
            )
            if coin["short_warnings"]:
                message += (
                    "⚠️ "
                    + ", ".join(
                        coin["short_warnings"][:4]
                    )
                    + "\n"
                )
            message += (
                f"\n🛑 SL: "
                f"{price_format(coin['short_sl'])}\n"
                f"🎯 TP1: "
                f"{price_format(coin['short_tp1'])}\n"
                f"🎯 TP2: "
                f"{price_format(coin['short_tp2'])}\n"
                f"🎯 TP3: "
                f"{price_format(coin['short_tp3'])}\n"
                "📐 R/R: 1 : 2\n\n"
            )
    message += (
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    # =====================================================
    # PUMP RADAR
    # =====================================================
    message += (
        "🚀 PUMP RADAR\n\n"
    )
    if not pumps:
        message += (
            "🟡 Şu anda belirgin "
            "pump başlangıcı yok.\n\n"
        )
    else:
        for i, coin in enumerate(
            pumps,
            1
        ):
            message += (
                f"🚀 {i}. "
                f"{coin['symbol']}\n"
                f"{coin['pump_signal']}\n"
                f"⭐ Pump gücü: "
                f"{coin['pump_score']}/100\n\n"
                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"
                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"
                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acceleration']:.1f}\n"
                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"
                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"
                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"
                f"🧠 "
                f"{', '.join(coin['pump_reasons'])}\n\n"
            )
    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Teknik sinyal sistemidir. "
        "Yatırım tavsiyesi değildir."
    )
    print(message)
    send_telegram(message)
# =========================================================
# START
# =========================================================
if __name__ == "__main__":
    main()
