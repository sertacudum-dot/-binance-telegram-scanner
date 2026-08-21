import os
import json
import urllib.request
import urllib.parse
import math
from datetime import datetime, timezone

BINANCE = "https://data-api.binance.vision"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

STABLECOINS = {
    "USDT", "USDC", "FDUSD", "USDE",
    "TUSD", "DAI", "RLUSD", "USD1", "USDD"
}


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
        data = get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        )

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
# BINANCE
# =========================================================

def get_klines(symbol, interval, limit=200):

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
# BASIC INDICATORS
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


def sma(values, period):

    if len(values) < period:
        return sum(values) / len(values)

    return sum(values[-period:]) / period


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


def rsi_series(values, period=14):

    result = []

    for i in range(period, len(values)):
        result.append(
            rsi(values[:i + 1], period)
        )

    return result


def stoch_rsi(values, period=14):

    series = rsi_series(values, period)

    if len(series) < period:
        return 50

    recent = series[-period:]

    lowest = min(recent)
    highest = max(recent)

    if highest == lowest:
        return 50

    return (
        (series[-1] - lowest)
        / (highest - lowest)
    ) * 100


# =========================================================
# MACD
# =========================================================

def macd(values):

    if len(values) < 50:
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

    if len(close) < period + 1:
        return 0

    trs = []

    for i in range(1, len(close)):

        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

        trs.append(tr)

    return sum(trs[-period:]) / period


# =========================================================
# ADX / DI
# =========================================================

def adx_di(high, low, close, period=14):

    if len(close) < period * 3:
        return 0, 0, 0

    tr = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(close)):

        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]

        tr.append(
            max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1])
            )
        )

        plus_dm.append(
            up if up > down and up > 0 else 0
        )

        minus_dm.append(
            down if down > up and down > 0 else 0
        )

    dx = []

    for i in range(period, len(tr)):

        tr_sum = sum(tr[i-period:i])

        if tr_sum == 0:
            continue

        pdi = (
            sum(plus_dm[i-period:i])
            / tr_sum
        ) * 100

        mdi = (
            sum(minus_dm[i-period:i])
            / tr_sum
        ) * 100

        denominator = pdi + mdi

        if denominator == 0:
            continue

        dx.append(
            abs(pdi - mdi)
            / denominator
            * 100
        )

    if not dx:
        return 0, 0, 0

    tr_sum = sum(tr[-period:])

    if tr_sum == 0:
        return 0, 0, 0

    plus_di = (
        sum(plus_dm[-period:])
        / tr_sum
    ) * 100

    minus_di = (
        sum(minus_dm[-period:])
        / tr_sum
    ) * 100

    adx_value = sma(dx, period)

    return adx_value, plus_di, minus_di


# =========================================================
# VWAP
# =========================================================

def vwap(high, low, close, volume, period=50):

    start = max(0, len(close) - period)

    pv = 0
    total_volume = 0

    for i in range(start, len(close)):

        typical = (
            high[i] + low[i] + close[i]
        ) / 3

        pv += typical * volume[i]
        total_volume += volume[i]

    if total_volume == 0:
        return close[-1]

    return pv / total_volume


# =========================================================
# SUPERTREND
# =========================================================

def supertrend_direction(
    high,
    low,
    close,
    period=10,
    multiplier=3
):

    if len(close) < period + 5:
        return 0

    atr_value = atr(
        high,
        low,
        close,
        period
    )

    if atr_value <= 0:
        return 0

    upper = (
        high[-1] + low[-1]
    ) / 2 + multiplier * atr_value

    lower = (
        high[-1] + low[-1]
    ) / 2 - multiplier * atr_value

    if close[-1] > upper:
        return 1

    if close[-1] < lower:
        return -1

    # Daha kullanışlı trend yaklaşımı
    ema21 = ema(close, 21)

    if close[-1] > ema21:
        return 1

    if close[-1] < ema21:
        return -1

    return 0


# =========================================================
# TDI
# =========================================================

def tdi(values):

    rsi_values = rsi_series(values, 13)

    if len(rsi_values) < 20:
        return 50, 50, 50

    price_line = rsi_values[-1]

    signal_line = sma(
        rsi_values,
        7
    )

    market_base = sma(
        rsi_values,
        34
    )

    return (
        price_line,
        signal_line,
        market_base
    )


# =========================================================
# BREAKOUT ENGINE
# =========================================================

