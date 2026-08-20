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


# ============================================================
# PUMP RADARI
# ============================================================

def pump_scan(symbol):

    try:

        close, high, low, volume = get_klines(
            symbol,
            "15m",
            100
        )

        if len(close) < 30:
            return None

        price = close[-1]

        # ----------------------------------------------------
        # HACİM
        # ----------------------------------------------------

        avg_volume = sum(
            volume[-21:-1]
        ) / 20

        if avg_volume <= 0:
            return None

        volume_ratio = (
            volume[-1] / avg_volume
        )

        # Pump radarının minimum hacim şartı
        if volume_ratio < 2.0:
            return None

        # ----------------------------------------------------
        # MOMENTUM
        # ----------------------------------------------------

        momentum_15m = (
            (price / close[-5]) - 1
        ) * 100

        momentum_1h = (
            (price / close[-17]) - 1
        ) * 100

        # En az kısa vadeli hareket
        if momentum_15m < 1.5:
            return None

        # ----------------------------------------------------
        # EMA
        # ----------------------------------------------------

        ema9 = ema(close, 9)
        ema21 = ema(close, 21)

        ema_bullish = (
            price > ema9 > ema21
        )

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        rsi15 = rsi(close)

        # ----------------------------------------------------
        # STOCH RSI
        # ----------------------------------------------------

        stoch = stoch_rsi(close)

        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        macd_line, macd_signal, macd_hist = macd(close)

        # ----------------------------------------------------
        # OBV
        # ----------------------------------------------------

        obv_values = obv(
            close,
            volume
        )

        obv_rising = False

        if len(obv_values) >= 6:

            obv_rising = (
                obv_values[-1]
                >
                obv_values[-5]
            )

        # ----------------------------------------------------
        # SON MUM GÜCÜ
        # ----------------------------------------------------

        candle_change = (
            (close[-1] / close[-2]) - 1
        ) * 100

        # ----------------------------------------------------
        # PUMP SCORE
        # ----------------------------------------------------

        score = 0
        reasons = []

        # Hacim

        if volume_ratio >= 10:
            score += 30
            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 5:
            score += 25
            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 3:
            score += 20
            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:
            score += 12
            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        # Momentum

        if momentum_15m >= 7:
            score += 25
            reasons.append(
                f"15m momentum +{momentum_15m:.1f}%"
            )

        elif momentum_15m >= 4:
            score += 20
            reasons.append(
                f"15m momentum +{momentum_15m:.1f}%"
            )

        elif momentum_15m >= 2.5:
            score += 15
            reasons.append(
                f"15m momentum +{momentum_15m:.1f}%"
            )

        elif momentum_15m >= 1.5:
            score += 8
            reasons.append(
                f"15m momentum +{momentum_15m:.1f}%"
            )

        # 1h momentum

        if momentum_1h >= 8:
            score += 15
            reasons.append(
                f"1h momentum +{momentum_1h:.1f}%"
            )

        elif momentum_1h >= 4:
            score += 10
            reasons.append(
                f"1h momentum +{momentum_1h:.1f}%"
            )

        elif momentum_1h >= 2:
            score += 5
            reasons.append(
                f"1h momentum +{momentum_1h:.1f}%"
            )

        # EMA

        if ema_bullish:
            score += 10
            reasons.append(
                "EMA9 > EMA21"
            )

        # MACD

        if macd_line > macd_signal and macd_hist > 0:
            score += 8
            reasons.append(
                "MACD pozitif"
            )

        # OBV

        if obv_rising:
            score += 7
            reasons.append(
                "OBV yükseliyor"
            )

        # Mum

        if candle_change >= 3:
            score += 8
            reasons.append(
                f"Son mum +{candle_change:.1f}%"
            )

        elif candle_change >= 1:
            score += 4
            reasons.append(
                f"Son mum +{candle_change:.1f}%"
            )

        # ----------------------------------------------------
        # PUMP SINIFI
        # ----------------------------------------------------

        score = max(
            0,
            min(100, score)
        )

        if score >= 85:

            signal = "🚀 PUMP BAŞLANGICI"

        elif score >= 75:

            signal = "🔥 PUMP ADAYI"

        else:

            signal = "👀 HAREKETLENME"

        # ----------------------------------------------------
        # Çok küçük hareketleri ele
        # ----------------------------------------------------

        if (
            volume_ratio < 2
            or momentum_15m < 1.5
        ):
            return None

        return {
            "symbol": symbol,
            "price": price,
            "score": score,
            "signal": signal,
            "rsi": rsi15,
            "stoch": stoch,
            "volume": volume_ratio,
            "momentum15": momentum_15m,
            "momentum1h": momentum_1h,
            "candle": candle_change,
            "reasons": reasons
        }

    except Exception as e:

        print(
            f"{symbol} pump analiz hatası: {e}"
        )

        return None


