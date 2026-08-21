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
# INDICATORS
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
# ADX + DI
# =========================================================

def adx_di(high, low, close, period=14):

    if len(close) < period * 2 + 5:
        return 0, 0, 0

    tr_list = []
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

        tr_list.append(tr)

        plus_dm.append(
            up_move if up_move > down_move and up_move > 0 else 0
        )

        minus_dm.append(
            down_move if down_move > up_move and down_move > 0 else 0
        )

    if len(tr_list) < period:
        return 0, 0, 0

    atr_value = sum(tr_list[-period:]) / period

    if atr_value == 0:
        return 0, 0, 0

    plus_di = (
        sum(plus_dm[-period:]) / period
    ) / atr_value * 100

    minus_di = (
        sum(minus_dm[-period:]) / period
    ) / atr_value * 100

    dx_values = []

    for i in range(
        max(0, len(tr_list) - period * 2),
        len(tr_list)
    ):

        tr_sum = sum(
            tr_list[max(0, i - period + 1):i + 1]
        )

        plus_sum = sum(
            plus_dm[max(0, i - period + 1):i + 1]
        )

        minus_sum = sum(
            minus_dm[max(0, i - period + 1):i + 1]
        )

        if tr_sum == 0:
            continue

        pdi = plus_sum / tr_sum * 100
        mdi = minus_sum / tr_sum * 100

        denominator = pdi + mdi

        if denominator == 0:
            continue

        dx = abs(pdi - mdi) / denominator * 100
        dx_values.append(dx)

    if not dx_values:
        return 0, plus_di, minus_di

    adx_value = sum(dx_values[-period:]) / min(
        period,
        len(dx_values)
    )

    return adx_value, plus_di, minus_di


# =========================================================
# VWAP
# =========================================================

def vwap(high, low, close, volume, period=50):

    start = max(0, len(close) - period)

    cumulative_price_volume = 0
    cumulative_volume = 0

    for i in range(start, len(close)):

        typical_price = (
            high[i] + low[i] + close[i]
        ) / 3

        cumulative_price_volume += (
            typical_price * volume[i]
        )

        cumulative_volume += volume[i]

    if cumulative_volume == 0:
        return close[-1]

    return (
        cumulative_price_volume
        /
        cumulative_volume
    )


# =========================================================
# SUPERTREND
# =========================================================

def supertrend(high, low, close, period=10, multiplier=3):

    if len(close) < period + 2:
        return False

    atr_value = atr(
        high,
        low,
        close,
        period
    )

    hl2 = (
        high[-1] + low[-1]
    ) / 2

    lower_band = (
        hl2 - multiplier * atr_value
    )

    return close[-1] > lower_band


# =========================================================
# PIVOTS
# =========================================================

def pivot_highs(values, lookback=3):

    pivots = []

    for i in range(
        lookback,
        len(values) - lookback
    ):

        current = values[i]

        left = values[
            i - lookback:i
        ]

        right = values[
            i + 1:i + lookback + 1
        ]

        if current >= max(left) and current >= max(right):
            pivots.append(
                (i, current)
            )

    return pivots


def pivot_lows(values, lookback=3):

    pivots = []

    for i in range(
        lookback,
        len(values) - lookback
    ):

        current = values[i]

        left = values[
            i - lookback:i
        ]

        right = values[
            i + 1:i + lookback + 1
        ]

        if current <= min(left) and current <= min(right):
            pivots.append(
                (i, current)
            )

    return pivots


# =========================================================
# FORMATION ENGINE
# =========================================================

