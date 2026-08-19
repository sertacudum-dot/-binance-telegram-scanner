import os
import json
import urllib.request
import urllib.parse
import statistics
from datetime import datetime, timezone

BINANCE = "https://api.binance.com"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def ema(values, period):
    k = 2 / (period + 1)
    result = [values[0]]
    for x in values[1:]:
        result.append(x * k + result[-1] * (1-k))
    return result

def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))

    if len(gains) < period:
        return 50

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain*(period-1) + gains[i]) / period
        avg_loss = (avg_loss*(period-1) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(values):
    e12 = ema(values, 12)
    e26 = ema(values, 26)
    line = [a-b for a,b in zip(e12, e26)]
    signal = ema(line, 9)
    return line[-1], signal[-1], line[-1]-signal[-1]

def get_klines(symbol, interval, limit=100):
    url = BINANCE + "/api/v3/klines?" + urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    })
    data = get(url)

    close = [float(x[4]) for x in data]
    volume = [float(x[5]) for x in data]

    return close, volume

def analyze(symbol):
    try:
        c15, v15 = get_klines(symbol, "15m")
        c1h, v1h = get_klines(symbol, "1h")

        price = c15[-1]

        r15 = rsi(c15)
        r1h = rsi(c1h)

        m15, s15, h15 = macd(c15)
        m1h, s1h, h1h = macd(c1h)

        e9 = ema(c15, 9)[-1]
        e21 = ema(c15, 21)[-1]
        e50 = ema(c15, 50)[-1]

        score = 0
        reasons = []

        # RSI
        if 50 <= r15 <= 68:
            score += 10
            reasons.append("RSI")
        elif r15 > 68:
            score += 3

        if r1h > 50:
            score += 7
            reasons.append("1h RSI")

        # MACD
        if m15 > s15:
            score += 8
            reasons.append("MACD")
        if h15 > 0 and h15 > h1h:
            score += 5

        if m1h > s1h:
            score += 8
            reasons.append("1h MACD")

        # EMA
        if price > e9 > e21:
            score += 8
            reasons.append("EMA9/21")

        if price > e50:
            score += 7
            reasons.append("EMA50")

        # Volume
        avg_vol = sum(v15[-20:]) / 20
        vol_ratio = v15[-1] / avg_vol if avg_vol else 1

        if vol_ratio >= 1.5:
            score += 10
            reasons.append(f"Hacim x{vol_ratio:.1f}")
        elif vol_ratio >= 1.2:
            score += 5

        # Momentum
        momentum = ((price / c15[-5]) - 1) * 100

        if 0 < momentum < 7:
            score += 7
            reasons.append("Momentum")

        # Son mumların yönü
        if c15[-1] > c15[-2] > c15[-3]:
            score += 5
            reasons.append("Kısa trend")

        # Aşırı yükselmiş coinleri cezalandır
        if momentum > 12:
            score -= 10

        score = max(0, min(100, score))

        # Basit ATR benzeri volatilite
        ranges = [
            abs(c15[i] - c15[i-1])
            for i in range(max(1, len(c15)-14), len(c15))
        ]

        atr = statistics.mean(ranges)

        sl = price - atr * 1.5
        tp1 = price + atr * 1.2
        tp2 = price + atr * 2.2

        return {
            "symbol": symbol,
            "price": price,
            "score": score,
            "r15": r15,
            "r1h": r1h,
            "vol": vol_ratio,
            "momentum": momentum,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "reasons": reasons
        }

    except Exception:
        return None

def price_format(x):
    if x >= 100:
        return f"{x:.2f}"
    if x >= 1:
        return f"{x:.4f}"
    if x >= 0.01:
        return f"{x:.6f}"
    return f"{x:.10f}"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")

    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def main():

    print("Binance taraması başladı...")

    tickers = get(BINANCE + "/api/v3/ticker/24hr")

    coins = []

    for t in tickers:

        symbol = t["symbol"]

        if not symbol.endswith("USDT"):
            continue

        if any(x in symbol for x in [
            "UPUSDT", "DOWNUSDT", "BULLUSDT",
            "BEARUSDT"
        ]):
            continue

        try:
            volume = float(t["quoteVolume"])

            if volume < 3000000:
                continue

            coins.append((symbol, volume))

        except:
            pass

    # En likit 100 coin
    coins.sort(key=lambda x: x[1], reverse=True)
    coins = coins[:100]

    results = []

    for symbol, volume in coins:

        result = analyze(symbol)

        if result:
            results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)

    top = results[:10]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    message = f"🚨 BINANCE AL TARAMASI\n"
    message += f"{now}\n"
    message += "15m + 1h analiz\n\n"

    for i, x in enumerate(top, 1):

        message += (
            f"{i}. {x['symbol']} 🟢 {x['score']}/100\n"
            f"Fiyat: {price_format(x['price'])}\n"
            f"RSI: {x['r15']:.1f} | 1h: {x['r1h']:.1f}\n"
            f"Hacim: x{x['vol']:.1f}\n"
            f"Momentum: {x['momentum']:+.1f}%\n"
            f"SL: {price_format(x['sl'])}\n"
            f"TP1: {price_format(x['tp1'])}\n"
            f"TP2: {price_format(x['tp2'])}\n"
            f"↳ {', '.join(x['reasons'][:5])}\n\n"
        )

    message += "⚠️ Teknik taramadır, yatırım tavsiyesi değildir."

    send_telegram(message)

    print(message)

if __name__ == "__main__":
    main()
