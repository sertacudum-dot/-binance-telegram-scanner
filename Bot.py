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

EXCLUDED = {
    "UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"
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

    try:
        with urllib.request.urlopen(req, timeout=20):
            print("Telegram mesajı gönderildi.")
    except Exception as e:
        print("Telegram gönderim hatası:", e)


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

    upper = middle + 2 * std
    lower = middle - 2 * std

    return upper, middle, lower, std


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

    for i in range(1, len(close)):

        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

        trs.append(tr)

    if len(trs) < period:
        return 0

    return sum(trs[-period:]) / period


# =========================================================
# ADX + DI
# =========================================================

def adx_di(high, low, close, period=14):

    if len(close) < period * 3:
        return 0, 0, 0

    tr_list = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(close)):

        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]

        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

        tr_list.append(tr)

        plus_dm.append(
            up if up > down and up > 0 else 0
        )

        minus_dm.append(
            down if down > up and down > 0 else 0
        )

    dx_values = []
    plus_values = []
    minus_values = []

    for i in range(period, len(tr_list)):

        tr_sum = sum(
            tr_list[i - period:i]
        )

        plus_sum = sum(
            plus_dm[i - period:i]
        )

        minus_sum = sum(
            minus_dm[i - period:i]
        )

        if tr_sum == 0:
            continue

        plus_di = 100 * plus_sum / tr_sum
        minus_di = 100 * minus_sum / tr_sum

        denominator = plus_di + minus_di

        if denominator == 0:
            continue

        dx = (
            abs(plus_di - minus_di)
            / denominator
        ) * 100

        dx_values.append(dx)
        plus_values.append(plus_di)
        minus_values.append(minus_di)

    if len(dx_values) < period:
        return 0, 0, 0

    adx_value = sum(
        dx_values[-period:]
    ) / period

    return (
        adx_value,
        plus_values[-1],
        minus_values[-1]
    )


# =========================================================
# VWAP
# =========================================================

