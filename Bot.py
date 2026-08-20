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

    url = (
        f"https://api.telegram.org/bot"
        f"{TOKEN}/sendMessage"
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

    with urllib.request.urlopen(
        req,
        timeout=20
    ) as r:

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

    url = (
        BINANCE
        + "/api/v3/klines?"
        + params
    )

    data = get(url)

    close = [
        float(x[4])
        for x in data
    ]

    high = [
        float(x[2])
        for x in data
    ]

    low = [
        float(x[3])
        for x in data
    ]

    volume = [
        float(x[5])
        for x in data
    ]

    return close, high, low, volume


# =========================================================
# EMA
# =========================================================

def ema(values, period):

    if len(values) < period:
        return values[-1]

    multiplier = 2 / (period + 1)

    result = (
        sum(values[:period])
        / period
    )

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

        change = (
            values[i]
            - values[i - 1]
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    avg_gain = (
        sum(gains[:period])
        / period
    )

    avg_loss = (
        sum(losses[:period])
        / period
    )

    for i in range(
        period,
        len(gains)
    ):

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

    return 100 - (
        100 / (1 + rs)
    )


# =========================================================
# STOCH RSI
# =========================================================

def stoch_rsi(values, period=14):

    rsi_values = []

    for i in range(
        period,
        len(values)
    ):

        rsi_values.append(
            rsi(
                values[:i + 1],
                period
            )
        )

    if len(rsi_values) < period:
        return 50

    recent = rsi_values[-period:]

    lowest = min(recent)
    highest = max(recent)

    if highest == lowest:
        return 50

    return (
        (
            rsi_values[-1]
            - lowest
        )
        /
        (
            highest
            - lowest
        )
    ) * 100


# =========================================================
# MACD
# =========================================================

def macd(values):

    if len(values) < 35:
        return 0, 0, 0

    macd_values = []

    for i in range(
        26,
        len(values)
    ):

        e12 = ema(
            values[:i + 1],
            12
        )

        e26 = ema(
            values[:i + 1],
            26
        )

        macd_values.append(
            e12 - e26
        )

    line = macd_values[-1]

    signal = ema(
        macd_values,
        9
    )

    histogram = (
        line - signal
    )

    return (
        line,
        signal,
        histogram
    )


# =========================================================
# BOLLINGER
# =========================================================

def bollinger(values, period=20):

    recent = values[-period:]

    middle = (
        sum(recent)
        / len(recent)
    )

    variance = (
        sum(
            (x - middle) ** 2
            for x in recent
        )
        / len(recent)
    )

    std = math.sqrt(
        variance
    )

    upper = middle + (
        2 * std
    )

    lower = middle - (
        2 * std
    )

    return (
        upper,
        middle,
        lower
    )


# =========================================================
# OBV
# =========================================================

def obv(values, volumes):

    result = 0

    output = [0]

    for i in range(
        1,
        len(values)
    ):

        if values[i] > values[i - 1]:

            result += volumes[i]

        elif values[i] < values[i - 1]:

            result -= volumes[i]

        output.append(result)

    return output


# =========================================================
# SUPERTREND
# =========================================================

def supertrend(
    high,
    low,
    close,
    period=10,
    multiplier=3
):

    if len(close) < period + 2:
        return False

    trs = []

    for i in range(
        1,
        len(close)
    ):

        tr = max(
            high[i] - low[i],
            abs(
                high[i]
                - close[i - 1]
            ),
            abs(
                low[i]
                - close[i - 1]
            )
        )

        trs.append(tr)

    atr = (
        sum(trs[-period:])
        / period
    )

    hl2 = (
        high[-1]
        + low[-1]
    ) / 2

    lower_band = (
        hl2
        - multiplier * atr
    )

    return close[-1] > lower_band


# =========================================================
# TDI
# =========================================================

def tdi(values):

    current = rsi(
        values,
        13
    )

    previous = rsi(
        values[:-1],
        13
    )

    signal = (
        current * 0.7
        + previous * 0.3
    )

    return (
        current,
        signal
    )


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

    base = symbol.replace(
        "USDT",
        ""
    )

    return base in STABLECOINS


# =========================================================
# ANALYSIS
# =========================================================

def analyze(symbol):

    try:

        close15, high15, low15, vol15 = (
            get_klines(
                symbol,
                "15m"
            )
        )

        close1h, high1h, low1h, vol1h = (
            get_klines(
                symbol,
                "1h"
            )
        )

        close4h, high4h, low4h, vol4h = (
            get_klines(
                symbol,
                "4h"
            )
        )

        price = close15[-1]

        score = 0

        reasons = []

        warnings = []


        # =================================================
        # RSI
        # =================================================

        rsi15 = rsi(
            close15
        )

        rsi1h = rsi(
            close1h
        )

        rsi4h = rsi(
            close4h
        )


        # 15m RSI

        if 50 <= rsi15 <= 65:

            score += 10

            reasons.append(
                "RSI ideal"
            )

        elif 65 < rsi15 <= 70:

            score += 5

            reasons.append(
                "RSI güçlü"
            )

        elif rsi15 > 70:

            score -= 8

            warnings.append(
                "RSI yüksek"
            )

        elif rsi15 < 45:

            score -= 7

            warnings.append(
                "RSI zayıf"
            )


        # 1H RSI

        if 50 <= rsi1h <= 65:

            score += 10

            reasons.append(
                "1h RSI"
            )

        elif 65 < rsi1h <= 70:

            score += 4

        elif 70 < rsi1h <= 75:

            score -= 7

            warnings.append(
                "1h RSI yüksek"
            )

        elif rsi1h > 75:

            score -= 18

            warnings.append(
                "1h aşırı alım"
            )

        elif rsi1h < 40:

            score -= 10

            warnings.append(
                "1h RSI zayıf"
            )


        # 4H RSI

        if 45 <= rsi4h <= 65:

            score += 8

            reasons.append(
                "4h RSI"
            )

        elif 65 < rsi4h <= 70:

            score += 3

        elif rsi4h > 70:

            score -= 8

            warnings.append(
                "4h RSI yüksek"
            )

        elif rsi4h < 40:

            score -= 12

            warnings.append(
                "4h RSI zayıf"
            )


        # =================================================
        # EMA
        # =================================================

        ema9 = ema(
            close15,
            9
        )

        ema21 = ema(
            close15,
            21
        )

        ema50 = ema(
            close15,
            50
        )

        ema21_4h = ema(
            close4h,
            21
        )

        ema50_4h = ema(
            close4h,
            50
        )


        if (
            price > ema9
            and ema9 > ema21
        ):

            score += 8

            reasons.append(
                "EMA9/21"
            )

        elif price < ema21:

            score -= 5


        if price > ema50:

            score += 5

            reasons.append(
                "EMA50"
            )


        # 4H trend

        if (
            price > ema21_4h
            and ema21_4h > ema50_4h
        ):

            score += 12

            reasons.append(
                "4h trend"
            )

        elif price > ema50_4h:

            score += 4

            reasons.append(
                "4h EMA50"
            )

        else:

            score -= 8

            warnings.append(
                "4h zayıf"
            )


        # =================================================
        # MACD
        # =================================================

        macd15, signal15, hist15 = (
            macd(close15)
        )

        macd1h, signal1h, hist1h = (
            macd(close1h)
        )


        if (
            macd15 > signal15
            and hist15 > 0
        ):

            score += 8

            reasons.append(
                "MACD"
            )

        else:

            score -= 2


        if (
            macd1h > signal1h
            and hist1h > 0
        ):

            score += 10

            reasons.append(
                "1h MACD"
            )

        else:

            score -= 3


        # =================================================
        # STOCH RSI
        # =================================================

        stoch = stoch_rsi(
            close15
        )


        if 20 <= stoch < 80:

            score += 8

            reasons.append(
                "Stoch RSI"
            )

        elif 80 <= stoch < 90:

            score += 1

            warnings.append(
                "Stoch RSI yüksek"
            )

        elif stoch >= 90:

            score -= 15

            warnings.append(
                "Stoch RSI çok yüksek"
            )

        elif stoch < 20:

            score += 3


        # =================================================
        # BOLLINGER
        # =================================================

        upper, middle, lower = (
            bollinger(
                close15
            )
        )


        if (
            middle < price < upper
            and price > close15[-2]
        ):

            score += 5

            reasons.append(
                "Bollinger"
            )

        elif price > upper:

            score -= 5

            warnings.append(
                "BB üstü"
            )


        # =================================================
        # OBV
        # =================================================

        obv_values = obv(
            close15,
            vol15
        )


        if len(obv_values) >= 6:

            if (
                obv_values[-1]
                >
                obv_values[-5]
            ):

                score += 5

                reasons.append(
                    "OBV"
                )

            else:

                score -= 2


        # =================================================
        # SUPERTREND
        # =================================================

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

            reasons.append(
                "Supertrend"
            )

        else:

            score -= 3


        if st1h:

            score += 5

            reasons.append(
                "1h Supertrend"
            )

        else:

            score -= 3


        # =================================================
        # TDI
        # =================================================

        tdi_rsi, tdi_signal = (
            tdi(close15)
        )


        if (
            tdi_rsi > tdi_signal
            and 50 < tdi_rsi < 70
        ):

            score += 5

            reasons.append(
                "TDI"
            )


        # =================================================
        # MOMENTUM
        # =================================================

        momentum = (
            (
                price
                / close15[-5]
            ) - 1
        ) * 100


        if 0.5 <= momentum <= 4:

            score += 5

            reasons.append(
                "Momentum"
            )

        elif momentum < 0:

            score -= 6

            warnings.append(
                "Momentum negatif"
            )

        elif momentum > 7:

            score -= 6

            warnings.append(
                "Çok hızlı yükselmiş"
            )


        # =================================================
        # VOLUME
        # =================================================

        avg_volume = (
            sum(
                vol15[-21:-1]
            ) / 20
        )

        if avg_volume <= 0:
            return None

        volume_ratio = (
            vol15[-1]
            / avg_volume
        )


        # Kritik filtre:
        # 1.0x altı AL adayı yok.

        if volume_ratio < 1.0:

            print(
                f"{symbol}: "
                f"hacim yetersiz "
                f"x{volume_ratio:.2f}"
            )

            return None


        if volume_ratio >= 3:

            score += 12

            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 2:

            score += 10

            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.5:

            score += 7

            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.2:

            score += 4

            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        else:

            score += 1

            warnings.append(
                "Hacim düşük"
            )


        # =================================================
        # HARD FILTERS
        # =================================================

        # 1H + 4H aşırı alım

        if (
            rsi1h > 78
            and rsi4h > 70
        ):

            return None


        # 1H ve 4H birlikte çok zayıf

        if (
            rsi1h < 40
            and rsi4h < 40
        ):

            return None


        # Momentum negatif + 4H zayıf

        if (
            momentum < 0
            and rsi4h < 42
        ):

            return None


        # Stoch RSI aşırı yüksek + 1H RSI yüksek

        if (
            stoch > 90
            and rsi1h > 70
        ):

            return None


        # =================================================
        # SCORE
        # =================================================

        score = max(
            0,
            min(
                100,
                score
            )
        )


        # Hacim çarpanı

        if volume_ratio >= 3:

            score *= 1.10

        elif volume_ratio >= 2:

            score *= 1.06

        elif volume_ratio >= 1.5:

            score *= 1.03


        score = int(
            max(
                0,
                min(
                    100,
                    score
                )
            )
        )


        # =================================================
        # SIGNAL
        # =================================================

        if score >= 82:

            signal = "🟢 GÜÇLÜ AL"

        elif score >= 72:

            signal = "🟢 AL ADAYI"

        elif score >= 65:

            signal = "🟡 İZLE"

        else:

            signal = "⚪ ZAYIF"


        # =================================================
        # STRONG BUY SAFETY
        # =================================================

        if signal == "🟢 GÜÇLÜ AL":

            if volume_ratio < 1.5:
                signal = "🟢 AL ADAYI"

            if momentum < 0:
                signal = "🟢 AL ADAYI"

            if rsi4h < 40:
                signal = "🟢 AL ADAYI"

            if rsi1h > 75:
                signal = "🟢 AL ADAYI"

            if stoch > 90:
                signal = "🟢 AL ADAYI"


        # =================================================
        # ATR / RISK
        # =================================================

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


        atr = (
            sum(true_ranges)
            / len(true_ranges)
        )


        # Stop mesafesi

        risk = atr * 1.5

        sl = price - risk


        # R bazlı hedefler

        tp1 = price + risk * 1.0

        tp2 = price + risk * 1.5

        tp3 = price + risk * 2.0


        # =================================================
        # RISK / REWARD
        # =================================================

        rr_tp3 = (
            tp3 - price
        ) / (
            price - sl
        )


        if rr_tp3 < 1.5:

            return None


        # =================================================
        # FINAL
        # =================================================

        return {

            "symbol": symbol,

            "price": price,

            "score": score,

            "signal": signal,

            "rsi15": rsi15,

            "rsi1h": rsi1h,

            "rsi4h": rsi4h,

            "stoch": stoch,

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
# MAIN
# =========================================================

def main():

    print(
        "🚀 YENİ NESİL BINANCE "
        "TRADE SCANNER BAŞLADI..."
    )


    tickers = get(
        BINANCE
        + "/api/v3/ticker/24hr"
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


            # Minimum likidite

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


    # En likit 100 coin

    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )


    candidates = candidates[:100]


    print(
        f"{len(candidates)} coin "
        "analiz edilecek."
    )


    results = []


    for symbol, _ in candidates:

        print(
            f"Analiz: {symbol}"
        )

        result = analyze(
            symbol
        )

        if result:

            results.append(
                result
            )


    # Skora göre sırala

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    # =====================================================
    # SADECE GERÇEKTEN TRADE EDİLEBİLİR SİNYALLER
    # =====================================================

    tradable = []


    for result in results:

        # Zayıf sinyalleri gönderme

        if result["score"] < 65:
            continue


        # Güçlü AL / AL ADAYI / İZLE

        tradable.append(
            result
        )


    # En fazla 5

    tradable = tradable[:5]


    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )


    message = (
        "🚨 GERÇEKLEŞTİRİLEBİLİR "
        "BINANCE AL TARAMASI\n\n"

        f"🕐 {now}\n"

        "📊 15m + 1h + 4h\n"

        "🧠 RSI • Stoch RSI • MACD • EMA\n"

        "📈 BB • TDI • OBV • Supertrend\n"

        "🔥 Hacim + Momentum + R/R filtresi\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )


    if not tradable:

        message += (

            "🟡 ŞU ANDA TRADE EDİLEBİLİR "
            "GÜÇLÜ SİNYAL YOK.\n\n"

            "Bot listeyi doldurmak için "
            "zayıf coin önermiyor.\n\n"

            "⏳ Bir sonraki tarama bekleniyor."
        )


    else:

        for i, coin in enumerate(
            tradable,
            1
        ):

            message += (

                f"🏆 {i}. "
                f"{coin['symbol']}\n"

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
                f"{', '.join(coin['reasons'][:8])}\n"
            )


            if coin["warnings"]:

                message += (

                    "⚠️ "

                    + ", ".join(
                        coin["warnings"][:4]
                    )

                    + "\n"
                )


            message += (

                f"\n🛑 SL: "
                f"{price_format(coin['sl'])}\n"

                f"🎯 TP1: "
                f"{price_format(coin['tp1'])}\n"

                f"🎯 TP2: "
                f"{price_format(coin['tp2'])}\n"

                f"🎯 TP3: "
                f"{price_format(coin['tp3'])}\n"

                "📐 R/R: 1 : 2\n\n"
            )


    message += (

        "━━━━━━━━━━━━━━━━━━\n"

        "⚠️ Teknik sinyal sistemidir. "
        "Yatırım tavsiyesi değildir."
    )


    print("\n")
    print(message)

    send_telegram(
        message
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
