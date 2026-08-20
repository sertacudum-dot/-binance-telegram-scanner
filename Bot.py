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
# BINANCE DATA
# =========================================================

def get_klines(symbol, interval, limit=180):

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


def rsi_series(values, period=14):

    result = []

    for i in range(period, len(values)):

        result.append(
            rsi(values[:i + 1], period)
        )

    return result


def stoch_rsi(values, period=14):

    rsis = rsi_series(values, period)

    if len(rsis) < period:
        return 50

    recent = rsis[-period:]

    lowest = min(recent)
    highest = max(recent)

    if highest == lowest:
        return 50

    return (
        (rsis[-1] - lowest)
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


# =========================================================
# ATR
# =========================================================

def calculate_atr(high, low, close, period=14):

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
# ADX + DI
# =========================================================

def calculate_adx(high, low, close, period=14):

    if len(close) < period * 2:
        return 20, 0, 0

    tr_values = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(close)):

        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]

        plus = (
            up_move
            if up_move > down_move and up_move > 0
            else 0
        )

        minus = (
            down_move
            if down_move > up_move and down_move > 0
            else 0
        )

        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

        tr_values.append(tr)
        plus_dm.append(plus)
        minus_dm.append(minus)

    if len(tr_values) < period:
        return 20, 0, 0

    atr = sum(tr_values[-period:]) / period

    if atr == 0:
        return 20, 0, 0

    plus_di = (
        100
        * (sum(plus_dm[-period:]) / period)
        / atr
    )

    minus_di = (
        100
        * (sum(minus_dm[-period:]) / period)
        / atr
    )

    denominator = plus_di + minus_di

    if denominator == 0:
        dx = 0
    else:
        dx = (
            abs(plus_di - minus_di)
            / denominator
        ) * 100

    adx = dx

    return adx, plus_di, minus_di


# =========================================================
# VWAP
# =========================================================

def calculate_vwap(high, low, close, volume, period=30):

    start = max(0, len(close) - period)

    total_volume = 0
    total_price_volume = 0

    for i in range(start, len(close)):

        typical_price = (
            high[i]
            + low[i]
            + close[i]
        ) / 3

        total_price_volume += (
            typical_price * volume[i]
        )

        total_volume += volume[i]

    if total_volume == 0:
        return close[-1]

    return total_price_volume / total_volume


# =========================================================
# SUPERTREND
# =========================================================

def supertrend(high, low, close, period=10, multiplier=3):

    if len(close) < period + 2:
        return False

    trs = []

    for i in range(1, len(close)):

        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

        trs.append(tr)

    atr = sum(trs[-period:]) / period

    hl2 = (
        high[-1] + low[-1]
    ) / 2

    lower_band = hl2 - multiplier * atr

    return close[-1] > lower_band


# =========================================================
# TDI
# =========================================================

def tdi(values):

    current = rsi(values, 13)

    previous = rsi(
        values[:-1],
        13
    )

    signal = (
        current * 0.7
        + previous * 0.3
    )

    return current, signal


# =========================================================
# FORMATTING
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
# VOLUME ANALYSIS
# =========================================================

def volume_analysis(volume):

    if len(volume) < 25:
        return 1, 1, 0

    avg_volume = (
        sum(volume[-21:-1])
        / 20
    )

    if avg_volume <= 0:
        return 1, 1, 0

    current_ratio = (
        volume[-1]
        / avg_volume
    )

    previous_avg = (
        sum(volume[-6:-1])
        / 5
    )

    if previous_avg <= 0:
        acceleration = 1
    else:
        acceleration = (
            volume[-1]
            / previous_avg
        )

    return (
        current_ratio,
        acceleration,
        avg_volume
    )


# =========================================================
# BREAKOUT ANALYSIS
# =========================================================

def breakout_analysis(
    close,
    high,
    low,
    volume
):

    if len(close) < 30:
        return False, False, 0

    resistance = max(
        high[-21:-1]
    )

    support = min(
        low[-21:-1]
    )

    price = close[-1]

    previous_price = close[-2]

    breakout_up = (
        price > resistance
        and previous_price <= resistance
    )

    breakout_down = (
        price < support
        and previous_price >= support
    )

    distance_to_resistance = (
        (resistance - price)
        / price
    ) * 100

    distance_to_support = (
        (price - support)
        / price
    ) * 100

    # Erken breakout bölgesi.
    near_resistance = (
        0 <= distance_to_resistance <= 1.0
    )

    near_support = (
        0 <= distance_to_support <= 1.0
    )

    return (
        breakout_up or near_resistance,
        breakout_down or near_support,
        distance_to_resistance
    )