def detect_bull_flag(close, high, low, volume):

    if len(close) < 40:
        return None

    pole_start = close[-35]
    pole_end = close[-20]

    pole_gain = (
        pole_end / pole_start - 1
    ) * 100

    if pole_gain < 3:
        return None

    flag_high = max(close[-20:-1])
    flag_low = min(close[-20:-1])

    flag_range = (
        flag_high - flag_low
    ) / flag_high * 100

    if flag_range > 8:
        return None

    recent_high = max(close[-10:-1])

    current = close[-1]

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    if avg_volume <= 0:
        return None

    volume_ratio = (
        volume[-1] / avg_volume
    )

    if current > recent_high and volume_ratio >= 1.5:

        return {
            "name": "🚩 BULL FLAG BREAKOUT KIRILDI",
            "direction": "LONG",
            "level": recent_high
        }

    return None


def detect_bear_flag(close, high, low, volume):

    if len(close) < 40:
        return None

    pole_start = close[-35]
    pole_end = close[-20]

    pole_drop = (
        1 - pole_end / pole_start
    ) * 100

    if pole_drop < 3:
        return None

    flag_high = max(close[-20:-1])
    flag_low = min(close[-20:-1])

    flag_range = (
        flag_high - flag_low
    ) / flag_high * 100

    if flag_range > 8:
        return None

    recent_low = min(close[-10:-1])

    current = close[-1]

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    if avg_volume <= 0:
        return None

    volume_ratio = (
        volume[-1] / avg_volume
    )

    if current < recent_low and volume_ratio >= 1.5:

        return {
            "name": "🚩 BEAR FLAG BREAKDOWN KIRILDI",
            "direction": "SHORT",
            "level": recent_low
        }

    return None


def detect_ascending_triangle(close, high, low, volume):

    if len(close) < 50:
        return None

    recent_highs = high[-30:-1]
    recent_lows = low[-30:-1]

    resistance = max(recent_highs)

    lower_half = min(
        recent_lows[:15]
    )

    upper_half = min(
        recent_lows[15:]
    )

    rising_lows = (
        upper_half > lower_half
    )

    current = close[-1]

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    volume_ratio = (
        volume[-1] / avg_volume
        if avg_volume > 0 else 0
    )

    if (
        rising_lows
        and current > resistance
        and volume_ratio >= 1.5
    ):

        return {
            "name": "🔺 ASCENDING TRIANGLE BREAKOUT KIRILDI",
            "direction": "LONG",
            "level": resistance
        }

    return None


def detect_descending_triangle(close, high, low, volume):

    if len(close) < 50:
        return None

    recent_highs = high[-30:-1]
    recent_lows = low[-30:-1]

    support = min(recent_lows)

    upper_half = max(
        recent_highs[:15]
    )

    lower_half = max(
        recent_highs[15:]
    )

    falling_highs = (
        lower_half < upper_half
    )

    current = close[-1]

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    volume_ratio = (
        volume[-1] / avg_volume
        if avg_volume > 0 else 0
    )

    if (
        falling_highs
        and current < support
        and volume_ratio >= 1.5
    ):

        return {
            "name": "🔻 DESCENDING TRIANGLE BREAKDOWN KIRILDI",
            "direction": "SHORT",
            "level": support
        }

    return None


def detect_cup_handle(close, volume):

    if len(close) < 80:
        return None

    window = close[-70:]

    left = window[:20]
    middle = window[20:50]
    right = window[50:60]
    handle = window[60:]

    left_high = max(left)
    right_high = max(right)

    bottom = min(middle)

    neckline = min(
        left_high,
        right_high
    )

    symmetry = abs(
        left_high - right_high
    ) / neckline

    depth = (
        neckline - bottom
    ) / neckline

    if symmetry > 0.06:
        return None

    if depth < 0.08 or depth > 0.45:
        return None

    if len(handle) < 5:
        return None

    handle_low = min(handle)

    if (
        handle_low < bottom
        or handle_low < neckline * 0.88
    ):
        return None

    current = close[-1]

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    volume_ratio = (
        volume[-1] / avg_volume
        if avg_volume > 0 else 0
    )

    if (
        current > neckline
        and volume_ratio >= 1.5
    ):

        return {
            "name": "🥣 CUP & HANDLE BREAKOUT KIRILDI",
            "direction": "LONG",
            "level": neckline
        }

    return None