def vwap(high, low, close, volume):

    typical = []

    for h, l, c in zip(high, low, close):
        typical.append((h + l + c) / 3)

    total_volume = sum(volume)

    if total_volume == 0:
        return close[-1]

    total = sum(
        p * v
        for p, v in zip(typical, volume)
    )

    return total / total_volume


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
        high[-1]
        + low[-1]
    ) / 2

    lower_band = hl2 - multiplier * atr_value
    upper_band = hl2 + multiplier * atr_value

    return close[-1] > lower_band


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
# SYMBOL FILTER
# =========================================================

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

        r15 = rsi(close15)
        r1 = rsi(close1h)
        r4 = rsi(close4h)

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        e9 = ema(close15, 9)
        e21 = ema(close15, 21)
        e50 = ema(close15, 50)

        e21_1h = ema(close1h, 21)
        e50_1h = ema(close1h, 50)

        e21_4h = ema(close4h, 21)
        e50_4h = ema(close4h, 50)

        # -------------------------------------------------
        # MACD
        # -------------------------------------------------

        m15, s15, h15 = macd(close15)
        m1, s1, h1 = macd(close1h)

        # -------------------------------------------------
        # STOCH
        # -------------------------------------------------

        stoch = stoch_rsi(close15)

        # -------------------------------------------------
        # BOLLINGER
        # -------------------------------------------------

        bb_upper, bb_middle, bb_lower, bb_std = bollinger(
            close15
        )

        bb_width = (
            (bb_upper - bb_lower)
            / bb_middle
            * 100
            if bb_middle != 0
            else 0
        )

        prev_upper, prev_middle, prev_lower, _ = bollinger(
            close15[:-1]
        )

        breakout = (
            price > bb_upper
            and close15[-2] <= prev_upper
        )

        breakdown = (
            price < bb_lower
            and close15[-2] >= prev_lower
        )

        # -------------------------------------------------
        # OBV
        # -------------------------------------------------

        obv_values = obv(
            close15,
            vol15
        )

        obv_up = (
            obv_values[-1]
            > obv_values[-6]
        )

        obv_down = (
            obv_values[-1]
            < obv_values[-6]
        )

        # -------------------------------------------------
        # SUPERTREND
        # -------------------------------------------------

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

        # -------------------------------------------------
        # TDI
        # -------------------------------------------------

        tdi_rsi, tdi_signal = tdi(close15)

        # -------------------------------------------------
        # ADX / DI
        # -------------------------------------------------

        adx15, plus_di, minus_di = adx_di(
            high15,
            low15,
            close15
        )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        vwap_value = vwap(
            high15,
            low15,
            close15,
            vol15
        )

        # -------------------------------------------------
        # ATR
        # -------------------------------------------------

        atr_value = atr(
            high15,
            low15,
            close15
        )

        if atr_value <= 0:
            return None

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        momentum15 = (
            price / close15[-5] - 1
        ) * 100

        momentum1h = (
            close1h[-1] / close1h[-4] - 1
        ) * 100

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        avg_volume = sum(
            vol15[-21:-1]
        ) / 20

        if avg_volume <= 0:
            return None

        volume_ratio = (
            vol15[-1]
            / avg_volume
        )

        previous_avg_volume = sum(
            vol15[-26:-6]
        ) / 20

        if previous_avg_volume <= 0:
            volume_acceleration = 1
        else:
            volume_acceleration = (
                avg_volume
                / previous_avg_volume
            )

        # Son 3 mumdaki hacim ivmesi
        recent_volume = sum(
            vol15[-3:]
        ) / 3

        previous_volume = sum(
            vol15[-8:-3]
        ) / 5

        if previous_volume > 0:
            volume_acceleration_recent = (
                recent_volume
                / previous_volume
            )
        else:
            volume_acceleration_recent = 1

        # -------------------------------------------------
        # BREAKOUT / BREAKDOWN
        # -------------------------------------------------

        recent_high = max(
            high15[-21:-1]
        )

        recent_low = min(
            low15[-21:-1]
        )

        price_breakout = (
            price > recent_high
        )

        price_breakdown = (
            price < recent_low
        )

        # -------------------------------------------------
        # TREND
        # -------------------------------------------------

        long_ema = (
            price > e9 > e21
            and price > e50
        )

        short_ema = (
            price < e9 < e21
            and price < e50
        )

        long_4h = (
            close4h[-1] > e21_4h
            and e21_4h > e50_4h
        )

        short_4h = (
            close4h[-1] < e21_4h
            and e21_4h < e50_4h
        )

        # =================================================
        # LONG SCORE
        # =================================================

        long_score = 0
        long_reasons = []

        if 50 <= r15 <= 67:
            long_score += 8
            long_reasons.append("RSI ideal")

        if 50 <= r1 <= 68:
            long_score += 8
            long_reasons.append("1h RSI")

        if 45 <= r4 <= 70:
            long_score += 6
            long_reasons.append("4h RSI")

        if long_ema:
            long_score += 10
            long_reasons.append("EMA9/21/50")

        if long_4h:
            long_score += 10
            long_reasons.append("4h trend")

        if m15 > s15 and h15 > 0:
            long_score += 6
            long_reasons.append("MACD")

        if m1 > s1 and h1 > 0:
            long_score += 8
            long_reasons.append("1h MACD")

        if 20 <= stoch <= 80:
            long_score += 5
            long_reasons.append("Stoch RSI")

        if price > bb_middle and price < bb_upper:
            long_score += 5
            long_reasons.append("Bollinger")

        if breakout:
            long_score += 8
            long_reasons.append("BB breakout")

        if obv_up:
            long_score += 4
            long_reasons.append("OBV")

        if st15 and st1:
            long_score += 5
            long_reasons.append("Supertrend")

        if tdi_rsi > tdi_signal and tdi_rsi > 50:
            long_score += 4
            long_reasons.append("TDI")

        if adx15 >= 25 and plus_di > minus_di:
            long_score += 8
            long_reasons.append("ADX/DI")

        if price > vwap_value:
            long_score += 6
            long_reasons.append("VWAP")

        if momentum15 >= 1.0:
            long_score += 6
            long_reasons.append("Momentum")

        if momentum1h > 0:
            long_score += 3

        if volume_ratio >= 3:
            long_score += 8
        elif volume_ratio >= 2:
            long_score += 6
        elif volume_ratio >= 1.5:
            long_score += 4

        if volume_acceleration_recent >= 1.5:
            long_score += 5
            long_reasons.append("Volume acceleration")

        if price_breakout:
            long_score += 5
            long_reasons.append("Breakout")

        # =================================================
        # SHORT SCORE
        # =================================================

        short_score = 0
        short_reasons = []

        if 33 <= r15 <= 50:
            short_score += 8
            short_reasons.append("RSI ideal")

        if 32 <= r1 <= 50:
            short_score += 8
            short_reasons.append("1h RSI")

        if 30 <= r4 <= 55:
            short_score += 6
            short_reasons.append("4h RSI")

        if short_ema:
            short_score += 10
            short_reasons.append("EMA9/21/50")

        if short_4h:
            short_score += 10
            short_reasons.append("4h trend")

        if m15 < s15 and h15 < 0:
            short_score += 6
            short_reasons.append("MACD")

        if m1 < s1 and h1 < 0:
            short_score += 8
            short_reasons.append("1h MACD")

        if 20 <= stoch <= 80:
            short_score += 5
            short_reasons.append("Stoch RSI")

        if price < bb_middle and price > bb_lower:
            short_score += 5
            short_reasons.append("Bollinger")

        if breakdown:
            short_score += 8
            short_reasons.append("BB breakdown")

        if obv_down:
            short_score += 4
            short_reasons.append("OBV")

        if not st15 and not st1:
            short_score += 5
            short_reasons.append("Supertrend")

        if tdi_rsi < tdi_signal and tdi_rsi < 50:
            short_score += 4
            short_reasons.append("TDI")

        if adx15 >= 25 and minus_di > plus_di:
            short_score += 8
            short_reasons.append("ADX/DI")

        if price < vwap_value:
            short_score += 6
            short_reasons.append("VWAP")

        if momentum15 <= -1.0:
            short_score += 6
            short_reasons.append("Momentum")

        if momentum1h < 0:
            short_score += 3

        if volume_ratio >= 3:
            short_score += 8
        elif volume_ratio >= 2:
            short_score += 6
        elif volume_ratio >= 1.5:
            short_score += 4

        if volume_acceleration_recent >= 1.5:
            short_score += 5
            short_reasons.append("Volume acceleration")

        if price_breakdown:
            short_score += 5
            short_reasons.append("Breakdown")

        # =================================================
        # HARD FILTERS FOR STRONG LONG
        # =================================================

        strong_long = (
            long_score >= 80
            and adx15 >= 20
            and plus_di > minus_di
            and price > vwap_value
            and long_ema
            and r1 < 72
            and r4 >= 45
            and momentum15 >= 0.7
            and volume_ratio >= 1.3
            and volume_acceleration_recent >= 1.05
            and not (
                stoch > 90
            )
        )

        # =================================================
        # HARD FILTERS FOR STRONG SHORT
        # =================================================

        strong_short = (
            short_score >= 80
            and adx15 >= 20
            and minus_di > plus_di
            and price < vwap_value
            and short_ema
            and r1 > 28
            and r4 <= 55
            and momentum15 <= -0.7
            and volume_ratio >= 1.3
            and volume_acceleration_recent >= 1.05
            and not (
                stoch < 10
            )
        )

        # =================================================
        # PUMP RADAR
        # =================================================

        pump_score = 0
        pump_reasons = []

        if momentum15 >= 2:
            pump_score += 20
            pump_reasons.append(
                f"15m momentum +{momentum15:.1f}%"
            )

        elif momentum15 >= 1:
            pump_score += 10

        if momentum1h >= 2:
            pump_score += 10
            pump_reasons.append(
                f"1h momentum +{momentum1h:.1f}%"
            )

        if volume_ratio >= 3:
            pump_score += 20
            pump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            pump_score += 14

        elif volume_ratio >= 1.5:
            pump_score += 8

        if volume_acceleration_recent >= 2:
            pump_score += 20
            pump_reasons.append(
                f"Hacim ivmesi x{volume_acceleration_recent:.1f}"
            )

        elif volume_acceleration_recent >= 1.5:
            pump_score += 12

        if adx15 >= 30:
            pump_score += 15
            pump_reasons.append(
                f"ADX {adx15:.1f}"
            )

        elif adx15 >= 25:
            pump_score += 8

        if price_breakout or breakout:
            pump_score += 20
            pump_reasons.append("Breakout")

        if price > vwap_value:
            pump_score += 8

        if obv_up:
            pump_score += 7
            pump_reasons.append("OBV")

        if bb_width < 2:
            pump_score += 5
            pump_reasons.append("BB sıkışması")

        # Pump için fiyat gerçekten hareket etmeli
        valid_pump = (
            pump_score >= 55
            and momentum15 >= 1.5
            and volume_ratio >= 1.3
            and volume_acceleration_recent >= 1.2
        )

        # =================================================
        # DUMP RADAR
        # =================================================

        dump_score = 0
        dump_reasons = []

        if momentum15 <= -2:
            dump_score += 20
            dump_reasons.append(
                f"15m momentum {momentum15:.1f}%"
            )

        elif momentum15 <= -1:
            dump_score += 10

        if momentum1h <= -2:
            dump_score += 10
            dump_reasons.append(
                f"1h momentum {momentum1h:.1f}%"
            )

        if volume_ratio >= 3:
            dump_score += 20
            dump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            dump_score += 14

        elif volume_ratio >= 1.5:
            dump_score += 8

        if volume_acceleration_recent >= 2:
            dump_score += 20
            dump_reasons.append(
                f"Hacim ivmesi x{volume_acceleration_recent:.1f}"
            )

        elif volume_acceleration_recent >= 1.5:
            dump_score += 12

        if adx15 >= 30:
            dump_score += 15
            dump_reasons.append(
                f"ADX {adx15:.1f}"
            )

        elif adx15 >= 25:
            dump_score += 8

        if price_breakdown or breakdown:
            dump_score += 20
            dump_reasons.append("Breakdown")

        if price < vwap_value:
            dump_score += 8

        if obv_down:
            dump_score += 7
            dump_reasons.append("OBV")

        if bb_width < 2:
            dump_score += 5
            dump_reasons.append("BB sıkışması")

        valid_dump = (
            dump_score >= 55
            and momentum15 <= -1.5
            and volume_ratio >= 1.3
            and volume_acceleration_recent >= 1.2
        )

        # =================================================
        # SCORE CAP
        # =================================================

        # 100'e yapışmasını engelliyoruz.
        long_score = min(long_score, 95)
        short_score = min(short_score, 95)
        pump_score = min(pump_score, 95)
        dump_score = min(dump_score, 95)

        # =================================================
        # ATR TARGETS
        # =================================================

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

            "strong_long": strong_long,
            "strong_short": strong_short,

            "pump_score": pump_score,
            "dump_score": dump_score,

            "valid_pump": valid_pump,
            "valid_dump": valid_dump,

            "rsi15": r15,
            "rsi1h": r1,
            "rsi4h": r4,

            "stoch": stoch,

            "volume": volume_ratio,
            "volume_acc": volume_acceleration_recent,

            "momentum": momentum15,
            "momentum1h": momentum1h,

            "adx": adx15,
            "plus_di": plus_di,
            "minus_di": minus_di,

            "vwap": vwap_value,

            "sl_long": long_sl,
            "tp1_long": long_tp1,
            "tp2_long": long_tp2,
            "tp3_long": long_tp3,

            "sl_short": short_sl,
            "tp1_short": short_tp1,
            "tp2_short": short_tp2,
            "tp3_short": short_tp3,

            "long_reasons": long_reasons,
            "short_reasons": short_reasons,

            "pump_reasons": pump_reasons,
            "dump_reasons": dump_reasons
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
        "LONG + SHORT SCANNER BAŞLADI..."
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
            for x in EXCLUDED
        ):
            continue

        try:

            quote_volume = float(
                ticker["quoteVolume"]
            )

            # Likidite filtresi
            if quote_volume < 5_000_000:
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
    # STRONG LONG
    # =====================================================

    longs = [
        x for x in results
        if x["strong_long"]
    ]

    longs.sort(
        key=lambda x: x["long_score"],
        reverse=True
    )

    longs = longs[:3]

    # =====================================================
    # STRONG SHORT
    # =====================================================

    shorts = [
        x for x in results
        if x["strong_short"]
    ]

    shorts.sort(
        key=lambda x: x["short_score"],
        reverse=True
    )

    shorts = shorts[:3]

    # =====================================================
    # PUMP RADAR
    # =====================================================

    pumps = [
        x for x in results
        if x["valid_pump"]
        and not x["strong_long"]
    ]

    pumps.sort(
        key=lambda x: x["pump_score"],
        reverse=True
    )

    pumps = pumps[:3]

    # =====================================================
    # DUMP RADAR
    # =====================================================

    dumps = [
        x for x in results
        if x["valid_dump"]
        and not x["strong_short"]
    ]

    dumps.sort(
        key=lambda x: x["dump_score"],
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

        "🎯 ATR + R/R hedefleme\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # =====================================================
    # LONG
    # =====================================================

    message += "📈 LONG FIRSATLARI\n\n"

    if not longs:

        message += (
            "🟡 Şu anda güçlü LONG sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            longs,
            1
        ):

            message += (
                f"🏆 {i}. "
                f"{coin['symbol']}\n"

                "🟢 GÜÇLÜ AL\n"

                f"⭐ Sinyal gücü: "
                f"{coin['long_score']}/100\n\n"

                f"💰 Giriş: "
                f"{price_format(coin['price'])}\n"

                f"RSI: "
                f"{coin['rsi15']:.1f}"
                f" | 1h: "
                f"{coin['rsi1h']:.1f}"
                f" | 4h: "
                f"{coin['rsi4h']:.1f}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acc']:.1f}\n"

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"

                f"🧠 Pozitif: "
                f"{', '.join(coin['long_reasons'][:9])}\n\n"

                f"🛑 SL: "
                f"{price_format(coin['sl_long'])}\n"

                f"🎯 TP1: "
                f"{price_format(coin['tp1_long'])}\n"

                f"🎯 TP2: "
                f"{price_format(coin['tp2_long'])}\n"

                f"🎯 TP3: "
                f"{price_format(coin['tp3_long'])}\n"

                "📐 R/R: 1 : 2\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # =====================================================
    # SHORT
    # =====================================================

    message += "📉 SHORT FIRSATLARI\n\n"

    if not shorts:

        message += (
            "🟡 Şu anda güçlü SHORT sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            shorts,
            1
        ):

            message += (
                f"🏆 {i}. "
                f"{coin['symbol']}\n"

                "🔴 GÜÇLÜ SAT\n"

                f"⭐ Sinyal gücü: "
                f"{coin['short_score']}/100\n\n"

                f"💰 Giriş: "
                f"{price_format(coin['price'])}\n"

                f"RSI: "
                f"{coin['rsi15']:.1f}"
                f" | 1h: "
                f"{coin['rsi1h']:.1f}"
                f" | 4h: "
                f"{coin['rsi4h']:.1f}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acc']:.1f}\n"

                f"📉 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"

                f"🧠 Negatif: "
                f"{', '.join(coin['short_reasons'][:9])}\n\n"

                f"🛑 SL: "
                f"{price_format(coin['sl_short'])}\n"

                f"🎯 TP1: "
                f"{price_format(coin['tp1_short'])}\n"

                f"🎯 TP2: "
                f"{price_format(coin['tp2_short'])}\n"

                f"🎯 TP3: "
                f"{price_format(coin['tp3_short'])}\n"

                "📐 R/R: 1 : 2\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # =====================================================
    # PUMP RADAR
    # =====================================================

    message += "🚀 PUMP RADAR\n\n"

    if not pumps:

        message += (
            "🟡 Şu anda belirgin pump hareketi yok.\n\n"
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
                f"x{coin['volume_acc']:.1f}\n"

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

    # =====================================================
    # DUMP RADAR
    # =====================================================

    message += "💥 DUMP RADAR\n\n"

    if not dumps:

        message += (
            "🟡 Şu anda belirgin dump hareketi yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            dumps,
            1
        ):

            message += (
                f"💥 {i}. "
                f"{coin['symbol']}\n"

                "⚠️ DÜŞÜŞ HIZLANIYOR\n"

                f"⭐ Dump gücü: "
                f"{coin['dump_score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acc']:.1f}\n"

                f"📉 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"🧠 "
                f"{', '.join(coin['dump_reasons'][:5])}\n\n"

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