def breakout(close, high, low, volume):

    if len(close) < 40:
        return None

    current = close[-1]

    resistance = max(
        high[-21:-1]
    )

    support = min(
        low[-21:-1]
    )

    avg_volume = sma(
        volume[:-1],
        20
    )

    if avg_volume <= 0:
        return None

    volume_ratio = (
        volume[-1] / avg_volume
    )

    candle_range = (
        high[-1] - low[-1]
    )

    if candle_range <= 0:
        return None

    body = abs(
        close[-1] - close[-2]
    )

    body_ratio = (
        body / candle_range
    )

    if (
        current > resistance
        and volume_ratio >= 1.8
        and body_ratio >= 0.45
    ):

        return {
            "direction": "LONG",
            "level": resistance,
            "volume": volume_ratio
        }

    if (
        current < support
        and volume_ratio >= 1.8
        and body_ratio >= 0.45
    ):

        return {
            "direction": "SHORT",
            "level": support,
            "volume": volume_ratio
        }

    return None


# =========================================================
# FORMATIONS
# =========================================================

def detect_flag(close, high, low, volume):

    if len(close) < 45:
        return None

    avg_volume = sma(
        volume[:-1],
        20
    )

    if avg_volume <= 0:
        return None

    volume_ratio = (
        volume[-1] / avg_volume
    )

    current = close[-1]

    # Bull pole
    pole_gain = (
        close[-20] / close[-35] - 1
    ) * 100

    flag_high = max(
        high[-15:-1]
    )

    if (
        pole_gain >= 4
        and current > flag_high
        and volume_ratio >= 1.5
    ):

        return {
            "direction": "LONG",
            "name": "🚩 BULL FLAG KIRILDI",
            "level": flag_high
        }

    # Bear pole
    pole_drop = (
        1 - close[-20] / close[-35]
    ) * 100

    flag_low = min(
        low[-15:-1]
    )

    if (
        pole_drop >= 4
        and current < flag_low
        and volume_ratio >= 1.5
    ):

        return {
            "direction": "SHORT",
            "name": "🚩 BEAR FLAG KIRILDI",
            "level": flag_low
        }

    return None


def detect_patterns(close, high, low, volume):

    patterns = []

    b = breakout(
        close,
        high,
        low,
        volume
    )

    if b:

        if b["direction"] == "LONG":

            patterns.append({
                "direction": "LONG",
                "name": "💥 RANGE BREAKOUT KIRILDI",
                "level": b["level"]
            })

        else:

            patterns.append({
                "direction": "SHORT",
                "name": "💥 RANGE BREAKDOWN KIRILDI",
                "level": b["level"]
            })

    flag = detect_flag(
        close,
        high,
        low,
        volume
    )

    if flag:
        patterns.append(flag)

    return patterns


# =========================================================
# VOLUME ENGINE
# =========================================================

def volume_metrics(volume):

    if len(volume) < 25:
        return 1, 1, 1

    avg20 = sma(
        volume[:-1],
        20
    )

    avg5 = sma(
        volume[-6:-1],
        5
    )

    current = volume[-1]

    if avg20 <= 0:
        return 1, 1, 1

    volume_ratio = (
        current / avg20
    )

    acceleration = (
        avg5 / avg20
        if avg20 > 0 else 1
    )

    recent_acceleration = (
        current / avg5
        if avg5 > 0 else 1
    )

    return (
        volume_ratio,
        acceleration,
        recent_acceleration
    )


# =========================================================
# PUMP / DUMP
# =========================================================

def pump_dump_radar(
    close,
    high,
    low,
    volume,
    adx_value,
    plus_di,
    minus_di
):

    if len(close) < 35:
        return None

    price = close[-1]

    momentum_3 = (
        price / close[-4] - 1
    ) * 100

    momentum_5 = (
        price / close[-6] - 1
    ) * 100

    volume_ratio, acceleration, recent_acceleration = (
        volume_metrics(volume)
    )

    stoch = stoch_rsi(close)

    # ---------------------------------------------
    # PUMP
    # ---------------------------------------------

    score = 0

    if momentum_3 >= 2:
        score += 20

    if momentum_5 >= 3:
        score += 15

    if volume_ratio >= 2:
        score += 20

    if acceleration >= 1.5:
        score += 15

    if recent_acceleration >= 1.5:
        score += 10

    if adx_value >= 25:
        score += 10

    if plus_di > minus_di:
        score += 10

    # Çok şişmiş hareketi ayrıca işaretle
    if momentum_5 >= 10:
        score -= 15

    if score >= 60:

        return {
            "type": "PUMP",
            "score": max(0, min(100, score)),
            "momentum": momentum_5,
            "volume": volume_ratio,
            "acceleration": acceleration,
            "adx": adx_value,
            "stoch": stoch
        }

    # ---------------------------------------------
    # DUMP
    # ---------------------------------------------

    score = 0

    if momentum_3 <= -2:
        score += 20

    if momentum_5 <= -3:
        score += 15

    if volume_ratio >= 2:
        score += 20

    if acceleration >= 1.5:
        score += 15

    if recent_acceleration >= 1.5:
        score += 10

    if adx_value >= 25:
        score += 10

    if minus_di > plus_di:
        score += 10

    if momentum_5 <= -10:
        score -= 15

    if score >= 60:

        return {
            "type": "DUMP",
            "score": max(0, min(100, score)),
            "momentum": momentum_5,
            "volume": volume_ratio,
            "acceleration": acceleration,
            "adx": adx_value,
            "stoch": stoch
        }

    return None


