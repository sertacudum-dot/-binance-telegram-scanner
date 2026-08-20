import os
import json
import urllib.request
import urllib.parse
import statistics
from datetime import datetime, timezone

BINANCE = "https://data-api.binance.vision"

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


def get(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def get_chat_id():
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

    try:
        data = get(url)

        for update in reversed(data.get("result", [])):
            message = update.get("message")

            if message and message.get("chat"):
                return str(message["chat"]["id"])

    except Exception as e:
        print("Chat ID alınamadı:", e)

    return None


def ema(values, period):
    k = 2 / (period + 1)

    result = [values[0]]

    for value in values[1:]:
        result.append(
            value * k + result[-1] * (1 - k)
        )

    return result


def rsi(values, period=14):

    gains = []
    losses = []

    for i in range(1, len(values)):

        change = values[i] - values[i - 1]

        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    if len(gains) < period:
        return 50

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):

        avg_gain = (
            avg_gain * (period - 1) + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def macd(values):

    ema12 = ema(values, 12)
    ema26 = ema(values, 26)

    macd_line = [
        a - b
        for a, b in zip(ema12, ema26)
    ]

    signal = ema(macd_line, 9)

    histogram = (
        macd_line[-1] - signal[-1]
    )

    return (
        macd_line[-1],
        signal[-1],
        histogram
    )


def get_klines(symbol, interval, limit=100):

    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    })

    url = (
        BINANCE +
        "/api/v3/klines?" +
        params
    )

    data = get(url)

    close = [
        float(x[4])
        for x in data
    ]

    volume = [
        float(x[5])
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

    return close, volume, high, low


def analyze(symbol):

    try:

        close15, volume15, high15, low15 = get_klines(
            symbol,
            "15m"
        )

        close1h, volume1h, high1h, low1h = get_klines(
            symbol,
            "1h"
        )

        price = close15[-1]

        rsi15 = rsi(close15)
        rsi1h = rsi(close1h)

        macd15, signal15, hist15 = macd(close15)
        macd1h, signal1h, hist1h = macd(close1h)

        ema9 = ema(close15, 9)[-1]
        ema21 = ema(close15, 21)[-1]
        ema50 = ema(close15, 50)[-1]

        score = 0

        reasons = []

        # RSI

        if 50 <= rsi15 <= 68:

            score += 10

            reasons.append("RSI")

        elif rsi15 > 68:

            score += 3

        if rsi1h > 50:

            score += 7

            reasons.append("1h RSI")


        # MACD

        if macd15 > signal15:

            score += 8

            reasons.append("MACD")

        if hist15 > 0:

            score += 5

        if macd1h > signal1h:

            score += 8

            reasons.append("1h MACD")


        # EMA

        if price > ema9 > ema21:

            score += 8

            reasons.append("EMA9/21")

        if price > ema50:

            score += 7

            reasons.append("EMA50")


        # Volume

        average_volume = (
            sum(volume15[-20:]) / 20
        )

        volume_ratio = (
            volume15[-1] /
            average_volume
            if average_volume
            else 1
        )

        if volume_ratio >= 1.5:

            score += 10

            reasons.append(
                f"Hacim x{volume_ratio:.1f}"
            )

        elif volume_ratio >= 1.2:

            score += 5


        # Momentum

        momentum = (
            (price / close15[-5]) - 1
        ) * 100

        if 0 < momentum < 7:

            score += 7

            reasons.append("Momentum")

        elif momentum >= 7:

            score += 2


        # Son mumlar

        if (
            close15[-1] >
            close15[-2] >
            close15[-3]
        ):

            score += 5

            reasons.append("Kısa trend")


        # Aşırı yükselişi cezalandır

        if momentum > 12:

            score -= 10


        score = max(
            0,
            min(100, score)
        )


        # ATR benzeri volatilite

        ranges = []

        for i in range(
            max(1, len(close15) - 14),
            len(close15)
        ):

            ranges.append(
                abs(
                    close15[i] -
                    close15[i - 1]
                )
            )

        atr = (
            statistics.mean(ranges)
            if ranges
            else price * 0.01
        )


        sl = price - atr * 1.5

        tp1 = price + atr * 1.2

        tp2 = price + atr * 2.2


        return {

            "symbol": symbol,

            "price": price,

            "score": score,

            "rsi15": rsi15,

            "rsi1h": rsi1h,

            "volume_ratio": volume_ratio,

            "momentum": momentum,

            "sl": sl,

            "tp1": tp1,

            "tp2": tp2,

            "reasons": reasons

        }


    except Exception as e:

        print(
            f"{symbol} analiz hatası:",
            e
        )

        return None


def price_format(value):

    if value >= 100:

        return f"{value:.2f}"

    if value >= 1:

        return f"{value:.4f}"

    if value >= 0.01:

        return f"{value:.6f}"

    return f"{value:.10f}"


def send_telegram(message):

    chat_id = get_chat_id()

    if not chat_id:

        print(
            "Chat ID bulunamadı."
        )

        return


    url = (
        f"https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )


    data = urllib.parse.urlencode({

        "chat_id": chat_id,

        "text": message

    }).encode()


    request = urllib.request.Request(

        url,

        data=data,

        method="POST"

    )


    with urllib.request.urlopen(
        request,
        timeout=20
    ) as response:

        return response.read()


def main():

    print(
        "🚀 Binance taraması başladı..."
    )


    tickers = get(
        BINANCE +
        "/api/v3/ticker/24hr"
    )


    coins = []


    for ticker in tickers:

        symbol = ticker["symbol"]


        if not symbol.endswith("USDT"):

            continue


        # Kaldıraç tokenlerini çıkar

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


            # Çok düşük hacimli coinleri çıkar

            if volume < 3000000:

                continue


            coins.append(
                (symbol, volume)
            )


        except:

            continue


    # En likit 100 coin

    coins.sort(
        key=lambda x: x[1],
        reverse=True
    )


    coins = coins[:100]


    print(
        f"{len(coins)} coin taranacak."
    )


    results = []


    for symbol, volume in coins:

        result = analyze(symbol)

        if result:

            results.append(result)


    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    top10 = results[:10]


    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )


    message = (
        "🚨 BINANCE AL TARAMASI\n\n"
        f"🕐 {now}\n"
        "📊 15m + 1h analiz\n"
        "━━━━━━━━━━━━━━\n\n"
    )


    for i, coin in enumerate(
        top10,
        1
    ):

        message += (

            f"🏆 {i}. "
            f"{coin['symbol']}\n"

            f"⭐ Skor: "
            f"{coin['score']}/100\n"

            f"💰 Fiyat: "
            f"{price_format(coin['price'])}\n"

            f"RSI: "
            f"{coin['rsi15']:.1f} "
            f"| 1h: "
            f"{coin['rsi1h']:.1f}\n"

            f"📈 Hacim: "
            f"x{coin['volume_ratio']:.1f}\n"

            f"🚀 Momentum: "
            f"{coin['momentum']:+.1f}%\n"

            f"🛑 SL: "
            f"{price_format(coin['sl'])}\n"

            f"🎯 TP1: "
            f"{price_format(coin['tp1'])}\n"

            f"🎯 TP2: "
            f"{price_format(coin['tp2'])}\n"

            f"🔎 "
            f"{', '.join(coin['reasons'][:5])}\n\n"
        )


    message += (
        "⚠️ Teknik taramadır. "
        "Yatırım tavsiyesi değildir."
    )


    print(message)


    send_telegram(message)


if __name__ == "__main__":

    main()