def detect_inverse_cup_handle(close, volume):

    if len(close) < 80:
        return None

    window = close[-70:]

    left = window[:20]
    middle = window[20:50]
    right = window[50:60]
    handle = window[60:]

    left_low = min(left)
    right_low = min(right)

    top = max(middle)

    neckline = max(
        left_low,
        right_low
    )

    symmetry = abs(
        left_low - right_low
    ) / max(neckline, 1e-12)

    depth = (
        top - neckline
    ) / max(top, 1e-12)

    if symmetry > 0.06:
        return None

    if depth < 0.08 or depth > 0.45:
        return None

    handle_high = max(handle)

    if (
        handle_high > top
        or handle_high > neckline * 1.12
    ):
        return None

    current = close[-1]

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    volume_ratio = (
        volume[-1] / avg_volume
        if avg_volume > 0 else 0
    )

    if (
        current < neckline
        and volume_ratio >= 1.5
    ):

        return {
            "name": "🙃 INVERSE CUP & HANDLE BREAKDOWN KIRILDI",
            "direction": "SHORT",
            "level": neckline
        }

    return None


def detect_range_breakout(close, high, low, volume):

    if len(close) < 35:
        return None

    resistance = max(
        high[-25:-1]
    )

    support = min(
        low[-25:-1]
    )

    current = close[-1]

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    if avg_volume <= 0:
        return None

    volume_ratio = (
        volume[-1] / avg_volume
    )

    if (
        current > resistance
        and volume_ratio >= 2
    ):

        return {
            "name": "📦 RANGE BREAKOUT KIRILDI",
            "direction": "LONG",
            "level": resistance
        }

    if (
        current < support
        and volume_ratio >= 2
    ):

        return {
            "name": "📦 RANGE BREAKDOWN KIRILDI",
            "direction": "SHORT",
            "level": support
        }

    return None


def detect_patterns(close, high, low, volume):

    patterns = []

    detectors = [
        detect_cup_handle,
        detect_inverse_cup_handle
    ]

    for detector in detectors:

        try:

            result = detector(
                close,
                volume
            )

            if result:
                patterns.append(result)

        except Exception:
            pass

    try:

        result = detect_bull_flag(
            close,
            high,
            low,
            volume
        )

        if result:
            patterns.append(result)

    except Exception:
        pass

    try:

        result = detect_bear_flag(
            close,
            high,
            low,
            volume
        )

        if result:
            patterns.append(result)

    except Exception:
        pass

    try:

        result = detect_ascending_triangle(
            close,
            high,
            low,
            volume
        )

        if result:
            patterns.append(result)

    except Exception:
        pass

    try:

        result = detect_descending_triangle(
            close,
            high,
            low,
            volume
        )

        if result:
            patterns.append(result)

    except Exception:
        pass

    try:

        result = detect_range_breakout(
            close,
            high,
            low,
            volume
        )

        if result:
            patterns.append(result)

    except Exception:
        pass

    return patterns