# ============================================================
# LONG / SHORT ANALİZİ
# ============================================================

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

        long_score = 0
        short_score = 0

        long_reasons = []
        short_reasons = []

        long_warnings = []
        short_warnings = []

        # ====================================================
        # RSI
        # ====================================================

        rsi15 = rsi(close15)
        rsi1h = rsi(close1h)
        rsi4h = rsi(close4h)

        # LONG RSI

        if 50 <= rsi15 <= 65:
            long_score += 8
            long_reasons.append("RSI ideal")

        elif 65 < rsi15 <= 70:
            long_score += 4

        elif rsi15 > 70:
            long_score -= 8
            long_warnings.append("RSI yüksek")

        elif rsi15 < 45:
            long_score -= 6
            long_warnings.append("RSI zayıf")

        # SHORT RSI

        if 35 <= rsi15 <= 50:
            short_score += 8
            short_reasons.append("RSI short bölgesi")

        elif 30 <= rsi15 < 35:
            short_score += 4

        elif rsi15 < 30:
            short_score -= 8
            short_warnings.append("RSI aşırı satım")

        elif rsi15 > 55:
            short_score -= 6
            short_warnings.append("RSI güçlü")

        # 1H LONG

        if 50 <= rsi1h <= 65:
            long_score += 8
            long_reasons.append("1h RSI")

        elif 65 < rsi1h <= 70:
            long_score += 3

        elif rsi1h > 70:
            long_score -= 8
            long_warnings.append("1h RSI yüksek")

        elif rsi1h < 40:
            long_score -= 10
            long_warnings.append("1h RSI zayıf")

        # 1H SHORT

        if 35 <= rsi1h <= 50:
            short_score += 8
            short_reasons.append("1h RSI")

        elif 30 <= rsi1h < 35:
            short_score += 3

        elif rsi1h < 30:
            short_score -= 8
            short_warnings.append("1h aşırı satım")

        elif rsi1h > 60:
            short_score -= 10
            short_warnings.append("1h RSI güçlü")

        # 4H LONG

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

        # 4H SHORT

        if 35 <= rsi4h <= 55:
            short_score += 8
            short_reasons.append("4h RSI")

        elif 30 <= rsi4h < 35:
            short_score += 3

        elif rsi4h < 30:
            short_score -= 10
            short_warnings.append("4h aşırı satım")

        elif rsi4h > 60:
            short_score -= 10
            short_warnings.append("4h güçlü")

        # ====================================================
        # EMA
        # ====================================================

        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)

        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)

        # LONG

        if price > ema9 and ema9 > ema21:
            long_score += 8
            long_reasons.append("EMA9/21")

        elif price < ema21:
            long_score -= 5

        if price > ema50:
            long_score += 5
            long_reasons.append("EMA50")

        if price > ema21_4h and ema21_4h > ema50_4h:
            long_score += 10
            long_reasons.append("4h trend")

        elif price > ema50_4h:
            long_score += 3
            long_reasons.append("4h EMA50")

        else:
            long_score -= 8
            long_warnings.append("4h zayıf")

        # SHORT

        if price < ema9 and ema9 < ema21:
            short_score += 8
            short_reasons.append("EMA9/21")

        elif price > ema21:
            short_score -= 5

        if price < ema50:
            short_score += 5
            short_reasons.append("EMA50")

        if price < ema21_4h and ema21_4h < ema50_4h:
            short_score += 10
            short_reasons.append("4h düşüş trendi")

        elif price < ema50_4h:
            short_score += 3
            short_reasons.append("4h EMA50")

        else:
            short_score -= 8
            short_warnings.append("4h güçlü")

        # ====================================================
        # MACD
        # ====================================================

        macd15, signal15, hist15 = macd(close15)
        macd1h, signal1h, hist1h = macd(close1h)

        if macd15 < signal15 and hist15 < 0:
            short_score += 7
            short_reasons.append("MACD")

        if macd1h < signal1h and hist1h < 0:
            short_score += 9
            short_reasons.append("1h MACD")

        if macd15 > signal15 and hist15 > 0:
            long_score += 7
            long_reasons.append("MACD")

        if macd1h > signal1h and hist1h > 0:
            long_score += 9
            long_reasons.append("1h MACD")

        # ====================================================
        # STOCH RSI
        # ====================================================

        stoch = stoch_rsi(close15)

        if 20 <= stoch <= 80:

            long_score += 7
            long_reasons.append("Stoch RSI")

            short_score += 7
            short_reasons.append("Stoch RSI")

        elif stoch > 80:

            long_score -= 4
            long_warnings.append("Stoch RSI yüksek")

        elif stoch < 20:

            short_score -= 4
            short_warnings.append("Stoch RSI düşük")

        # ====================================================
        # BOLLINGER
        # ====================================================

        upper, middle, lower = bollinger(close15)

        if middle < price < upper:
            long_score += 4
            long_reasons.append("Bollinger")

        if lower < price < middle:
            short_score += 4
            short_reasons.append("Bollinger")

        # ====================================================
        # OBV
        # ====================================================

        obv_values = obv(close15, vol15)

        if len(obv_values) >= 6:

            if obv_values[-1] > obv_values[-5]:
                long_score += 4
                long_reasons.append("OBV")

            elif obv_values[-1] < obv_values[-5]:
                short_score += 4
                short_reasons.append("OBV")

        # ====================================================
        # SUPERTREND
        # ====================================================

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

        if st15:
            long_score += 4
            long_reasons.append("Supertrend")

        else:
            short_score += 4
            short_reasons.append("Supertrend")

        if st1h:
            long_score += 4
            long_reasons.append("1h Supertrend")

        else:
            short_score += 4
            short_reasons.append("1h Supertrend")

        # ====================================================
        # MOMENTUM
        # ====================================================

        momentum = (
            (price / close15[-5]) - 1
        ) * 100

        if 0.5 <= momentum <= 4:
            long_score += 6
            long_reasons.append("Momentum")

        elif momentum > 7:
            long_score -= 8
            long_warnings.append("Aşırı hızlı yükseliş")

        if -4 <= momentum <= -0.5:
            short_score += 6
            short_reasons.append("Momentum")

        elif momentum < -7:
            short_score -= 8
            short_warnings.append("Aşırı hızlı düşüş")

        # ====================================================
        # VOLUME
        # ====================================================

        avg_volume = sum(
            vol15[-21:-1]
        ) / 20

        if avg_volume <= 0:
            return None

        volume_ratio = (
            vol15[-1] / avg_volume
        )

        # LONG / SHORT minimum hacim

        if volume_ratio < 1.2:
            return None

        if volume_ratio >= 3:
            long_score += 12
            short_score += 12

        elif volume_ratio >= 2:
            long_score += 10
            short_score += 10

        elif volume_ratio >= 1.5:
            long_score += 7
            short_score += 7

        else:
            long_score += 2
            short_score += 2

        # ====================================================
        # NORMAL LONG HARD FILTER
        # ====================================================

        long_valid = True

        if stoch > 90:
            long_valid = False

        if rsi1h > 75:
            long_valid = False

        if rsi4h < 40:
            long_valid = False

        if momentum < 0:
            long_valid = False

        if (
            rsi4h < 43
            and price < ema50_4h
        ):
            long_valid = False

        # ====================================================
        # NORMAL SHORT HARD FILTER
        # ====================================================

        short_valid = True

        if stoch < 10:
            short_valid = False

        if rsi1h < 25:
            short_valid = False

        if rsi4h > 60:
            short_valid = False

        if momentum > 0:
            short_valid = False

        if (
            rsi4h > 57
            and price > ema50_4h
        ):
            short_valid = False

        # ====================================================
        # NORMAL SIGNAL
        # ====================================================

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

        if long_valid:

            if long_score >= 85:
                long_signal = "🟢 GÜÇLÜ AL"

            elif long_score >= 75:
                long_signal = "🟢 AL ADAYI"

        if short_valid:

            if short_score >= 85:
                short_signal = "🔴 GÜÇLÜ SAT"

            elif short_score >= 75:
                short_signal = "🔴 SAT ADAYI"

        # ====================================================
        # ATR
        # ====================================================

        true_ranges = []

        for i in range(
            len(close15) - 14,
            len(close15)
        ):

            tr = max(
                high15[i] - low15[i],
                abs(
                    high15[i]
                    - close15[i - 1]
                ),
                abs(
                    low15[i]
                    - close15[i - 1]
                )
            )

            true_ranges.append(tr)

        atr = sum(
            true_ranges
        ) / len(true_ranges)

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
            "short_score": short_score,

            "long_signal": long_signal,
            "short_signal": short_signal,

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
            "short_tp3": short_tp3,

            "long_reasons": long_reasons,
            "short_reasons": short_reasons,

            "long_warnings": long_warnings,
            "short_warnings": short_warnings
        }

    except Exception as e:

        print(
            f"{symbol} analiz hatası: {e}"
        )

        return None


