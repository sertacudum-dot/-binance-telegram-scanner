import os
import json
import urllib.request
import urllib.parse
import math
from datetime import datetime, timezone

BINANCE = "https://data-api.binance.vision"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


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

    url = (
        f"https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()

    req = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=20) as r:
        print("Telegram mesajı gönderildi.")
        return r.read()


# =========================================================
# BINANCE DATA
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

    if len(values) < period * 2:
        return 50, 50

    rsi_values = []

    for i in range(period, len(values)):

        rsi_values.append(
            rsi(values[:i + 1], period)
        )

    if len(rsi_values) < period:
        return 50, 50

    recent = rsi_values[-period:]

    lowest = min(recent)
    highest = max(recent)

    if highest == lowest:
        stoch = 50
    else:
        stoch = (
            (rsi_values[-1] - lowest)
            / (highest - lowest)
        ) * 100

    k_values = []

    for i in range(
        max(0, len(rsi_values) - 3),
        len(rsi_values)
    ):

        window = rsi_values[
            max(0, i - period + 1):i + 1
        ]

        lo = min(window)
        hi = max(window)

        if hi == lo:
            k_values.append(50)
        else:
            k_values.append(
                (
                    (rsi_values[i] - lo)
                    / (hi - lo)
                ) * 100
            )

    k = k_values[-1]

    d = sum(k_values) / len(k_values)

    return k, d


def macd(values):

    ema12 = ema(values, 12)
    ema26 = ema(values, 26)

    macd_line = ema12 - ema26

    # Signal için yaklaşık MACD serisi
    macd_series = []

    start = max(26, len(values) - 40)

    for i in range(start, len(values)):

        e12 = ema(values[:i + 1], 12)
        e26 = ema(values[:i + 1], 26)

        macd_series.append(e12 - e26)

    signal = ema(macd_series, 9)

    histogram = macd_line - signal

    return macd_line, signal, histogram


def bollinger(values, period=20, mult=2):

    recent = values[-period:]

    middle = sum(recent) / len(recent)

    variance = sum(
        (x - middle) ** 2
        for x in recent
    ) / len(recent)

    std = math.sqrt(variance)

    upper = middle + mult * std
    lower = middle - mult * std

    return upper, middle, lower


def obv(values, volumes):

    result = 0

    obv_values = [0]

    for i in range(1, len(values)):

        if values[i] > values[i - 1]:
            result += volumes[i]

        elif values[i] < values[i - 1]:
            result -= volumes[i]

        obv_values.append(result)

    return obv_values


def supertrend(high, low, close, period=10, multiplier=3):

    if len(close) < period + 2:
        return True

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

    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    return close[-1] > lower


def tdi(values):

    r = rsi(values, 13)

    r2 = rsi(values[:-1], 13)

    signal = (
        r * 0.7 +
        r2 * 0.3
    )

    return r, signal


# =========================================================
# FILTERS
# =========================================================

STABLECOINS = {
    "USDT",
    "USDC",
    "FDUSD",
    "USDE",
    "TUSD",
    "DAI",
    "RLUSD",
    "USD1",
    "USDD"
}