# =========================================================
# EARLY MOMENTUM
# =========================================================

def momentum_analysis(close):

    if len(close) < 10:
        return 0, 0

    momentum_5 = (
        close[-1]
        / close[-6]
        - 1
    ) * 100

    momentum_10 = (
        close[-1]
        / close[-11]
        - 1
    ) * 100

    return momentum_5, momentum_10


# =========================================================
# LONG / SHORT ANALYSIS
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

        long_score = 50
        short_score = 50

        long_reasons = []
        short_reasons = []

        long_warnings = []
        short_warnings = []

        # =================================================
        # RSI
        # =================================================

        r15 = rsi(close15)
        r1 = rsi(close1h)
        r4 = rsi(close4h)

        # LONG RSI
        if 50 <= r15 <= 65:
            long_score += 5
            long_reasons.append("RSI ideal")

        elif 65 < r15 <= 70:
            long_score += 2

        elif r15 > 72:
            long_score -= 7
            long_warnings.append("RSI yüksek")

        elif r15 < 40:
            long_score -= 7
            long_warnings.append("RSI zayıf")

        if 50 <= r1 <= 65:
            long_score += 5
            long_reasons.append("1h RSI")

        elif 65 < r1 <= 70:
            long_score += 2

        elif r1 > 75:
            long_score -= 12
            long_warnings.append("1h aşırı alım")

        elif r1 < 40:
            long_score -= 8

        if 45 <= r4 <= 65:
            long_score += 5
            long_reasons.append("4h RSI")

        elif 65 < r4 <= 70:
            long_score += 1

        elif r4 > 72:
            long_score -= 6
            long_warnings.append("4h RSI yüksek")

        elif r4 < 40:
            long_score -= 12
            long_warnings.append("4h RSI zayıf")

        # SHORT RSI
        if 35 <= r15 <= 50:
            short_score += 5
            short_reasons.append("RSI short bölgesi")

        elif r15 < 30:
            short_score -= 8
            short_warnings.append("RSI aşırı düşük")

        elif r15 > 70:
            short_score += 4
            short_reasons.append("RSI yüksek")

        if 35 <= r1 <= 50:
            short_score += 5
            short_reasons.append("1h RSI")

        elif r1 > 70:
            short_score += 6
            short_reasons.append("1h aşırı alım")

        elif r1 < 30:
            short_score -= 8

        if 35 <= r4 <= 55:
            short_score += 5
            short_reasons.append("4h RSI")

        elif r4 > 70:
            short_score += 6
            short_reasons.append("4h aşırı alım")

        elif r4 < 30:
            short_score -= 8

        # =================================================
        # EMA
        # =================================================

        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)

        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)

        if price > ema9 > ema21:
            long_score += 7
            long_reasons.append("EMA9/21")

        if price > ema50:
            long_score += 5
            long_reasons.append("EMA50")

        if (
            price > ema21_4h
            and ema21_4h > ema50_4h
        ):
            long_score += 8
            long_reasons.append("4h trend")

        elif price > ema50_4h:
            long_score += 3

        else:
            long_score -= 6
            long_warnings.append("4h zayıf")

        if price < ema9 < ema21:
            short_score += 7
            short_reasons.append("EMA9/21 aşağı")

        if price < ema50:
            short_score += 5
            short_reasons.append("EMA50 altında")

        if (
            price < ema21_4h
            and ema21_4h < ema50_4h
        ):
            short_score += 8
            short_reasons.append("4h düşüş trendi")

        elif price < ema50_4h:
            short_score += 3

        else:
            short_score -= 6

        # =================================================
        # MACD
        # =================================================

        macd15, sig15, hist15 = macd(close15)
        macd1, sig1, hist1 = macd(close1h)

        if macd15 > sig15 and hist15 > 0:
            long_score += 5
            long_reasons.append("MACD")

        if macd1 > sig1 and hist1 > 0:
            long_score += 7
            long_reasons.append("1h MACD")

        if macd15 < sig15 and hist15 < 0:
            short_score += 5
            short_reasons.append("MACD aşağı")

        if macd1 < sig1 and hist1 < 0:
            short_score += 7
            short_reasons.append("1h MACD")

        # =================================================
        # STOCH RSI
        # =================================================

        stoch = stoch_rsi(close15)

        if 20 <= stoch <= 80:
            long_score += 4
            short_score += 4

        elif stoch > 90:
            long_score -= 7
            long_warnings.append("Stoch RSI çok yüksek")

            short_score += 5
            short_reasons.append("Stoch RSI aşırı yüksek")

        elif stoch < 10:
            short_score -= 7
            short_warnings.append("Stoch RSI çok düşük")

            long_score += 4

        # =================================================
        # BOLLINGER
        # =================================================

        upper, middle, lower = bollinger(
            close15
        )

        if middle < price < upper:
            long_score += 3
            long_reasons.append("Bollinger")

        if lower < price < middle:
            short_score += 3
            short_reasons.append("Bollinger")

        # =================================================
        # OBV
        # =================================================

        obv_values = obv(
            close15,
            vol15
        )

        if len(obv_values) >= 6:

            if obv_values[-1] > obv_values[-5]:
                long_score += 4
                long_reasons.append("OBV")

            elif obv_values[-1] < obv_values[-5]:
                short_score += 4
                short_reasons.append("OBV düşüş")

        # =================================================
        # SUPERTREND
        # =================================================

        st15 = supertrend(
            high15,
            low15,
            close15
        )

        st1 = supertrend(
            high1h,
            low1h,
            close1h
        )

        if st15:
            long_score += 3
            long_reasons.append("Supertrend")

        else:
            short_score += 3
            short_reasons.append("Supertrend aşağı")

        if st1:
            long_score += 3
            long_reasons.append("1h Supertrend")

        else:
            short_score += 3
            short_reasons.append("1h Supertrend aşağı")

        # =================================================
        # TDI
        # =================================================

        tdi_rsi, tdi_signal = tdi(close15)

        if (
            tdi_rsi > tdi_signal
            and 45 < tdi_rsi < 70
        ):
            long_score += 3
            long_reasons.append("TDI")

        if (
            tdi_rsi < tdi_signal
            and 30 < tdi_rsi < 55
        ):
            short_score += 3
            short_reasons.append("TDI")

        # =================================================
        # MOMENTUM
        # =================================================

        momentum5, momentum10 = momentum_analysis(
            close15
        )

        # LONG
        if 0.3 <= momentum5 <= 3:
            long_score += 5
            long_reasons.append("Momentum")

        elif momentum5 > 5:
            long_score -= 5
            long_warnings.append("Hareket çok ilerlemiş")

        elif momentum5 < 0:
            long_score -= 5

        # SHORT
        if -3 <= momentum5 <= -0.3:
            short_score += 5
            short_reasons.append("Momentum")

        elif momentum5 < -5:
            short_score -= 5
            short_warnings.append("Düşüş çok ilerlemiş")

        elif momentum5 > 0:
            short_score -= 5

        # =================================================
        # VOLUME
        # =================================================

        volume_ratio, volume_acceleration, _ = (
            volume_analysis(vol15)
        )

        # LONG volume
        if volume_ratio >= 3:
            long_score += 8
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            long_score += 6
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.5:
            long_score += 4
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio < 1.0:
            long_score -= 4
            long_warnings.append("Hacim düşük")

        # SHORT volume
        if volume_ratio >= 3:
            short_score += 8
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            short_score += 6
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.5:
            short_score += 4
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        # =================================================
        # VOLUME ACCELERATION
        # =================================================

        if volume_acceleration >= 3:

            long_score += 6
            short_score += 6

            long_reasons.append(
                f"Hacim ivmesi x{volume_acceleration:.1f}"
            )

            short_reasons.append(
                f"Hacim ivmesi x{volume_acceleration:.1f}"
            )

        elif volume_acceleration >= 2:

            long_score += 4
            short_score += 4

        elif volume_acceleration >= 1.4:

            long_score += 2
            short_score += 2

        # =================================================
        # ADX + DI
        # =================================================

        adx, plus_di, minus_di = calculate_adx(
            high15,
            low15,
            close15
        )

        if adx >= 25:

            if plus_di > minus_di:

                long_score += 6
                long_reasons.append(
                    f"ADX {adx:.1f} +DI"
                )

            elif minus_di > plus_di:

                short_score += 6
                short_reasons.append(
                    f"ADX {adx:.1f} -DI"
                )

        elif adx >= 20:

            if plus_di > minus_di:
                long_score += 3

            elif minus_di > plus_di:
                short_score += 3

        # Çok yüksek ADX sonrası kovalamayı engelle
        if adx > 60:

            if momentum5 > 3:
                long_score -= 7
                long_warnings.append(
                    "Trend fazla ilerlemiş"
                )

            if momentum5 < -3:
                short_score -= 7
                short_warnings.append(
                    "Düşüş fazla ilerlemiş"
                )

        # =================================================
        # VWAP
        # =================================================

        vwap = calculate_vwap(
            high15,
            low15,
            close15,
            vol15
        )

        vwap_distance = (
            (price - vwap)
            / vwap
        ) * 100

        if price > vwap:

            long_score += 5
            long_reasons.append("VWAP üstü")

            if vwap_distance < 3:
                long_score += 2

            elif vwap_distance > 6:
                long_score -= 4
                long_warnings.append(
                    "VWAP'tan uzak"
                )

        else:

            short_score += 5
            short_reasons.append("VWAP altı")

            if vwap_distance < -6:
                short_score -= 4
                short_warnings.append(
                    "VWAP'tan uzak"
                )

        # =================================================
        # BREAKOUT
        # =================================================

        breakout_up, breakout_down, distance = (
            breakout_analysis(
                close15,
                high15,
                low15,
                vol15
            )
        )

        if breakout_up:

            long_score += 6
            long_reasons.append("Breakout")

        if breakout_down:

            short_score += 6
            short_reasons.append("Breakdown")

        # =================================================
        # EARLY BREAKOUT BONUS
        # =================================================

        resistance = max(
            high15[-21:-1]
        )

        support = min(
            low15[-21:-1]
        )

        distance_resistance = (
            (resistance - price)
            / price
        ) * 100

        distance_support = (
            (price - support)
            / price
        ) * 100

        if (
            0 <= distance_resistance <= 1.0
            and momentum5 > 0
            and volume_acceleration >= 1.4
        ):

            long_score += 6
            long_reasons.append(
                "Erken breakout bölgesi"
            )

        if (
            0 <= distance_support <= 1.0
            and momentum5 < 0
            and volume_acceleration >= 1.4
        ):

            short_score += 6
            short_reasons.append(
                "Erken breakdown bölgesi"
            )

        # =================================================
        # ANTI-CHASE FILTER
        # =================================================

        if momentum5 > 5:

            long_score -= 10
            long_warnings.append(
                "Pump zaten ilerledi"
            )

        if momentum5 < -5:

            short_score -= 10
            short_warnings.append(
                "Dump zaten ilerledi"
            )

        # =================================================
        # HARD FILTERS
        # =================================================

        # LONG minimum volume
        if volume_ratio < 1.2:
            long_score = 0

        # SHORT minimum volume
        if volume_ratio < 1.2:
            short_score = 0

        # LONG aşırı alım
        if r1 > 78:
            long_score = 0

        if stoch > 95:
            long_score = 0

        # SHORT aşırı satış
        if r1 < 25:
            short_score = 0

        if stoch < 5:
            short_score = 0

        # =================================================
        # NORMALIZE
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

        long_conditions = [

            volume_ratio >= 1.5,

            volume_acceleration >= 1.3,

            momentum5 > 0,

            r15 >= 48,

            r1 >= 48,

            r4 >= 43,

            price > ema21,

            macd1 > sig1,

            plus_di >= minus_di,

            price >= vwap * 0.995
        ]

        short_conditions = [

            volume_ratio >= 1.5,

            volume_acceleration >= 1.3,

            momentum5 < 0,

            r15 <= 52,

            r1 <= 52,

            r4 <= 57,

            price < ema21,

            macd1 < sig1,

            minus_di >= plus_di,

            price <= vwap * 1.005
        ]

        long_count = sum(
            long_conditions
        )

        short_count = sum(
            short_conditions
        )

        # LONG
        if (
            long_score >= 90
            and long_count >= 8
        ):
            long_signal = "🟢 GÜÇLÜ AL"

        elif (
            long_score >= 80
            and long_count >= 7
        ):
            long_signal = "🟢 GÜÇLÜ AL"

        elif (
            long_score >= 72
            and long_count >= 6
        ):
            long_signal = "🟢 AL ADAYI"

        elif long_score >= 65:
            long_signal = "🟡 İZLE"

        else:
            long_signal = "⚪ ZAYIF"

        # SHORT
        if (
            short_score >= 90
            and short_count >= 8
        ):
            short_signal = "🔴 GÜÇLÜ SAT"

        elif (
            short_score >= 80
            and short_count >= 7
        ):
            short_signal = "🔴 GÜÇLÜ SAT"

        elif (
            short_score >= 72
            and short_count >= 6
        ):
            short_signal = "🔴 SAT ADAYI"

        elif short_score >= 65:
            short_signal = "🟠 İZLE"

        else:
            short_signal = "⚪ ZAYIF"

        # =================================================
        # ATR
        # =================================================

        atr = calculate_atr(
            high15,
            low15,
            close15
        )

        if atr <= 0:
            return None

        risk = atr * 1.5

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

        if momentum5 >= 2:
            pump_score += 15
            pump_reasons.append(
                f"15m momentum +{momentum5:.1f}%"
            )

        if momentum5 >= 3:
            pump_score += 10

        if volume_acceleration >= 2:
            pump_score += 15
            pump_reasons.append(
                f"Hacim ivmesi x{volume_acceleration:.1f}"
            )

        if volume_ratio >= 2:
            pump_score += 15
            pump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        if adx >= 25 and plus_di > minus_di:
            pump_score += 15
            pump_reasons.append(
                f"ADX {adx:.1f}"
            )

        if breakout_up:
            pump_score += 15
            pump_reasons.append(
                "Breakout"
            )

        if price > vwap:
            pump_score += 5

        if stoch > 90:
            pump_score -= 10
            pump_reasons.append(
                "Stoch RSI çok yüksek"
            )

        if momentum5 > 6:
            pump_score -= 15
            pump_reasons.append(
                "Hareket fazla ilerledi"
            )

        pump_score = max(
            0,
            min(100, pump_score)
        )

        return {

            "symbol": symbol,

            "price": price,

            "long_score": long_score,
            "short_score": short_score,

            "long_signal": long_signal,
            "short_signal": short_signal,

            "r15": r15,
            "r1": r1,
            "r4": r4,

            "stoch": stoch,

            "volume": volume_ratio,

            "volume_acceleration":
                volume_acceleration,

            "momentum":
                momentum5,

            "adx":
                adx,

            "plus_di":
                plus_di,

            "minus_di":
                minus_di,

            "vwap":
                vwap,

            "long_sl":
                long_sl,

            "long_tp1":
                long_tp1,

            "long_tp2":
                long_tp2,

            "long_tp3":
                long_tp3,

            "short_sl":
                short_sl,

            "short_tp1":
                short_tp1,

            "short_tp2":
                short_tp2,

            "short_tp3":
                short_tp3,

            "long_reasons":
                long_reasons,

            "short_reasons":
                short_reasons,

            "long_warnings":
                long_warnings,

            "short_warnings":
                short_warnings,

            "pump_score":
                pump_score,

            "pump_reasons":
                pump_reasons
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
        "🚀 GELİŞMİŞ LONG + SHORT "
        "SCANNER BAŞLADI..."
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
        if (
            x["long_score"] >= 65
            and x["long_signal"]
            in [
                "🟢 GÜÇLÜ AL",
                "🟢 AL ADAYI"
            ]
        )
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
        if (
            x["short_score"] >= 65
            and x["short_signal"]
            in [
                "🔴 GÜÇLÜ SAT",
                "🔴 SAT ADAYI"
            ]
        )
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
        if x["pump_score"] >= 55
    ]

    pumps.sort(
        key=lambda x: x["pump_score"],
        reverse=True
    )

    pumps = pumps[:3]

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

        "💥 Early Breakout Detection\n"

        "🎯 ATR + R/R hedefleme\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        "📈 LONG FIRSATLARI\n\n"
    )

    # =====================================================
    # LONG MESSAGE
    # =====================================================

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
                f"{coin['r15']:.1f}"
                f" | 1h: "
                f"{coin['r1']:.1f}"
                f" | 4h: "
                f"{coin['r4']:.1f}\n"

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
                f"{', '.join(coin['long_reasons'][:8])}\n"
            )

            if coin["long_warnings"]:

                message += (
                    "⚠️ "
                    + ", ".join(
                        coin["long_warnings"][:3]
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
                f"{coin['r15']:.1f}"
                f" | 1h: "
                f"{coin['r1']:.1f}"
                f" | 4h: "
                f"{coin['r4']:.1f}\n"

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
                f"{', '.join(coin['short_reasons'][:8])}\n"
            )

            if coin["short_warnings"]:

                message += (
                    "⚠️ "
                    + ", ".join(
                        coin["short_warnings"][:3]
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
            "🟡 Şu anda erken pump "
            "sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            pumps,
            1
        ):

            message += (

                f"🚀 {i}. "
                f"{coin['symbol']}\n"

                "⚡ HAREKETLENİYOR\n"

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
                f"{', '.join(coin['pump_reasons'][:5])}\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    message += (
        "⚠️ Teknik sinyal sistemidir. "
        "Yatırım tavsiyesi değildir."
    )

    print(message)

    send_telegram(message)


if __name__ == "__main__":
    main()