# =========================================================
# PUMP / DUMP RADAR
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

    if len(close) < 30:
        return None

    price = close[-1]

    momentum = (
        price / close[-5] - 1
    ) * 100

    avg_volume = sum(
        volume[-21:-1]
    ) / 20

    if avg_volume <= 0:
        return None

    volume_ratio = (
        volume[-1] / avg_volume
    )

    previous_avg = sum(
        volume[-11:-1]
    ) / 10

    if previous_avg <= 0:
        volume_acceleration = 1

    else:
        volume_acceleration = (
            volume[-1] / previous_avg
        )

    stoch = stoch_rsi(close)

    pump_score = 0

    if momentum >= 3:
        pump_score += 25
    elif momentum >= 2:
        pump_score += 15
    elif momentum >= 1:
        pump_score += 8

    if volume_ratio >= 5:
        pump_score += 25
    elif volume_ratio >= 3:
        pump_score += 20
    elif volume_ratio >= 2:
        pump_score += 12

    if volume_acceleration >= 5:
        pump_score += 20
    elif volume_acceleration >= 3:
        pump_score += 15
    elif volume_acceleration >= 2:
        pump_score += 10

    if adx_value >= 35:
        pump_score += 15

    if plus_di > minus_di:
        pump_score += 10

    if stoch >= 90:
        pump_score += 5

    if pump_score >= 60:

        return {
            "type": "PUMP",
            "score": min(100, pump_score),
            "momentum": momentum,
            "volume": volume_ratio,
            "acceleration": volume_acceleration,
            "adx": adx_value,
            "stoch": stoch
        }

    dump_score = 0

    if momentum <= -3:
        dump_score += 25
    elif momentum <= -2:
        dump_score += 15
    elif momentum <= -1:
        dump_score += 8

    if volume_ratio >= 5:
        dump_score += 25
    elif volume_ratio >= 3:
        dump_score += 20
    elif volume_ratio >= 2:
        dump_score += 12

    if volume_acceleration >= 5:
        dump_score += 20
    elif volume_acceleration >= 3:
        dump_score += 15
    elif volume_acceleration >= 2:
        dump_score += 10

    if adx_value >= 35:
        dump_score += 15

    if minus_di > plus_di:
        dump_score += 10

    if stoch <= 10:
        dump_score += 5

    if dump_score >= 60:

        return {
            "type": "DUMP",
            "score": min(100, dump_score),
            "momentum": momentum,
            "volume": volume_ratio,
            "acceleration": volume_acceleration,
            "adx": adx_value,
            "stoch": stoch
        }

    return None


