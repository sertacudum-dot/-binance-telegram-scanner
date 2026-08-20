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
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        }
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
# KLINES
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
        / (highest - lowest)
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

    hl2 = (high[-1] + low[-1]) / 2

    lower_band = hl2 - multiplier * atr

    return close[-1] > lower_band


def tdi(values):

    current = rsi(values, 13)
    previous = rsi(values[:-1], 13)

    signal = current * 0.7 + previous * 0.3

    return current, signal


def atr_value(high, low, close, period=14):

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
# HELPERS
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


def pct_change(current, previous):

    if previous == 0:
        return 0

    return ((current / previous) - 1) * 100


# =========================================================
# ANALYSIS
# =========================================================

def analyze(symbol):

    try:

        close15, high15, low15, vol15 = get_klines(
            symbol, "15m"
        )

        close1h, high1h, low1h, vol1h = get_klines(
            symbol, "1h"
        )

        close4h, high4h, low4h, vol4h = get_klines(
            symbol, "4h"
        )

        price = close15[-1]

        # =================================================
        # BASIC INDICATORS
        # =================================================

        rsi15 = rsi(close15)
        rsi1h = rsi(close1h)
        rsi4h = rsi(close4h)

        stoch = stoch_rsi(close15)

        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)

        ema9_prev = ema(close15[:-1], 9)
        ema21_prev = ema(close15[:-1], 21)

        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)

        macd15, signal15, hist15 = macd(close15)
        macd1h, signal1h, hist1h = macd(close1h)

        macd15_prev, signal15_prev, hist15_prev = macd(
            close15[:-1]
        )

        upper, middle, lower = bollinger(close15)

        obv_values = obv(close15, vol15)

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

        tdi_rsi, tdi_signal = tdi(close15)

        # =================================================
        # MOMENTUM
        # =================================================

        momentum15 = pct_change(
            close15[-1],
            close15[-2]
        )

        momentum1h = pct_change(
            close15[-1],
            close15[-5]
        )

        momentum4h = pct_change(
            close15[-1],
            close15[-17]
        )

        previous_momentum = pct_change(
            close15[-2],
            close15[-6]
        )

        momentum_acceleration = (
            momentum1h - previous_momentum
        )

        # =================================================
        # VOLUME
        # =================================================

        avg_volume = (
            sum(vol15[-21:-1]) / 20
        )

        if avg_volume <= 0:
            return None

        volume_ratio = (
            vol15[-1] / avg_volume
        )

        previous_avg_volume = (
            sum(vol15[-22:-2]) / 20
        )

        previous_volume_ratio = (
            vol15[-2] / previous_avg_volume
            if previous_avg_volume > 0
            else 1
        )

        volume_acceleration = (
            volume_ratio - previous_volume_ratio
        )

        # =================================================
        # NORMAL LONG
        # =================================================

        long_score = 0
        long_reasons = []
        long_warnings = []

        if 50 <= rsi15 <= 68:
            long_score += 8
            long_reasons.append("RSI ideal")

        elif rsi15 > 70:
            long_score -= 8
            long_warnings.append("RSI yüksek")

        elif rsi15 < 45:
            long_score -= 6
            long_warnings.append("RSI zayıf")

        if 50 <= rsi1h <= 68:
            long_score += 8
            long_reasons.append("1h RSI")

        elif rsi1h > 75:
            long_score -= 20
            long_warnings.append("1h aşırı alım")

        elif rsi1h < 40:
            long_score -= 10
            long_warnings.append("1h RSI zayıf")

        if 45 <= rsi4h <= 68:
            long_score += 8
            long_reasons.append("4h RSI")

        elif rsi4h < 40:
            long_score -= 15
            long_warnings.append("4h RSI zayıf")

        if price > ema9 > ema21:
            long_score += 10
            long_reasons.append("EMA9/21")

        if price > ema50:
            long_score += 5
            long_reasons.append("EMA50")

        if (
            price > ema21_4h
            and ema21_4h > ema50_4h
        ):
            long_score += 10
            long_reasons.append("4h trend")

        elif price > ema50_4h:
            long_score += 3
            long_reasons.append("4h EMA50")

        else:
            long_score -= 8
            long_warnings.append("4h zayıf")

        if macd15 > signal15 and hist15 > 0:
            long_score += 7
            long_reasons.append("MACD")

        if macd1h > signal1h and hist1h > 0:
            long_score += 9
            long_reasons.append("1h MACD")

        if 20 <= stoch <= 80:
            long_score += 7
            long_reasons.append("Stoch RSI")

        elif stoch > 90:
            long_score -= 18
            long_warnings.append("Stoch RSI çok yüksek")

        if middle < price < upper:
            long_score += 4
            long_reasons.append("Bollinger")

        if len(obv_values) >= 6:

            if obv_values[-1] > obv_values[-5]:
                long_score += 4
                long_reasons.append("OBV")

        if st15:
            long_score += 4
            long_reasons.append("Supertrend")

        if st1h:
            long_score += 4
            long_reasons.append("1h Supertrend")

        if tdi_rsi > tdi_signal and 50 < tdi_rsi < 70:
            long_score += 4
            long_reasons.append("TDI")

        if 0.5 <= momentum1h <= 5:
            long_score += 6
            long_reasons.append("Momentum")

        elif momentum1h < 0:
            long_score -= 12
            long_warnings.append("Momentum negatif")

        # Volume

        if volume_ratio >= 3:
            long_score += 12
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            long_score += 10
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.5:
            long_score += 7
            long_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.2:
            long_score += 2
            long_warnings.append("Hacim düşük")

        # =================================================
        # EARLY PUMP
        # =================================================

        pump_score = 0
        pump_reasons = []

        # Hacim patlaması

        if volume_ratio >= 5:
            pump_score += 25
            pump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 3:
            pump_score += 20
            pump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            pump_score += 15
            pump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.5:
            pump_score += 8
            pump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        # Momentum

        if 1 <= momentum1h <= 4:
            pump_score += 15
            pump_reasons.append(
                f"Momentum +{momentum1h:.1f}%"
            )

        elif 4 < momentum1h <= 10:
            pump_score += 12
            pump_reasons.append(
                f"Hızlı momentum +{momentum1h:.1f}%"
            )

        # Momentum hızlanması

        if momentum_acceleration > 0.5:
            pump_score += 12
            pump_reasons.append(
                "Momentum hızlanıyor"
            )

        # EMA breakout

        if (
            price > ema9
            and ema9 > ema21
            and close15[-2] <= ema9_prev
        ):
            pump_score += 12
            pump_reasons.append(
                "EMA9 breakout"
            )

        elif price > ema9 > ema21:
            pump_score += 6
            pump_reasons.append(
                "EMA yükseliş yapısı"
            )

        # MACD acceleration

        if (
            hist15 > 0
            and hist15 > hist15_prev
        ):
            pump_score += 10
            pump_reasons.append(
                "MACD hızlanıyor"
            )

        # Stoch RSI

        if 30 <= stoch <= 80:
            pump_score += 8
            pump_reasons.append(
                "Stoch RSI yükseliş bölgesi"
            )

        elif 80 < stoch <= 95:
            pump_score += 4

        # OBV

        if (
            len(obv_values) >= 6
            and obv_values[-1] > obv_values[-5]
        ):
            pump_score += 6
            pump_reasons.append(
                "OBV yükseliyor"
            )

        # Supertrend

        if st15:
            pump_score += 5
            pump_reasons.append(
                "Supertrend pozitif"
            )

        # 1h destek

        if rsi1h >= 50:
            pump_score += 5
            pump_reasons.append(
                "1h yapı destekliyor"
            )

        # Pump hard filters

        pump_valid = (
            volume_ratio >= 1.5
            and momentum1h > 0.5
            and rsi15 < 75
            and pump_score >= 55
        )

        # =================================================
        # NORMAL SHORT
        # =================================================

        short_score = 0
        short_reasons = []
        short_warnings = []

        if 32 <= rsi15 <= 50:
            short_score += 8
            short_reasons.append("RSI zayıf")

        elif rsi15 < 30:
            short_score -= 8
            short_warnings.append("RSI aşırı düşük")

        if 32 <= rsi1h <= 50:
            short_score += 8
            short_reasons.append("1h RSI zayıf")

        elif rsi1h < 25:
            short_score -= 10
            short_warnings.append("1h aşırı satım")

        if rsi4h <= 50:
            short_score += 8
            short_reasons.append("4h RSI zayıf")

        if price < ema9 < ema21:
            short_score += 10
            short_reasons.append("EMA9/21 aşağı")

        if price < ema50:
            short_score += 5
            short_reasons.append("EMA50 altında")

        if (
            price < ema21_4h
            and ema21_4h < ema50_4h
        ):
            short_score += 10
            short_reasons.append("4h düşüş trendi")

        elif price < ema50_4h:
            short_score += 3
            short_reasons.append("4h EMA50 altında")

        if macd15 < signal15 and hist15 < 0:
            short_score += 7
            short_reasons.append("MACD negatif")

        if macd1h < signal1h and hist1h < 0:
            short_score += 9
            short_reasons.append("1h MACD negatif")

        if stoch < 80:
            short_score += 5

        if price < middle:
            short_score += 4
            short_reasons.append("Bollinger")

        if (
            len(obv_values) >= 6
            and obv_values[-1] < obv_values[-5]
        ):
            short_score += 4
            short_reasons.append("OBV düşüyor")

        if not st15:
            short_score += 4
            short_reasons.append("Supertrend negatif")

        if not st1h:
            short_score += 4
            short_reasons.append("1h Supertrend negatif")

        if momentum1h < -0.5:
            short_score += 10
            short_reasons.append(
                f"Momentum {momentum1h:+.1f}%"
            )

        # Short volume

        if volume_ratio >= 3:
            short_score += 12
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            short_score += 10
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.5:
            short_score += 7
            short_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        # =================================================
        # EARLY DUMP
        # =================================================

        dump_score = 0
        dump_reasons = []

        if volume_ratio >= 5:
            dump_score += 25
            dump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 3:
            dump_score += 20
            dump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            dump_score += 15
            dump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.5:
            dump_score += 8
            dump_reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        if -10 <= momentum1h <= -1:
            dump_score += 15
            dump_reasons.append(
                f"Negatif momentum {momentum1h:.1f}%"
            )

        if momentum_acceleration < -0.5:
            dump_score += 12
            dump_reasons.append(
                "Düşüş hızlanıyor"
            )

        if (
            price < ema9
            and ema9 < ema21
            and close15[-2] >= ema9_prev
        ):
            dump_score += 12
            dump_reasons.append(
                "EMA9 aşağı kırılım"
            )

        elif price < ema9 < ema21:
            dump_score += 6
            dump_reasons.append(
                "EMA düşüş yapısı"
            )

        if (
            hist15 < 0
            and hist15 < hist15_prev
        ):
            dump_score += 10
            dump_reasons.append(
                "MACD negatif hızlanıyor"
            )

        if 20 <= stoch <= 70:
            dump_score += 8
            dump_reasons.append(
                "Stoch RSI düşüş alanı"
            )

        if (
            len(obv_values) >= 6
            and obv_values[-1] < obv_values[-5]
        ):
            dump_score += 6
            dump_reasons.append(
                "OBV düşüyor"
            )

        if not st15:
            dump_score += 5
            dump_reasons.append(
                "Supertrend negatif"
            )

        if rsi1h <= 50:
            dump_score += 5
            dump_reasons.append(
                "1h yapı zayıf"
            )

        dump_valid = (
            volume_ratio >= 1.5
            and momentum1h < -0.5
            and rsi15 > 25
            and dump_score >= 55
        )

        # =================================================
        # NORMAL SIGNALS
        # =================================================

        long_score = max(
            0,
            min(100, long_score)
        )

        short_score = max(
            0,
            min(100, short_score)
        )

        if (
            long_score >= 82
            and price > ema9 > ema21
            and volume_ratio >= 1.5
            and momentum1h > 0
            and rsi1h < 72
        ):
            long_signal = "🟢 GÜÇLÜ LONG"

        elif long_score >= 70:
            long_signal = "🟢 LONG ADAYI"

        else:
            long_signal = "⚪ ZAYIF"

        if (
            short_score >= 82
            and price < ema9 < ema21
            and volume_ratio >= 1.5
            and momentum1h < 0
            and rsi1h > 28
        ):
            short_signal = "🔴 GÜÇLÜ SHORT"

        elif short_score >= 70:
            short_signal = "🔴 SHORT ADAYI"

        else:
            short_signal = "⚪ ZAYIF"

        # =================================================
        # ATR / TARGETS
        # =================================================

        atr = atr_value(
            high15,
            low15,
            close15
        )

        if atr <= 0:
            return None

        long_risk = atr * 1.5

        long_sl = price - long_risk
        long_tp1 = price + long_risk
        long_tp2 = price + long_risk * 1.5
        long_tp3 = price + long_risk * 2

        short_risk = atr * 1.5

        short_sl = price + short_risk
        short_tp1 = price - short_risk
        short_tp2 = price - short_risk * 1.5
        short_tp3 = price - short_risk * 2

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

            "pump_score": min(100, pump_score),
            "pump_valid": pump_valid,
            "pump_reasons": pump_reasons,

            "dump_score": min(100, dump_score),
            "dump_valid": dump_valid,
            "dump_reasons": dump_reasons,

            "rsi15": rsi15,
            "rsi1h": rsi1h,
            "rsi4h": rsi4h,
            "stoch": stoch,

            "volume": volume_ratio,
            "momentum": momentum1h,
            "momentum15": momentum15,
            "momentum_acceleration": momentum_acceleration,

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
        "LONG + SHORT + PUMP SCANNER BAŞLADI..."
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
    # LISTS
    # =====================================================

    longs = [
        x for x in results
        if x["long_score"] >= 70
    ]

    shorts = [
        x for x in results
        if x["short_score"] >= 70
    ]

    pumps = [
        x for x in results
        if x["pump_valid"]
    ]

    dumps = [
        x for x in results
        if x["dump_valid"]
    ]

    longs.sort(
        key=lambda x: x["long_score"],
        reverse=True
    )

    shorts.sort(
        key=lambda x: x["short_score"],
        reverse=True
    )

    pumps.sort(
        key=lambda x: x["pump_score"],
        reverse=True
    )

    dumps.sort(
        key=lambda x: x["dump_score"],
        reverse=True
    )

    longs = longs[:3]
    shorts = shorts[:3]
    pumps = pumps[:3]
    dumps = dumps[:3]

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

        "🔥 Hacim + Momentum filtresi\n"

        "🚀 Early Pump / Dump radarı\n"

        "🎯 ATR + R/R hedefleme\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # =====================================================
    # PUMP
    # =====================================================

    message += (
        "🚀 EARLY PUMP RADARI\n\n"
    )

    if not pumps:

        message += (
            "🟡 Şu anda erken pump sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(pumps, 1):

            message += (
                f"🚨 {i}. "
                f"{coin['symbol']}\n"

                f"🚀 EARLY PUMP\n"

                f"⭐ Pump gücü: "
                f"{coin['pump_score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📈 15m momentum: "
                f"{coin['momentum15']:+.1f}%\n"

                f"⚡ Hızlanma: "
                f"{coin['momentum_acceleration']:+.1f}\n"

                f"RSI: "
                f"{coin['rsi15']:.1f} "
                f"| 1h: "
                f"{coin['rsi1h']:.1f} "
                f"| 4h: "
                f"{coin['rsi4h']:.1f}\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"🧠 "
                f"{', '.join(coin['pump_reasons'][:6])}\n\n"

                f"🛑 SL: "
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
        "📈 LONG FIRSATLARI\n\n"
    )

    if not longs:

        message += (
            "🟡 Şu anda trade edilebilir "
            "LONG sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(longs, 1):

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

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"🧠 "
                f"{', '.join(coin['long_reasons'][:7])}\n"
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
            )

    message += (
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📉 SHORT FIRSATLARI\n\n"
    )

    if not shorts:

        message += (
            "🟡 Şu anda trade edilebilir "
            "SHORT sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(shorts, 1):

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

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"🧠 "
                f"{', '.join(coin['short_reasons'][:7])}\n"
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
            )

    message += (
        "━━━━━━━━━━━━━━━━━━\n\n"
        "💣 EARLY DUMP RADARI\n\n"
    )

    if not dumps:

        message += (
            "🟡 Şu anda erken dump sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(dumps, 1):

            message += (
                f"🚨 {i}. "
                f"{coin['symbol']}\n"

                f"💣 EARLY DUMP\n"

                f"⭐ Dump gücü: "
                f"{coin['dump_score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"📉 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"⚡ Hızlanma: "
                f"{coin['momentum_acceleration']:+.1f}\n"

                f"RSI: "
                f"{coin['rsi15']:.1f} "
                f"| 1h: "
                f"{coin['rsi1h']:.1f} "
                f"| 4h: "
                f"{coin['rsi4h']:.1f}\n"

                f"🧠 "
                f"{', '.join(coin['dump_reasons'][:6])}\n\n"

                f"🛑 SL: "
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
        "━━━━━━━━━━━━━━━━━━\n"

        "⚠️ Teknik sinyal sistemidir. "
        "Yatırım tavsiyesi değildir."
    )

    print(message)

    send_telegram(message)


if __name__ == "__main__":
    main()