# =========================================================
# PRICE
# =========================================================

def price_format(value):

    if value >= 100:
        return f"{value:.2f}"

    if value >= 1:
        return f"{value:.4f}"

    if value >= 0.01:
        return f"{value:.6f}"

    return f"{value:.10f}"


def stablecoin_pair(symbol):

    base = symbol.replace("USDT", "")

    return base in STABLECOINS


# =========================================================
# ANALYSIS
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

        r15 = rsi(close15)
        r1 = rsi(close1h)
        r4 = rsi(close4h)

        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)

        ema21_1h = ema(close1h, 21)
        ema50_1h = ema(close1h, 50)

        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)

        macd15, signal15, hist15 = macd(close15)
        macd1, signal1, hist1 = macd(close1h)

        stoch = stoch_rsi(close15)

        upper, middle, lower = bollinger(
            close15
        )

        obv_values = obv(
            close15,
            vol15
        )

        obv_rising = (
            obv_values[-1]
            > obv_values[-6]
        )

        obv_falling = (
            obv_values[-1]
            < obv_values[-6]
        )

        atr_value = atr(
            high15,
            low15,
            close15
        )

        if atr_value <= 0:
            return None

        atr_percent = (
            atr_value / price
        ) * 100

        adx_value, plus_di, minus_di = adx_di(
            high15,
            low15,
            close15
        )

        current_vwap = vwap(
            high15,
            low15,
            close15,
            vol15
        )

        supertrend = supertrend_direction(
            high15,
            low15,
            close15
        )

        tdi_price, tdi_signal, tdi_base = tdi(
            close15
        )

        volume_ratio, volume_acceleration, recent_volume_acceleration = (
            volume_metrics(vol15)
        )

        momentum_3 = (
            price / close15[-4] - 1
        ) * 100

        momentum_5 = (
            price / close15[-6] - 1
        ) * 100

        patterns = detect_patterns(
            close15,
            high15,
            low15,
            vol15
        )

        # =================================================
        # MARKET REGIME
        # =================================================

        bullish_4h = (
            price > ema21_4h
            and ema21_4h > ema50_4h
        )

        bearish_4h = (
            price < ema21_4h
            and ema21_4h < ema50_4h
        )

        bullish_1h = (
            price > ema21_1h
            and ema21_1h > ema50_1h
        )

        bearish_1h = (
            price < ema21_1h
            and ema21_1h < ema50_1h
        )

        # =================================================
        # LONG SCORE
        # =================================================

        long_score = 0
        long_reasons = []

        if bullish_4h:
            long_score += 15
            long_reasons.append("4h trend")

        if bullish_1h:
            long_score += 12
            long_reasons.append("1h trend")

        if price > ema9 > ema21:
            long_score += 10
            long_reasons.append("EMA9/21")

        if price > ema50:
            long_score += 5
            long_reasons.append("EMA50")

        if 52 <= r15 <= 68:
            long_score += 7
            long_reasons.append("RSI")

        if 52 <= r1 <= 70:
            long_score += 6
            long_reasons.append("1h RSI")

        if 50 <= r4 <= 70:
            long_score += 5
            long_reasons.append("4h RSI")

        if macd1 > signal1 and hist1 > 0:
            long_score += 10
            long_reasons.append("MACD")

        if 35 <= stoch <= 82:
            long_score += 5
            long_reasons.append("Stoch RSI")

        if price > middle:
            long_score += 4
            long_reasons.append("BB")

        if price > current_vwap:
            long_score += 7
            long_reasons.append("VWAP")

        if obv_rising:
            long_score += 5
            long_reasons.append("OBV")

        if adx_value >= 25 and plus_di > minus_di:
            long_score += 10
            long_reasons.append("ADX/DI")

        if supertrend == 1:
            long_score += 7
            long_reasons.append("Supertrend")

        if tdi_price > tdi_signal > tdi_base:
            long_score += 8
            long_reasons.append("TDI")

        # ---------------------------------------------
        # VOLUME
        # ---------------------------------------------

        if volume_ratio >= 2:
            long_score += 8
            long_reasons.append("Hacim")

        elif volume_ratio >= 1.5:
            long_score += 4

        if volume_acceleration >= 1.5:
            long_score += 5
            long_reasons.append("Volume acceleration")

        # ---------------------------------------------
        # MOMENTUM
        # ---------------------------------------------

        if 0.8 <= momentum_3 <= 4:
            long_score += 7
            long_reasons.append("Momentum")

        # ---------------------------------------------
        # BREAKOUT
        # ---------------------------------------------

        long_breakout = any(
            p["direction"] == "LONG"
            for p in patterns
        )

        if long_breakout:

            long_score += 12

            long_reasons.append(
                "BREAKOUT"
            )

        # =================================================
        # LONG PENALTIES
        # =================================================

        if r15 > 75:
            long_score -= 12

        if stoch > 90:
            long_score -= 12

        if momentum_5 > 8:
            long_score -= 15

        if atr_percent < 0.25:
            long_score -= 15

        if not bullish_1h:
            long_score -= 10

        # =================================================
        # SHORT
        # =================================================

        short_score = 0
        short_reasons = []

        if bearish_4h:
            short_score += 15
            short_reasons.append("4h downtrend")

        if bearish_1h:
            short_score += 12
            short_reasons.append("1h downtrend")

        if price < ema9 < ema21:
            short_score += 10
            short_reasons.append("EMA9/21")

        if price < ema50:
            short_score += 5
            short_reasons.append("EMA50")

        if 32 <= r15 <= 48:
            short_score += 7
            short_reasons.append("RSI")

        if 30 <= r1 <= 50:
            short_score += 6
            short_reasons.append("1h RSI")

        if 30 <= r4 <= 50:
            short_score += 5
            short_reasons.append("4h RSI")

        if macd1 < signal1 and hist1 < 0:
            short_score += 10
            short_reasons.append("MACD")

        if 18 <= stoch <= 65:
            short_score += 5
            short_reasons.append("Stoch RSI")

        if price < middle:
            short_score += 4
            short_reasons.append("BB")

        if price < current_vwap:
            short_score += 7
            short_reasons.append("VWAP")

        if obv_falling:
            short_score += 5
            short_reasons.append("OBV")

        if adx_value >= 25 and minus_di > plus_di:
            short_score += 10
            short_reasons.append("ADX/DI")

        if supertrend == -1:
            short_score += 7
            short_reasons.append("Supertrend")

        if tdi_price < tdi_signal < tdi_base:
            short_score += 8
            short_reasons.append("TDI")

        if volume_ratio >= 2:
            short_score += 8
            short_reasons.append("Hacim")

        elif volume_ratio >= 1.5:
            short_score += 4

        if volume_acceleration >= 1.5:
            short_score += 5
            short_reasons.append("Volume acceleration")

        if -4 <= momentum_3 <= -0.8:
            short_score += 7
            short_reasons.append("Momentum")

        short_breakout = any(
            p["direction"] == "SHORT"
            for p in patterns
        )

        if short_breakout:

            short_score += 12

            short_reasons.append(
                "BREAKDOWN"
            )

        # =================================================
        # SHORT PENALTIES
        # =================================================

        if r15 < 25:
            short_score -= 12

        if stoch < 10:
            short_score -= 12

        if momentum_5 < -8:
            short_score -= 15

        if atr_percent < 0.25:
            short_score -= 15

        if not bearish_1h:
            short_score -= 10

        # =================================================
        # FINAL SCORE
        # =================================================

        long_score = max(
            0,
            min(99, long_score)
        )

        short_score = max(
            0,
            min(99, short_score)
        )

        # =================================================
        # REAL SIGNAL FILTER
        # =================================================

        long_signal = None
        short_signal = None

        long_confirmations = (
            bullish_1h
            and bullish_4h
            and price > current_vwap
            and plus_di > minus_di
            and adx_value >= 22
            and volume_ratio >= 1.5
            and momentum_3 >= 0.8
            and atr_percent >= 0.25
        )

        short_confirmations = (
            bearish_1h
            and bearish_4h
            and price < current_vwap
            and minus_di > plus_di
            and adx_value >= 22
            and volume_ratio >= 1.5
            and momentum_3 <= -0.8
            and atr_percent >= 0.25
        )

        # Strong AL requires either breakout
        # or exceptional multi-indicator confirmation

        if (
            long_score >= 78
            and long_confirmations
            and (
                long_breakout
                or (
                    macd1 > signal1
                    and supertrend == 1
                    and tdi_price > tdi_signal
                )
            )
        ):

            long_signal = "🟢 GÜÇLÜ AL"

        if (
            short_score >= 78
            and short_confirmations
            and (
                short_breakout
                or (
                    macd1 < signal1
                    and supertrend == -1
                    and tdi_price < tdi_signal
                )
            )
        ):

            short_signal = "🔴 GÜÇLÜ SAT"

        # =================================================
        # RADAR
        # =================================================

        radar = pump_dump_radar(
            close15,
            high15,
            low15,
            vol15,
            adx_value,
            plus_di,
            minus_di
        )

        # =================================================
        # ATR TARGETS
        # =================================================

        # Gerçek R/R = 1:2
        risk = atr_value * 1.2

        long_sl = price - risk
        long_tp1 = price + risk
        long_tp2 = price + risk * 2

        short_sl = price + risk
        short_tp1 = price - risk
        short_tp2 = price - risk * 2

        return {

            "symbol": symbol,
            "price": price,

            "long_score": long_score,
            "short_score": short_score,

            "long_signal": long_signal,
            "short_signal": short_signal,

            "long_reasons": long_reasons,
            "short_reasons": short_reasons,

            "rsi15": r15,
            "rsi1h": r1,
            "rsi4h": r4,

            "stoch": stoch,

            "volume": volume_ratio,
            "volume_acceleration": volume_acceleration,

            "momentum": momentum_3,
            "momentum5": momentum_5,

            "adx": adx_value,
            "plus_di": plus_di,
            "minus_di": minus_di,

            "vwap": current_vwap,

            "atr_percent": atr_percent,

            "supertrend": supertrend,

            "tdi": tdi_price,
            "tdi_signal": tdi_signal,

            "patterns": patterns,

            "radar": radar,

            "long_sl": long_sl,
            "long_tp1": long_tp1,
            "long_tp2": long_tp2,

            "short_sl": short_sl,
            "short_tp1": short_tp1,
            "short_tp2": short_tp2
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
        "🚀 GELİŞMİŞ BINANCE SCANNER"
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

            # Likidite filtresi
            if quote_volume < 10_000_000:
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

    # İlk 100 likit coin
    candidates = candidates[:100]

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
        if x["long_signal"] == "🟢 GÜÇLÜ AL"
    ]

    longs.sort(
        key=lambda x: x["long_score"],
        reverse=True
    )

    longs = longs[:3]

    # =====================================================
    # SHORT
    # =====================================================

    shorts = [
        x for x in results
        if x["short_signal"] == "🔴 GÜÇLÜ SAT"
    ]

    shorts.sort(
        key=lambda x: x["short_score"],
        reverse=True
    )

    shorts = shorts[:3]

    # =====================================================
    # PUMP
    # =====================================================

    pumps = [
        x for x in results
        if x["radar"]
        and x["radar"]["type"] == "PUMP"
    ]

    pumps.sort(
        key=lambda x: x["radar"]["score"],
        reverse=True
    )

    pumps = pumps[:3]

    # =====================================================
    # DUMP
    # =====================================================

    dumps = [
        x for x in results
        if x["radar"]
        and x["radar"]["type"] == "DUMP"
    ]

    dumps.sort(
        key=lambda x: x["radar"]["score"],
        reverse=True
    )

    dumps = dumps[:3]

    # =====================================================
    # MESSAGE
    # =====================================================

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )

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

        "🚩 Flag Breakout\n"

        "🎯 ATR + gerçek R/R\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # =====================================================
    # LONG
    # =====================================================

    message += "📈 LONG FIRSATLARI\n\n"

    if not longs:

        message += (
            "🟡 Şu anda trade edilebilir "
            "GÜÇLÜ LONG sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            longs,
            1
        ):

            message += (
                f"🏆 {i}. {coin['symbol']}\n"
                f"{coin['long_signal']}\n"
                f"⭐ Sinyal gücü: "
                f"{coin['long_score']}/99\n\n"

                f"💰 Giriş: "
                f"{price_format(coin['price'])}\n"

                f"RSI: {coin['rsi15']:.1f}"
                f" | 1h: {coin['rsi1h']:.1f}"
                f" | 4h: {coin['rsi4h']:.1f}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acceleration']:.1f}\n"

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"

                f"📊 ATR: "
                f"{coin['atr_percent']:.2f}%\n"
            )

            if coin["long_reasons"]:

                message += (
                    "🧠 Teyit: "
                    + ", ".join(
                        coin["long_reasons"][:10]
                    )
                    + "\n"
                )

            for pattern in coin["patterns"]:

                if pattern["direction"] == "LONG":

                    message += (
                        "\n💥 FORMASYON KIRILDI:\n"
                        f"{pattern['name']}\n"
                        f"📍 Seviye: "
                        f"{price_format(pattern['level'])}\n"
                    )

            message += (
                f"\n🛑 SL: "
                f"{price_format(coin['long_sl'])}\n"

                f"🎯 TP1: "
                f"{price_format(coin['long_tp1'])}\n"

                f"🎯 TP2: "
                f"{price_format(coin['long_tp2'])}\n"

                "📐 R/R: 1 : 2\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # =====================================================
    # SHORT
    # =====================================================

    message += "📉 SHORT FIRSATLARI\n\n"

    if not shorts:

        message += (
            "🟡 Şu anda trade edilebilir "
            "GÜÇLÜ SHORT sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            shorts,
            1
        ):

            message += (
                f"🏆 {i}. {coin['symbol']}\n"
                f"{coin['short_signal']}\n"
                f"⭐ Sinyal gücü: "
                f"{coin['short_score']}/99\n\n"

                f"💰 Giriş: "
                f"{price_format(coin['price'])}\n"

                f"RSI: {coin['rsi15']:.1f}"
                f" | 1h: {coin['rsi1h']:.1f}"
                f" | 4h: {coin['rsi4h']:.1f}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acceleration']:.1f}\n"

                f"📉 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"

                f"📊 ATR: "
                f"{coin['atr_percent']:.2f}%\n"
            )

            if coin["short_reasons"]:

                message += (
                    "🧠 Teyit: "
                    + ", ".join(
                        coin["short_reasons"][:10]
                    )
                    + "\n"
                )

            for pattern in coin["patterns"]:

                if pattern["direction"] == "SHORT":

                    message += (
                        "\n💥 FORMASYON KIRILDI:\n"
                        f"{pattern['name']}\n"
                        f"📍 Seviye: "
                        f"{price_format(pattern['level'])}\n"
                    )

            message += (
                f"\n🛑 SL: "
                f"{price_format(coin['short_sl'])}\n"

                f"🎯 TP1: "
                f"{price_format(coin['short_tp1'])}\n"

                f"🎯 TP2: "
                f"{price_format(coin['short_tp2'])}\n"

                "📐 R/R: 1 : 2\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # =====================================================
    # PUMP RADAR
    # =====================================================

    message += "🚀 PUMP RADAR\n\n"

    if not pumps:

        message += (
            "🟡 Şu anda güçlü pump hareketi yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            pumps,
            1
        ):

            radar = coin["radar"]

            message += (
                f"🚀 {i}. {coin['symbol']}\n"
                f"⚡ HAREKETLENİYOR\n"
                f"⭐ Pump gücü: "
                f"{radar['score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{radar['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{radar['acceleration']:.1f}\n"

                f"🚀 Momentum: "
                f"{radar['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{radar['adx']:.1f}\n"

                f"📊 Stoch RSI: "
                f"{radar['stoch']:.1f}\n\n"
            )

    # =====================================================
    # DUMP RADAR
    # =====================================================

    message += "💣 DUMP RADAR\n\n"

    if not dumps:

        message += (
            "🟡 Şu anda güçlü dump hareketi yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            dumps,
            1
        ):

            radar = coin["radar"]

            message += (
                f"💣 {i}. {coin['symbol']}\n"
                f"⚡ DÜŞÜŞ HIZLANIYOR\n"
                f"⭐ Dump gücü: "
                f"{radar['score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{radar['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{radar['acceleration']:.1f}\n"

                f"📉 Momentum: "
                f"{radar['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{radar['adx']:.1f}\n"

                f"📊 Stoch RSI: "
                f"{radar['stoch']:.1f}\n\n"
            )

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Teknik sinyal sistemidir. "
        "Yatırım tavsiyesi değildir."
    )

    print(message)

    send_telegram(message)


if __name__ == "__main__":
    main()
