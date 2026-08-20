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


def get(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


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

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    return close[-1] > lower_band and close[-1] > upper_band


def tdi(values):

    current = rsi(values, 13)
    previous = rsi(values[:-1], 13)

    signal = current * 0.7 + previous * 0.3

    return current, signal


def atr_value(high, low, close, period=14):

    if len(close) < period + 1:
        return 0

    trs = []

    start = len(close) - period

    for i in range(start, len(close)):

        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

        trs.append(tr)

    return sum(trs) / len(trs)


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

        # ==================================================
        # INDICATORS
        # ==================================================

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

        atr = atr_value(
            high15,
            low15,
            close15
        )

        if atr <= 0:
            return None

        momentum = (
            (price / close15[-5]) - 1
        ) * 100

        avg_volume = sum(
            vol15[-21:-1]
        ) / 20

        if avg_volume <= 0:
            return None

        volume_ratio = (
            vol15[-1] / avg_volume
        )

        # ==================================================
        # LONG SCORE
        # ==================================================

        long_score = 0
        long_reasons = []
        long_warnings = []

        # RSI 15m

        if 50 <= rsi15 <= 65:
            long_score += 8
            long_reasons.append("RSI ideal")

        elif 65 < rsi15 <= 70:
            long_score += 4

        elif rsi15 > 70:
            long_score -= 8
            long_warnings.append("RSI yüksek")

        elif rsi15 < 45:
            long_score -= 8
            long_warnings.append("RSI zayıf")

        # RSI 1h

        if 50 <= rsi1h <= 65:
            long_score += 8
            long_reasons.append("1h RSI")

        elif 65 < rsi1h <= 70:
            long_score += 3

        elif 70 < rsi1h <= 75:
            long_score -= 8
            long_warnings.append("1h RSI yüksek")

        elif rsi1h > 75:
            long_score -= 20
            long_warnings.append("1h aşırı alım")

        elif rsi1h < 40:
            long_score -= 10
            long_warnings.append("1h RSI zayıf")

        # RSI 4h

        if 45 <= rsi4h <= 65:
            long_score += 8
            long_reasons.append("4h RSI")

        elif 65 < rsi4h <= 70:
            long_score += 3

        elif rsi4h > 70:
            long_score -= 7
            long_warnings.append("4h RSI yüksek")

        elif rsi4h < 40:
            long_score -= 15
            long_warnings.append("4h RSI zayıf")

        # EMA

        if price > ema9 > ema21:
            long_score += 8
            long_reasons.append("EMA9/21")

        if price > ema50:
            long_score += 5
            long_reasons.append("EMA50")

        if price > ema21_4h > ema50_4h:
            long_score += 10
            long_reasons.append("4h trend")

        elif price > ema50_4h:
            long_score += 3
            long_reasons.append("4h EMA50")

        else:
            long_score -= 8
            long_warnings.append("4h zayıf")

        # MACD

        if macd15 > signal15 and hist15 > 0:
            long_score += 7
            long_reasons.append("MACD")

        if macd1h > signal1h and hist1h > 0:
            long_score += 9
            long_reasons.append("1h MACD")

        # Stoch RSI

        if 20 <= stoch <= 80:
            long_score += 7
            long_reasons.append("Stoch RSI")

        elif 80 < stoch <= 90:
            long_score -= 3
            long_warnings.append("Stoch RSI yüksek")

        elif stoch > 90:
            long_score -= 18
            long_warnings.append("Stoch RSI çok yüksek")

        # Bollinger

        if middle < price < upper:
            long_score += 4
            long_reasons.append("Bollinger")

        elif price > upper:
            long_score -= 5
            long_warnings.append("BB üstü")

        # OBV

        if len(obv_values) >= 6:
            if obv_values[-1] > obv_values[-5]:
                long_score += 4
                long_reasons.append("OBV")

        # Supertrend

        if st15:
            long_score += 4
            long_reasons.append("Supertrend")

        if st1h:
            long_score += 4
            long_reasons.append("1h Supertrend")

        # TDI

        if tdi_rsi > tdi_signal and 50 < tdi_rsi < 70:
            long_score += 4
            long_reasons.append("TDI")

        # Momentum

        if 0.5 <= momentum <= 4:
            long_score += 6
            long_reasons.append("Momentum")

        elif momentum < 0:
            long_score -= 12
            long_warnings.append("Momentum negatif")

        elif momentum > 7:
            long_score -= 8
            long_warnings.append("Momentum çok hızlı")

        # Volume

        if volume_ratio >= 3:
            long_score += 12
            long_reasons.append(f"Hacim x{volume_ratio:.1f}")

        elif volume_ratio >= 2:
            long_score += 10
            long_reasons.append(f"Hacim x{volume_ratio:.1f}")

        elif volume_ratio >= 1.5:
            long_score += 7
            long_reasons.append(f"Hacim x{volume_ratio:.1f}")

        else:
            long_score += 2
            long_warnings.append("Hacim düşük")

        # ==================================================
        # SHORT SCORE
        # ==================================================

        short_score = 0
        short_reasons = []
        short_warnings = []

        # RSI 15m

        if 35 <= rsi15 <= 50:
            short_score += 8
            short_reasons.append("RSI zayıf")

        elif 30 <= rsi15 < 35:
            short_score += 4

        elif rsi15 < 30:
            short_score -= 10
            short_warnings.append("RSI aşırı düşük")

        elif rsi15 > 65:
            short_score -= 7
            short_warnings.append("RSI güçlü")

        # RSI 1h

        if 35 <= rsi1h <= 50:
            short_score += 8
            short_reasons.append("1h RSI")

        elif rsi1h < 30:
            short_score -= 15
            short_warnings.append("1h aşırı düşük")

        elif rsi1h > 65:
            short_score += 4
            short_reasons.append("1h RSI yüksek")

        elif rsi1h > 75:
            short_score -= 12
            short_warnings.append("1h aşırı alım")

        # RSI 4h

        if 35 <= rsi4h <= 55:
            short_score += 8
            short_reasons.append("4h RSI")

        elif rsi4h < 35:
            short_score -= 10
            short_warnings.append("4h RSI çok düşük")

        elif rsi4h > 65:
            short_score -= 6
            short_warnings.append("4h RSI güçlü")

        # EMA

        if price < ema9 < ema21:
            short_score += 8
            short_reasons.append("EMA9/21")

        if price < ema50:
            short_score += 6
            short_reasons.append("EMA50")

        if price < ema21_4h < ema50_4h:
            short_score += 10
            short_reasons.append("4h düşüş trendi")

        elif price < ema50_4h:
            short_score += 4
            short_reasons.append("4h EMA50")

        else:
            short_score -= 8
            short_warnings.append("4h güçlü")

        # MACD

        if macd15 < signal15 and hist15 < 0:
            short_score += 7
            short_reasons.append("MACD")

        if macd1h < signal1h and hist1h < 0:
            short_score += 9
            short_reasons.append("1h MACD")

        # Stoch RSI

        if 20 <= stoch <= 80:
            short_score += 7
            short_reasons.append("Stoch RSI")

        elif stoch < 20:
            short_score -= 3
            short_warnings.append("Stoch RSI düşük")

        elif stoch > 90:
            short_score += 3
            short_reasons.append("Stoch RSI dönüş bölgesi")

        # Bollinger

        if lower < price < middle:
            short_score += 4
            short_reasons.append("Bollinger")

        elif price < lower:
            short_score -= 5
            short_warnings.append("BB altı")

        # OBV

        if len(obv_values) >= 6:
            if obv_values[-1] < obv_values[-5]:
                short_score += 4
                short_reasons.append("OBV")

        # Supertrend

        if not st15:
            short_score += 4
            short_reasons.append("Supertrend")

        if not st1h:
            short_score += 4
            short_reasons.append("1h Supertrend")

        # TDI

        if tdi_rsi < tdi_signal and 30 < tdi_rsi < 55:
            short_score += 4
            short_reasons.append("TDI")

        # Momentum

        if -4 <= momentum <= -0.5:
            short_score += 6
            short_reasons.append("Momentum")

        elif momentum > 0:
            short_score -= 12
            short_warnings.append("Momentum pozitif")

        elif momentum < -7:
            short_score -= 8
            short_warnings.append("Aşırı hızlı düşüş")

        # Volume

        if volume_ratio >= 3:
            short_score += 12
            short_reasons.append(f"Hacim x{volume_ratio:.1f}")

        elif volume_ratio >= 2:
            short_score += 10
            short_reasons.append(f"Hacim x{volume_ratio:.1f}")

        elif volume_ratio >= 1.5:
            short_score += 7
            short_reasons.append(f"Hacim x{volume_ratio:.1f}")

        else:
            short_score += 2
            short_warnings.append("Hacim düşük")

        # ==================================================
        # HARD FILTERS
        # ==================================================

        long_valid = True
        short_valid = True

        # Hacim filtresi
        if volume_ratio < 1.2:
            long_valid = False
            short_valid = False

        # LONG hard filters
        if stoch > 92:
            long_valid = False

        if rsi1h > 78:
            long_valid = False

        if momentum < 0:
            long_valid = False

        if rsi4h < 40 and price < ema50_4h:
            long_valid = False

        # SHORT hard filters
        if stoch < 8:
            short_valid = False

        if rsi1h < 25:
            short_valid = False

        if momentum > 0:
            short_valid = False

        if rsi4h > 70 and price > ema50_4h:
            short_valid = False

        # ==================================================
        # NORMALIZE
        # ==================================================

        long_score = max(
            0,
            min(100, long_score)
        )

        short_score = max(
            0,
            min(100, short_score)
        )

        # ==================================================
        # LONG SIGNAL
        # ==================================================

        long_conditions = [
            volume_ratio >= 1.5,
            momentum >= 0.5,
            50 <= rsi15 <= 68,
            50 <= rsi1h <= 70,
            rsi4h >= 45,
            20 <= stoch <= 80,
            macd1h > signal1h,
            price > ema9 > ema21
        ]

        long_count = sum(long_conditions)

        if (
            long_valid
            and long_score >= 82
            and long_count >= 7
        ):
            long_signal = "🟢 GÜÇLÜ AL"

        elif (
            long_valid
            and long_score >= 72
            and long_count >= 5
        ):
            long_signal = "🟢 AL ADAYI"

        elif long_valid and long_score >= 65:
            long_signal = "🟡 İZLE"

        else:
            long_signal = None

        if long_signal == "🟢 GÜÇLÜ AL":

            if volume_ratio < 1.5:
                long_signal = "🟢 AL ADAYI"

            if stoch > 80:
                long_signal = "🟢 AL ADAYI"

            if rsi1h > 70:
                long_signal = "🟢 AL ADAYI"

            if rsi4h < 45:
                long_signal = "🟢 AL ADAYI"

        # ==================================================
        # SHORT SIGNAL
        # ==================================================

        short_conditions = [
            volume_ratio >= 1.5,
            momentum <= -0.5,
            32 <= rsi15 <= 50,
            30 <= rsi1h <= 55,
            rsi4h <= 55,
            20 <= stoch <= 80,
            macd1h < signal1h,
            price < ema9 < ema21
        ]

        short_count = sum(short_conditions)

        if (
            short_valid
            and short_score >= 82
            and short_count >= 7
        ):
            short_signal = "🔴 GÜÇLÜ SAT / SHORT"

        elif (
            short_valid
            and short_score >= 72
            and short_count >= 5
        ):
            short_signal = "🔴 SHORT ADAYI"

        elif short_valid and short_score >= 65:
            short_signal = "🟠 SHORT İZLE"

        else:
            short_signal = None

        if short_signal == "🔴 GÜÇLÜ SAT / SHORT":

            if volume_ratio < 1.5:
                short_signal = "🔴 SHORT ADAYI"

            if stoch < 20:
                short_signal = "🔴 SHORT ADAYI"

            if rsi1h < 30:
                short_signal = "🔴 SHORT ADAYI"

            if rsi4h > 55:
                short_signal = "🔴 SHORT ADAYI"

        # ==================================================
        # ATR TARGETS
        # ==================================================

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

            "rsi15": rsi15,
            "rsi1h": rsi1h,
            "rsi4h": rsi4h,
            "stoch": stoch,
            "volume": volume_ratio,
            "momentum": momentum,

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


def main():

    print(
        "🚀 LONG + SHORT BINANCE SCANNER BAŞLADI..."
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

    # ==================================================
    # LONG LIST
    # ==================================================

    long_results = [
        x for x in results
        if x["long_signal"] is not None
        and x["long_score"] >= 65
    ]

    long_results.sort(
        key=lambda x: x["long_score"],
        reverse=True
    )

    long_results = long_results[:5]

    # ==================================================
    # SHORT LIST
    # ==================================================

    short_results = [
        x for x in results
        if x["short_signal"] is not None
        and x["short_score"] >= 65
    ]

    short_results.sort(
        key=lambda x: x["short_score"],
        reverse=True
    )

    short_results = short_results[:5]

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

        "🔥 Hacim + Momentum filtresi\n"

        "🎯 ATR + R/R hedefleme\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # ==================================================
    # LONG
    # ==================================================

    message += "📈 LONG FIRSATLARI\n\n"

    if not long_results:

        message += (
            "🟡 Şu anda trade edilebilir "
            "LONG sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            long_results,
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
                f"{coin['rsi15']:.1f}"
                f" | 1h: "
                f"{coin['rsi1h']:.1f}"
                f" | 4h: "
                f"{coin['rsi4h']:.1f}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"🧠 Pozitif: "
                f"{', '.join(coin['long_reasons'][:8])}\n"
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

    # ==================================================
    # SHORT
    # ==================================================

    message += (
        "━━━━━━━━━━━━━━━━━━\n\n"
        "📉 SHORT FIRSATLARI\n\n"
    )

    if not short_results:

        message += (
            "🟡 Şu anda trade edilebilir "
            "SHORT sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            short_results,
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
                f"{coin['rsi15']:.1f}"
                f" | 1h: "
                f"{coin['rsi1h']:.1f}"
                f" | 4h: "
                f"{coin['rsi4h']:.1f}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📊 Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"🧠 Negatif: "
                f"{', '.join(coin['short_reasons'][:8])}\n"
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
        "━━━━━━━━━━━━━━━━━━\n"

        "⚠️ Teknik sinyal sistemidir. "
        "Yatırım tavsiyesi değildir."
    )

    print(message)

    send_telegram(message)


if __name__ == "__main__":
    main()