# =========================================================
# FORMAT
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

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        rsi15 = rsi(close15)
        rsi1h = rsi(close1h)
        rsi4h = rsi(close4h)

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)

        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)

        # -------------------------------------------------
        # MACD
        # -------------------------------------------------

        macd15, signal15, hist15 = macd(close15)
        macd1h, signal1h, hist1h = macd(close1h)

        # -------------------------------------------------
        # STOCH
        # -------------------------------------------------

        stoch = stoch_rsi(close15)

        # -------------------------------------------------
        # BB
        # -------------------------------------------------

        upper, middle, lower = bollinger(
            close15
        )

        # -------------------------------------------------
        # OBV
        # -------------------------------------------------

        obv_values = obv(
            close15,
            vol15
        )

        obv_positive = (
            len(obv_values) >= 6
            and
            obv_values[-1] > obv_values[-5]
        )

        # -------------------------------------------------
        # ATR
        # -------------------------------------------------

        atr_value = atr(
            high15,
            low15,
            close15
        )

        # -------------------------------------------------
        # ADX / DI
        # -------------------------------------------------

        adx_value, plus_di, minus_di = adx_di(
            high15,
            low15,
            close15
        )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        current_vwap = vwap(
            high15,
            low15,
            close15,
            vol15
        )

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        avg_volume = sum(
            vol15[-21:-1]
        ) / 20

        if avg_volume <= 0:
            return None

        volume_ratio = (
            vol15[-1] / avg_volume
        )

        previous_avg = sum(
            vol15[-11:-1]
        ) / 10

        volume_acceleration = (
            vol15[-1] / previous_avg
            if previous_avg > 0 else 1
        )

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        momentum = (
            price / close15[-5] - 1
        ) * 100

        # -------------------------------------------------
        # PATTERNS
        # -------------------------------------------------

        patterns = detect_patterns(
            close15,
            high15,
            low15,
            vol15
        )

        long_patterns = [
            p for p in patterns
            if p["direction"] == "LONG"
        ]

        short_patterns = [
            p for p in patterns
            if p["direction"] == "SHORT"
        ]

        # -------------------------------------------------
        # LONG SCORE
        # -------------------------------------------------

        long_score = 0
        long_reasons = []

        if 50 <= rsi15 <= 68:
            long_score += 8
            long_reasons.append("RSI ideal")

        if 50 <= rsi1h <= 70:
            long_score += 8
            long_reasons.append("1h RSI")

        if 45 <= rsi4h <= 70:
            long_score += 7
            long_reasons.append("4h RSI")

        if price > ema9 > ema21:
            long_score += 10
            long_reasons.append("EMA9/21")

        if price > ema50:
            long_score += 6
            long_reasons.append("EMA50")

        if (
            price > ema21_4h
            and ema21_4h > ema50_4h
        ):
            long_score += 10
            long_reasons.append("4h trend")

        if macd1h > signal1h:
            long_score += 8
            long_reasons.append("1h MACD")

        if 20 <= stoch <= 80:
            long_score += 6
            long_reasons.append("Stoch RSI")

        if middle < price < upper:
            long_score += 4
            long_reasons.append("Bollinger")

        if obv_positive:
            long_score += 5
            long_reasons.append("OBV")

        if price > current_vwap:
            long_score += 6
            long_reasons.append("VWAP")

        if adx_value >= 25 and plus_di > minus_di:
            long_score += 8
            long_reasons.append("ADX/DI")

        if volume_ratio >= 3:
            long_score += 10

        elif volume_ratio >= 2:
            long_score += 7

        elif volume_ratio >= 1.5:
            long_score += 4

        if volume_acceleration >= 3:
            long_score += 6
            long_reasons.append("Volume Acceleration")

        if 0.5 <= momentum <= 5:
            long_score += 7
            long_reasons.append("Momentum")

        # Formasyon kırılımı büyük bonus
        if long_patterns:

            long_score += 15

            long_reasons.append(
                long_patterns[0]["name"]
            )

        # -------------------------------------------------
        # SHORT SCORE
        # -------------------------------------------------

        short_score = 0
        short_reasons = []

        if 32 <= rsi15 <= 50:
            short_score += 8
            short_reasons.append("RSI zayıf")

        if 30 <= rsi1h <= 50:
            short_score += 8
            short_reasons.append("1h RSI")

        if 30 <= rsi4h <= 55:
            short_score += 7
            short_reasons.append("4h RSI")

        if price < ema9 < ema21:
            short_score += 10
            short_reasons.append("EMA9/21")

        if price < ema50:
            short_score += 6
            short_reasons.append("EMA50")

        if (
            price < ema21_4h
            and ema21_4h < ema50_4h
        ):
            short_score += 10
            short_reasons.append("4h downtrend")

        if macd1h < signal1h:
            short_score += 8
            short_reasons.append("1h MACD")

        if stoch < 80:
            short_score += 5
            short_reasons.append("Stoch RSI")

        if lower < price < middle:
            short_score += 4
            short_reasons.append("Bollinger")

        if not obv_positive:
            short_score += 5
            short_reasons.append("OBV")

        if price < current_vwap:
            short_score += 6
            short_reasons.append("VWAP")

        if adx_value >= 25 and minus_di > plus_di:
            short_score += 8
            short_reasons.append("ADX/DI")

        if volume_ratio >= 3:
            short_score += 10

        elif volume_ratio >= 2:
            short_score += 7

        elif volume_ratio >= 1.5:
            short_score += 4

        if volume_acceleration >= 3:
            short_score += 6
            short_reasons.append("Volume Acceleration")

        if -5 <= momentum <= -0.5:
            short_score += 7
            short_reasons.append("Momentum")

        if short_patterns:

            short_score += 15

            short_reasons.append(
                short_patterns[0]["name"]
            )

        # -------------------------------------------------
        # HARD FILTERS
        # -------------------------------------------------

        if volume_ratio < 1.3:

            long_score -= 15
            short_score -= 15

        if adx_value < 18:

            long_score -= 8
            short_score -= 8

        if stoch > 92:

            long_score -= 10

        if stoch < 8:

            short_score -= 10

        # -------------------------------------------------
        # PUMP / DUMP
        # -------------------------------------------------

        radar = pump_dump_radar(
            close15,
            high15,
            low15,
            vol15,
            adx_value,
            plus_di,
            minus_di
        )

        # -------------------------------------------------
        # SIGNAL THRESHOLD
        # -------------------------------------------------

        long_score = max(
            0,
            min(100, long_score)
        )

        short_score = max(
            0,
            min(100, short_score)
        )

        long_signal = None
        short_signal = None

        # Artık AL ADAYI yok.
        # Güçlü AL için ciddi teyit gerekiyor.

        if (
            long_score >= 85
            and volume_ratio >= 1.5
            and adx_value >= 20
            and plus_di > minus_di
            and price > current_vwap
            and momentum > 0
        ):

            long_signal = "🟢 GÜÇLÜ AL"

        if (
            short_score >= 85
            and volume_ratio >= 1.5
            and adx_value >= 20
            and minus_di > plus_di
            and price < current_vwap
            and momentum < 0
        ):

            short_signal = "🔴 GÜÇLÜ SAT"

        # -------------------------------------------------
        # ATR TARGETS
        # -------------------------------------------------

        if atr_value <= 0:
            return None

        risk = atr_value * 1.5

        long_sl = price - risk
        long_tp1 = price + risk
        long_tp2 = price + risk * 1.5
        long_tp3 = price + risk * 2

        short_sl = price + risk
        short_tp1 = price - risk
        short_tp2 = price - risk * 1.5
        short_tp3 = price - risk * 2

        return {
            "symbol": symbol,
            "price": price,

            "long_score": long_score,
            "short_score": short_score,

            "long_signal": long_signal,
            "short_signal": short_signal,

            "long_reasons": long_reasons,
            "short_reasons": short_reasons,

            "rsi15": rsi15,
            "rsi1h": rsi1h,
            "rsi4h": rsi4h,

            "stoch": stoch,

            "volume": volume_ratio,
            "volume_acceleration": volume_acceleration,

            "momentum": momentum,

            "adx": adx_value,
            "plus_di": plus_di,
            "minus_di": minus_di,

            "vwap": current_vwap,

            "patterns": patterns,

            "radar": radar,

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
        "🚀 GELİŞMİŞ "
        "BINANCE LONG + SHORT SCANNER"
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

        "🥣 Cup & Handle\n"

        "🚩 Bull/Bear Flag\n"

        "🔺 Triangle Patterns\n"

        "🎯 ATR + R/R hedefleme\n"

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

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"
            )

            if coin["long_reasons"]:

                message += (
                    "🧠 Teknik teyit: "
                    + ", ".join(
                        coin["long_reasons"][:10]
                    )
                    + "\n"
                )

            if coin["patterns"]:

                for pattern in coin["patterns"]:

                    if pattern["direction"] == "LONG":

                        message += (
                            f"\n💥 FORMASYON KIRILDI:\n"
                            f"{pattern['name']}\n"
                            f"📍 Kırılım seviyesi: "
                            f"{price_format(pattern['level'])}\n"
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

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"
            )

            if coin["short_reasons"]:

                message += (
                    "🧠 Teknik teyit: "
                    + ", ".join(
                        coin["short_reasons"][:10]
                    )
                    + "\n"
                )

            if coin["patterns"]:

                for pattern in coin["patterns"]:

                    if pattern["direction"] == "SHORT":

                        message += (
                            f"\n💥 FORMASYON KIRILDI:\n"
                            f"{pattern['name']}\n"
                            f"📍 Kırılım seviyesi: "
                            f"{price_format(pattern['level'])}\n"
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
                f"🚀 {i}. "
                f"{coin['symbol']}\n"

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
                f"💣 {i}. "
                f"{coin['symbol']}\n"

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