def is_stablecoin_pair(symbol):

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

        score = 0
        reasons = []
        warnings = []


        # -------------------------------------------------
        # 15M RSI
        # -------------------------------------------------

        rsi15 = rsi(close15)

        if 50 <= rsi15 <= 65:

            score += 8
            reasons.append("RSI ideal")

        elif 65 < rsi15 <= 70:

            score += 3

        elif rsi15 > 70:

            score -= 8
            warnings.append("RSI yüksek")

        elif rsi15 < 45:

            score -= 5


        # -------------------------------------------------
        # 1H RSI
        # -------------------------------------------------

        rsi1h = rsi(close1h)

        if 50 <= rsi1h <= 65:

            score += 8
            reasons.append("1h RSI")

        elif 65 < rsi1h <= 70:

            score += 3

        elif rsi1h > 75:

            score -= 10
            warnings.append("1h aşırı alım")

        elif rsi1h < 45:

            score -= 5


        # -------------------------------------------------
        # 4H TREND
        # -------------------------------------------------

        rsi4h = rsi(close4h)

        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)

        if (
            price > ema21_4h
            and ema21_4h > ema50_4h
        ):

            score += 10
            reasons.append("4h trend")

        elif price < ema50_4h:

            score -= 8
            warnings.append("4h zayıf")


        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)

        if price > ema9 > ema21:

            score += 8
            reasons.append("EMA9/21")

        if price > ema50:

            score += 5
            reasons.append("EMA50")


        # -------------------------------------------------
        # MACD
        # -------------------------------------------------

        macd15, signal15, hist15 = macd(close15)

        macd1h, signal1h, hist1h = macd(close1h)

        if macd15 > signal15 and hist15 > 0:

            score += 8
            reasons.append("MACD")

        if macd1h > signal1h and hist1h > 0:

            score += 8
            reasons.append("1h MACD")


        # -------------------------------------------------
        # STOCH RSI
        # -------------------------------------------------

        stoch_k, stoch_d = stoch_rsi(close15)

        if (
            stoch_k > stoch_d
            and stoch_k < 80
        ):

            score += 7
            reasons.append("Stoch RSI")

        elif stoch_k > 90:

            score -= 5
            warnings.append("Stoch RSI yüksek")


        # -------------------------------------------------
        # BOLLINGER
        # -------------------------------------------------

        upper, middle, lower = bollinger(close15)

        if (
            middle < price < upper
            and price > close15[-2]
        ):

            score += 5
            reasons.append("Bollinger")


        if price > upper:

            score -= 5
            warnings.append("BB üstü")


        # -------------------------------------------------
        # OBV
        # -------------------------------------------------

        obv_values = obv(
            close15,
            vol15
        )

        if len(obv_values) >= 6:

            if (
                obv_values[-1]
                > obv_values[-5]
            ):

                score += 7
                reasons.append("OBV")


        # -------------------------------------------------
        # SUPERTREND
        # -------------------------------------------------

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

            score += 5
            reasons.append("Supertrend")

        if st1h:

            score += 5
            reasons.append("1h Supertrend")


        # -------------------------------------------------
        # TDI
        # -------------------------------------------------

        tdi_rsi, tdi_signal = tdi(close15)

        if (
            tdi_rsi > tdi_signal
            and 50 < tdi_rsi < 70
        ):

            score += 6
            reasons.append("TDI")


        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        avg_volume = (
            sum(vol15[-20:]) / 20
        )

        volume_ratio = (
            vol15[-1] / avg_volume
            if avg_volume
            else 1
        )

        if volume_ratio >= 2.5:

            score += 12
            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.8:

            score += 9
            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.3:

            score += 5

        elif volume_ratio < 0.7:

            score -= 8
            warnings.append("Hacim zayıf")


        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        momentum = (
            (price / close15[-5]) - 1
        ) * 100

        if 0.5 <= momentum <= 5:

            score += 7
            reasons.append("Momentum")

        elif momentum > 8:

            score -= 5
            warnings.append("Çok yükselmiş")


        # -------------------------------------------------
        # FINAL SCORE
        # -------------------------------------------------

        score = max(
            0,
            min(100, score)
        )


        # -------------------------------------------------
        # SIGNAL
        # -------------------------------------------------

        if score >= 80:

            signal = "🟢 GÜÇLÜ AL"

        elif score >= 70:

            signal = "🟢 AL ADAYI"

        elif score >= 60:

            signal = "🟡 İZLE"

        else:

            signal = "⚪ ZAYIF"


        # -------------------------------------------------
        # RISK
        # -------------------------------------------------

        ranges = []

        for i in range(
            len(close15) - 14,
            len(close15)
        ):

            ranges.append(
                max(
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
            )

        atr = sum(ranges) / len(ranges)

        sl = price - atr * 1.5

        tp1 = price + atr * 1.2

        tp2 = price + atr * 2.0

        tp3 = price + atr * 3.0


        return {

            "symbol": symbol,
            "price": price,
            "score": score,
            "signal": signal,

            "rsi15": rsi15,
            "rsi1h": rsi1h,
            "rsi4h": rsi4h,

            "stoch": stoch_k,

            "volume": volume_ratio,

            "momentum": momentum,

            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,

            "reasons": reasons,
            "warnings": warnings
        }


    except Exception as e:

        print(
            f"{symbol} analiz hatası: {e}"
        )

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


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "🚀 Gelişmiş Binance taraması başladı..."
    )


    tickers = get(
        BINANCE +
        "/api/v3/ticker/24hr"
    )


    candidates = []


    for ticker in tickers:

        symbol = ticker["symbol"]


        if not symbol.endswith("USDT"):

            continue


        if is_stablecoin_pair(symbol):

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

            volume = float(
                ticker["quoteVolume"]
            )

            if volume < 5000000:

                continue

            candidates.append(
                (symbol, volume)
            )

        except:

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

        result = analyze(symbol)

        if result:

            # Zayıf hacim + aşırı alım
            # kombinasyonlarını ele

            if (
                result["volume"] < 0.8
                and result["score"] < 75
            ):

                continue


            results.append(result)


    # Önce güçlü sinyaller

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    # İlk 10

    top10 = results[:10]


    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )


    message = (
        "🚨 GELİŞMİŞ BINANCE AL TARAMASI\n\n"
        f"🕐 {now}\n"
        "📊 15m + 1h + 4h\n"
        "🧠 RSI • Stoch RSI • MACD • EMA\n"
        "📈 BB • TDI • OBV • Supertrend\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )


    for i, coin in enumerate(
        top10,
        1
    ):

        message += (

            f"🏆 {i}. {coin['symbol']}\n"

            f"{coin['signal']}\n"

            f"⭐ Sinyal gücü: "
            f"{coin['score']}/100\n\n"

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
            f"{', '.join(coin['reasons'][:6])}\n"
        )


        if coin["warnings"]:

            message += (
                f"⚠️ "
                f"{', '.join(coin['warnings'][:3])}\n"
            )


        message += (

            f"\n🛑 SL: "
            f"{price_format(coin['sl'])}\n"

            f"🎯 TP1: "
            f"{price_format(coin['tp1'])}\n"

            f"🎯 TP2: "
            f"{price_format(coin['tp2'])}\n"

            f"🎯 TP3: "
            f"{price_format(coin['tp3'])}\n\n"
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