# ============================================================
# MAIN
# ============================================================

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
    pump_results = []

    for symbol, _ in candidates:

        print(
            f"Analiz: {symbol}"
        )

        result = analyze(symbol)

        if result:
            results.append(result)

        pump = pump_scan(symbol)

        if pump:
            pump_results.append(pump)

    # ========================================================
    # LONG
    # ========================================================

    long_results = [
        x for x in results
        if x["long_signal"] is not None
    ]

    long_results.sort(
        key=lambda x: x["long_score"],
        reverse=True
    )

    long_results = long_results[:5]

    # ========================================================
    # SHORT
    # ========================================================

    short_results = [
        x for x in results
        if x["short_signal"] is not None
    ]

    short_results.sort(
        key=lambda x: x["short_score"],
        reverse=True
    )

    short_results = short_results[:5]

    # ========================================================
    # PUMP
    # ========================================================

    pump_results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    pump_results = pump_results[:5]

    # ========================================================
    # MESSAGE
    # ========================================================

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )

    message = (
        "🚨 GELİŞMİŞ BINANCE "
        "LONG + SHORT + PUMP TARAMASI\n\n"

        f"🕐 {now}\n"

        "📊 15m + 1h + 4h\n"

        "🧠 RSI • Stoch RSI • MACD • EMA\n"

        "📈 BB • TDI • OBV • Supertrend\n"

        "🔥 Hacim + Momentum filtresi\n"

        "🎯 ATR + R/R hedefleme\n"

        "🚀 Pump Radar aktif\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # ========================================================
    # LONG MESSAGE
    # ========================================================

    message += (
        "📈 LONG FIRSATLARI\n\n"
    )

    if not long_results:

        message += (
            "🟡 Şu anda trade edilebilir "
            "LONG sinyali yok.\n"
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

                "📐 TP3 R/R: 1 : 2\n\n"
            )

    message += (
        "\n━━━━━━━━━━━━━━━━━━\n\n"
        "📉 SHORT FIRSATLARI\n\n"
    )

    # ========================================================
    # SHORT MESSAGE
    # ========================================================

    if not short_results:

        message += (
            "🟡 Şu anda trade edilebilir "
            "SHORT sinyali yok.\n"
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

                f"🧠 Pozitif: "
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

                "📐 TP3 R/R: 1 : 2\n\n"
            )

    # ========================================================
    # PUMP RADAR MESSAGE
    # ========================================================

    message += (
        "\n━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 PUMP RADARI\n\n"
    )

    if not pump_results:

        message += (
            "🟡 Şu anda olağandışı "
            "pump hareketi yok.\n"
        )

    else:

        for i, coin in enumerate(
            pump_results,
            1
        ):

            message += (

                f"🚀 {i}. "
                f"{coin['symbol']}\n"

                f"{coin['signal']}\n"

                f"⭐ Pump gücü: "
                f"{coin['score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"🚀 15m Momentum: "
                f"{coin['momentum15']:+.1f}%\n"

                f"📈 1h Momentum: "
                f"{coin['momentum1h']:+.1f}%\n"

                f"📊 RSI: "
                f"{coin['rsi']:.1f}\n"

                f"⚡ Stoch RSI: "
                f"{coin['stoch']:.1f}\n"

                f"🕯️ Son mum: "
                f"{coin['candle']:+.1f}%\n"

                f"🧠 Sinyaller: "
                f"{', '.join(coin['reasons'][:7])}\n\n"

                "⚠️ Pump radarı erken hareket "
                "alarmıdır. Kovalamaca sinyali değildir.\n\n"
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
