import os
import json
import math
import urllib.request
import urllib.parse
from datetime import datetime, timezone


# =========================================================
# AYARLAR
# =========================================================

BINANCE = "https://data-api.binance.vision"
TELEGRAM = "https://api.telegram.org"

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

SCAN_LIMIT = int(os.environ.get("SCAN_LIMIT", "80"))


STABLECOINS = {
    "USDT", "USDC", "FDUSD", "USDE",
    "TUSD", "DAI", "RLUSD", "USD1",
    "USDD", "EUR", "TRY"
}


# =========================================================
# SEKTÖRLER
# =========================================================

SECTORS = {

    "DEFI": {
        "UNI", "AAVE", "MKR", "CRV",
        "LDO", "COMP", "SNX", "DYDX",
        "1INCH", "SUSHI", "ENA",
        "PENDLE", "MORPHO", "JUP",
        "RAY", "CAKE"
    },

    "L1": {
        "ETH", "SOL", "AVAX", "ADA",
        "DOT", "ATOM", "NEAR", "APT",
        "SUI", "SEI", "ALGO",
        "TRX", "TON", "ICP"
    },

    "L2": {
        "ARB", "OP", "ZK",
        "STRK", "MANTA", "IMX",
        "MATIC", "POL", "ZRO"
    },

    "GAMING": {
        "IMX", "GALA", "SAND",
        "MANA", "AXS", "RON",
        "BEAM", "PIXEL",
        "ILV", "MAGIC", "SUPER"
    },

    "AI": {
        "FET", "TAO", "RENDER",
        "NEAR", "WLD", "ARKM",
        "AKT", "IO", "AIOZ",
        "VIRTUAL"
    },

    "MEME": {
        "DOGE", "SHIB", "PEPE",
        "FLOKI", "BONK", "WIF",
        "MEME", "BRETT", "MOG"
    }
}


# =========================================================
# HTTP
# =========================================================

def http_json(url, data=None, timeout=20):

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "BinanceEarlyScanner/3.0"
        }
    )

    with urllib.request.urlopen(
        req,
        timeout=timeout
    ) as response:

        return json.loads(
            response.read().decode()
        )


def get(url):

    return http_json(url)


# =========================================================
# TELEGRAM
# =========================================================

def telegram_updates():

    if not TOKEN:
        return []

    try:

        data = get(
            f"{TELEGRAM}/bot{TOKEN}/getUpdates"
            "?limit=20&timeout=1"
        )

        return data.get(
            "result",
            []
        )

    except Exception as e:

        print(
            "Telegram updates:",
            e
        )

        return []


def telegram_send(
    text,
    chat_id=None
):

    cid = chat_id or CHAT_ID

    if not TOKEN:

        print(
            "TELEGRAM_BOT_TOKEN bulunamadı."
        )

        return False

    if not cid:

        print(
            "Telegram CHAT_ID bulunamadı."
        )

        return False

    payload = urllib.parse.urlencode({
        "chat_id": cid,
        "text": text
    }).encode()

    try:

        http_json(
            f"{TELEGRAM}/bot{TOKEN}/sendMessage",
            payload
        )

        return True

    except Exception as e:

        print(
            "Telegram gönderim hatası:",
            e
        )

        return False


def handle_commands():

    updates = telegram_updates()

    for update in updates:

        message = update.get(
            "message"
        ) or {}

        text = (
            message.get("text")
            or ""
        ).strip().lower()

        chat = (
            message.get("chat")
            or {}
        )

        chat_id = str(
            chat.get("id", "")
        )

        if not chat_id:
            continue

        if text.startswith("/start"):

            telegram_send(
                "✅ BİNANCE TARAMA BOTU ÇALIŞIYOR.\n\n"
                "Her 15 dakikada piyasayı tarıyorum.\n\n"
                "Aradığım şeyler:\n"
                "• Erken momentum\n"
                "• Hacim artışı\n"
                "• Alıcı baskısı\n"
                "• Sektör rotasyonu\n"
                "• Yükselen sektörde geride kalan coinler\n"
                "• Breakout hazırlığı\n"
                "• Aşırı yükselmiş coinlerin elenmesi\n\n"
                "⚠️ GitHub Actions sürekli çalışan bir servis değildir. "
                "/start cevabı workflow'un bir sonraki çalışmasında gelir.",
                chat_id
            )


# =========================================================
# KLINE
# =========================================================

def get_klines(
    symbol,
    interval,
    limit=120
):

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

    # Açık mum kullanılmıyor.
    if len(data) > 2:
        data = data[:-1]

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

    taker_buy = [
        float(x[9])
        for x in data
    ]

    return (
        close,
        high,
        low,
        volume,
        taker_buy
    )


# =========================================================
# EMA
# =========================================================

def ema(values, period):

    if not values:
        return 0

    if len(values) < period:

        return sum(values) / len(values)

    multiplier = 2 / (
        period + 1
    )

    result = (
        sum(values[:period])
        / period
    )

    for value in values[period:]:

        result = (
            value * multiplier
            + result * (
                1 - multiplier
            )
        )

    return result


# =========================================================
# RSI
# =========================================================

def rsi(
    values,
    period=14
):

    if len(values) <= period:
        return 50

    gains = []
    losses = []

    for i in range(
        1,
        len(values)
    ):

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
            avg_gain * (
                period - 1
            )
            + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (
                period - 1
            )
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = (
        avg_gain
        / avg_loss
    )

    return (
        100
        - 100 / (
            1 + rs
        )
    )


# =========================================================
# MACD
# =========================================================

def macd(values):

    if len(values) < 35:

        return (
            0,
            0,
            0,
            0
        )

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

    previous = (
        macd_values[-2]
        if len(macd_values) > 1
        else line
    )

    acceleration = (
        line - previous
    )

    histogram = (
        line - signal
    )

    return (
        line,
        signal,
        histogram,
        acceleration
    )


# =========================================================
# BOLLINGER
# =========================================================

def bollinger(
    values,
    period=20
):

    recent = values[-period:]

    middle = (
        sum(recent)
        / len(recent)
    )

    variance = sum(
        (
            x - middle
        ) ** 2
        for x in recent
    ) / len(recent)

    std = math.sqrt(
        variance
    )

    upper = (
        middle
        + 2 * std
    )

    lower = (
        middle
        - 2 * std
    )

    width = (
        4 * std
        / middle
        * 100
        if middle
        else 0
    )

    return (
        upper,
        middle,
        lower,
        width
    )


# =========================================================
# OBV
# =========================================================

def obv(
    values,
    volumes
):

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

        output.append(
            result
        )

    return output


# =========================================================
# ATR
# =========================================================

def atr(
    high,
    low,
    close,
    period=14
):

    if len(close) < period + 1:

        return 0

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

    return (
        sum(trs[-period:])
        / period
    )


# =========================================================
# ADX / DI
# =========================================================

def adx_di(
    high,
    low,
    close,
    period=14
):

    if len(close) < (
        period * 2 + 5
    ):

        return (
            0,
            0,
            0
        )

    tr_list = []
    plus_dm = []
    minus_dm = []

    for i in range(
        1,
        len(close)
    ):

        up_move = (
            high[i]
            - high[i - 1]
        )

        down_move = (
            low[i - 1]
            - low[i]
        )

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

        tr_list.append(tr)

        plus_dm.append(
            up_move
            if (
                up_move > down_move
                and up_move > 0
            )
            else 0
        )

        minus_dm.append(
            down_move
            if (
                down_move > up_move
                and down_move > 0
            )
            else 0
        )

    def di_at(index):

        start = max(
            0,
            index - period + 1
        )

        tr_sum = sum(
            tr_list[start:index + 1]
        )

        if tr_sum == 0:

            return (
                0,
                0
            )

        plus = (
            sum(
                plus_dm[start:index + 1]
            )
            / tr_sum
            * 100
        )

        minus = (
            sum(
                minus_dm[start:index + 1]
            )
            / tr_sum
            * 100
        )

        return (
            plus,
            minus
        )

    plus_di, minus_di = di_at(
        len(tr_list) - 1
    )

    dx_values = []

    start = max(
        0,
        len(tr_list)
        - period * 2
    )

    for i in range(
        start,
        len(tr_list)
    ):

        plus, minus = di_at(i)

        denominator = (
            plus + minus
        )

        if denominator == 0:
            continue

        dx = (
            abs(
                plus - minus
            )
            / denominator
            * 100
        )

        dx_values.append(dx)

    if not dx_values:

        return (
            0,
            plus_di,
            minus_di
        )

    recent_dx = dx_values[-period:]

    adx_value = (
        sum(recent_dx)
        / len(recent_dx)
    )

    return (
        adx_value,
        plus_di,
        minus_di
    )


# =========================================================
# VWAP
# =========================================================

def vwap(
    high,
    low,
    close,
    volume,
    period=50
):

    start = max(
        0,
        len(close) - period
    )

    cumulative_pv = 0
    cumulative_volume = 0

    for i in range(
        start,
        len(close)
    ):

        typical_price = (
            high[i]
            + low[i]
            + close[i]
        ) / 3

        cumulative_pv += (
            typical_price
            * volume[i]
        )

        cumulative_volume += (
            volume[i]
        )

    if cumulative_volume == 0:

        return close[-1]

    return (
        cumulative_pv
        / cumulative_volume
    )


# =========================================================
# YARDIMCI
# =========================================================

def percent_change(
    current,
    previous
):

    if previous == 0:
        return 0

    return (
        current / previous
        - 1
    ) * 100


def price_format(value):

    if value >= 100:
        return f"{value:.2f}"

    if value >= 1:
        return f"{value:.4f}"

    if value >= 0.01:
        return f"{value:.6f}"

    return f"{value:.10f}"


def get_sector(symbol):

    if symbol.endswith("USDT"):

        base = symbol[:-4]

    else:

        base = symbol

    for name, coins in SECTORS.items():

        if base in coins:

            return name

    return "OTHER"


# =========================================================
# BTC / ETH MARKET
# =========================================================

def market_snapshot():

    market = {}

    for symbol in (
        "BTCUSDT",
        "ETHUSDT"
    ):

        close, _, _, _, _ = (
            get_klines(
                symbol,
                "15m",
                80
            )
        )

        market[symbol] = {

            "price": close[-1],

            "momentum":
                percent_change(
                    close[-1],
                    close[-5]
                ),

            "rsi":
                rsi(close)
        }

    return market


# =========================================================
# COIN ANALİZİ
# =========================================================

def analyze(
    symbol,
    market
):

    try:

        close, high, low, volume, taker = (
            get_klines(
                symbol,
                "15m",
                120
            )
        )

        close1h, _, _, _, _ = (
            get_klines(
                symbol,
                "1h",
                80
            )
        )

        close4h, _, _, _, _ = (
            get_klines(
                symbol,
                "4h",
                80
            )
        )

        if len(close) < 60:

            return None

        price = close[-1]

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        rsi15 = rsi(close)

        rsi_previous = rsi(
            close[:-5]
        )

        rsi_delta = (
            rsi15
            - rsi_previous
        )

        rsi1h = rsi(
            close1h
        )

        rsi4h = rsi(
            close4h
        )

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        ema9 = ema(
            close,
            9
        )

        ema21 = ema(
            close,
            21
        )

        ema50 = ema(
            close,
            50
        )

        ema21_1h = ema(
            close1h,
            21
        )

        ema50_1h = ema(
            close1h,
            50
        )

        # -------------------------------------------------
        # MACD
        # -------------------------------------------------

        (
            macd_line,
            macd_signal,
            macd_hist,
            macd_acceleration
        ) = macd(close)

        (
            _,
            _,
            _,
            macd_acceleration_1h
        ) = macd(close1h)

        # -------------------------------------------------
        # BOLLINGER
        # -------------------------------------------------

        (
            upper,
            middle,
            lower,
            bb_width
        ) = bollinger(
            close
        )

        # -------------------------------------------------
        # OBV
        # -------------------------------------------------

        obv_values = obv(
            close,
            volume
        )

        obv_slope = (
            percent_change(
                obv_values[-1],
                obv_values[-6]
            )
            if obv_values[-6] != 0
            else 0
        )

        # -------------------------------------------------
        # ADX
        # -------------------------------------------------

        (
            adx_value,
            plus_di,
            minus_di
        ) = adx_di(
            high,
            low,
            close
        )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        current_vwap = vwap(
            high,
            low,
            close,
            volume
        )

        # -------------------------------------------------
        # HACİM
        # -------------------------------------------------

        average_volume = (
            sum(
                volume[-21:-1]
            )
            / 20
        )

        if average_volume <= 0:

            return None

        volume_ratio = (
            volume[-1]
            / average_volume
        )

        previous_volume = (
            sum(
                volume[-11:-1]
            )
            / 10
        )

        volume_acceleration = (
            volume[-1]
            / previous_volume
            if previous_volume > 0
            else 1
        )

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        momentum = percent_change(
            price,
            close[-5]
        )

        previous_momentum = percent_change(
            close[-5],
            close[-9]
        )

        momentum_acceleration = (
            momentum
            - previous_momentum
        )

        # -------------------------------------------------
        # TAKER BUY
        # -------------------------------------------------

        if volume[-1] > 0:

            taker_buy_percent = (
                taker[-1]
                / volume[-1]
                * 100
            )

        else:

            taker_buy_percent = 50

        total_taker_volume = sum(
            taker[-6:]
        )

        total_volume = sum(
            volume[-6:]
        )

        if total_volume > 0:

            recent_taker_percent = (
                total_taker_volume
                / total_volume
                * 100
            )

        else:

            recent_taker_percent = 50

        taker_delta = (
            taker_buy_percent
            - recent_taker_percent
        )

        # -------------------------------------------------
        # TREND
        # -------------------------------------------------

        trend15 = (
            price > ema9
            and ema9 > ema21
        )

        trend1h = (
            close1h[-1]
            > ema21_1h
            > ema50_1h
        )

        # -------------------------------------------------
        # SCORE
        # -------------------------------------------------

        score = 0

        reasons = []

        # RSI yükseliyor
        if rsi_delta >= 5:

            score += 14

            reasons.append(
                "RSI güçlü yükseliyor"
            )

        elif rsi_delta >= 3:

            score += 9

            reasons.append(
                "RSI yükseliyor"
            )

        # 15 dk trend
        if trend15:

            score += 10

            reasons.append(
                "15dk trend yukarı"
            )

        # 1 saat trend
        if trend1h:

            score += 10

            reasons.append(
                "1s trend yukarı"
            )

        # MACD
        if (
            macd_hist > 0
            and macd_acceleration > 0
        ):

            score += 9

            reasons.append(
                "MACD hızlanıyor"
            )

        # OBV
        if obv_slope > 0:

            score += 9

            reasons.append(
                "OBV yükseliyor"
            )

        # Hacim
        if volume_ratio >= 2:

            score += 10

            reasons.append(
                "Hacim güçlü"
            )

        elif volume_ratio >= 1.5:

            score += 7

            reasons.append(
                "Hacim uyanıyor"
            )

        elif volume_ratio >= 1.2:

            score += 4

            reasons.append(
                "Hacim artıyor"
            )

        # Hacim ivmesi
        if volume_acceleration >= 2:

            score += 8

            reasons.append(
                "Hacim ivmesi güçlü"
            )

        elif volume_acceleration >= 1.5:

            score += 5

            reasons.append(
                "Hacim ivmesi"
            )

        # Taker buy
        if taker_buy_percent >= 56:

            score += 9

            reasons.append(
                "Güçlü alıcı baskısı"
            )

        elif taker_buy_percent >= 53:

            score += 6

            reasons.append(
                "Alıcı baskısı"
            )

        # Sağlıklı momentum
        if (
            momentum >= 0.4
            and momentum <= 4
        ):

            score += 8

            reasons.append(
                "Sağlıklı momentum"
            )

        # Momentum hızlanması
        if momentum_acceleration >= 0.2:

            score += 7

            reasons.append(
                "Momentum hızlanıyor"
            )

        # VWAP
        if price > current_vwap:

            score += 5

            reasons.append(
                "VWAP üstü"
            )

        # ADX / DI
        if (
            adx_value >= 25
            and plus_di > minus_di
        ):

            score += 7

            reasons.append(
                "ADX/DI pozitif"
            )

        elif (
            adx_value >= 20
            and plus_di > minus_di
        ):

            score += 4

            reasons.append(
                "Trend güçleniyor"
            )

        # BB sıkışması
        if bb_width < 4:

            score += 5

            reasons.append(
                "Bollinger sıkışması"
            )

        # =================================================
        # AŞIRI UZAMA CEZALARI
        # =================================================

        extension = (
            (
                price
                / ema21
            ) - 1
        ) * 100

        if extension > 5:

            score -= 15

            reasons.append(
                "Aşırı yükselme cezası"
            )

        elif extension > 3:

            score -= 7

            reasons.append(
                "Uzatma riski"
            )

        if rsi15 > 72:

            score -= 12

            reasons.append(
                "RSI aşırı yüksek"
            )

        elif rsi15 > 68:

            score -= 5

            reasons.append(
                "RSI yükseldi"
            )

        if momentum > 5:

            score -= 15

            reasons.append(
                "Momentum fazla hızlı"
            )

        # =================================================
        # ALT SINIR
        # =================================================

        score = max(
            0,
            min(
                100,
                score
            )
        )

        return {

            "symbol":
                symbol,

            "price":
                price,

            "sector":
                get_sector(symbol),

            "score":
                score,

            "momentum":
                momentum,

            "momentum_acc":
                momentum_acceleration,

            "rsi":
                rsi15,

            "rsi_delta":
                rsi_delta,

            "adx":
                adx_value,

            "volume":
                volume_ratio,

            "volume_acc":
                volume_acceleration,

            "taker":
                taker_buy_percent,

            "taker_delta":
                taker_delta,

            "bb_width":
                bb_width,

            "vwap":
                current_vwap,

            "reasons":
                reasons,

            "trend":
                (
                    trend15
                    and trend1h
                )
        }

    except Exception as e:

        print(
            f"{symbol} analiz hatası:",
            e
        )

        return None


# =========================================================
# SEKTÖR İSTATİSTİKLERİ
# =========================================================

def sector_statistics(
    results
):

    groups = {}

    for coin in results:

        groups.setdefault(
            coin["sector"],
            []
        ).append(coin)

    statistics = {}

    for sector_name, coins in groups.items():

        if len(coins) < 2:

            continue

        statistics[
            sector_name
        ] = {

            "momentum":
                sum(
                    x["momentum"]
                    for x in coins
                )
                / len(coins),

            "volume":
                sum(
                    x["volume"]
                    for x in coins
                )
                / len(coins),

            "count":
                len(coins)
        }

    return statistics


# =========================================================
# GÖRECELİ GÜÇ / GERİDE KALAN
# =========================================================

def relative_strength(
    results,
    statistics
):

    for coin in results:

        sector_data = statistics.get(
            coin["sector"]
        )

        coin["relative"] = 0

        if not sector_data:

            coin["laggard"] = False

            continue

        sector_momentum = (
            sector_data["momentum"]
        )

        coin["relative"] = (
            coin["momentum"]
            - sector_momentum
        )

        # Sektör yükseliyor.
        # Coin geride.
        # Ama coin içinde toparlanma belirtileri var.
        if (
            sector_momentum > 0.8
            and coin["momentum"]
            < sector_momentum - 0.5
            and coin["volume"] >= 1.2
            and coin["rsi_delta"] >= 2
        ):

            coin["laggard"] = True

            coin["score"] = min(
                100,
                coin["score"] + 10
            )

            coin["reasons"].append(
                "Yükselen sektörde geride"
            )

        else:

            coin["laggard"] = False

    return results


# =========================================================
# MARKET SCORE
# =========================================================

def market_score(
    market
):

    score = 0

    if (
        market["BTCUSDT"]["momentum"]
        > 0
    ):

        score += 1

    if (
        market["BTCUSDT"]["rsi"]
        > 50
    ):

        score += 1

    if (
        market["ETHUSDT"]["momentum"]
        > 0
    ):

        score += 1

    if (
        market["ETHUSDT"]["rsi"]
        > 50
    ):

        score += 1

    if (
        market["BTCUSDT"]["momentum"]
        > -1
    ):

        score += 1

    return score


# =========================================================
# TARAMA
# =========================================================

def scan():

    # Telegram komutlarını kontrol et
    handle_commands()

    tickers = get(
        BINANCE
        + "/api/v3/ticker/24hr"
    )

    candidates = []

    for ticker in tickers:

        symbol = ticker.get(
            "symbol",
            ""
        )

        if not symbol.endswith(
            "USDT"
        ):

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

        base = symbol[:-4]

        if base in STABLECOINS:

            continue

        try:

            quote_volume = float(
                ticker[
                    "quoteVolume"
                ]
            )

            if quote_volume < 3_000_000:

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

    candidates = candidates[
        :SCAN_LIMIT
    ]

    print(
        f"{len(candidates)} coin analiz edilecek."
    )

    market = market_snapshot()

    results = []

    for symbol, _ in candidates:

        print(
            "Analiz:",
            symbol
        )

        result = analyze(
            symbol,
            market
        )

        if result:

            results.append(
                result
            )

    statistics = (
        sector_statistics(
            results
        )
    )

    results = relative_strength(
        results,
        statistics
    )

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return (
        market,
        results,
        statistics
    )


# =========================================================
# MESAJ
# =========================================================

def build_message(
    market,
    results,
    statistics
):

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )

    mscore = market_score(
        market
    )

    message = (

        "🧠 BİNANCE ERKEN HAREKET TARAMASI\n\n"

        f"🕐 {now}\n"

        "📊 15dk + 1s + 4s\n"

        "🧠 RSI • EMA • MACD • BB\n"

        "📈 OBV • ADX/DI • VWAP\n"

        "🔥 Hacim • Alıcı Baskısı\n"

        "⚡ Momentum İvmesi\n"

        "🟣 Sektör Rotasyonu\n"

        "🎯 Göreceli Güç\n"

        "🚀 Erken Hareket Motoru\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        "🌍 PİYASA DURUMU\n\n"

        f"₿ BTC momentum: "
        f"{market['BTCUSDT']['momentum']:+.2f}%\n"

        f"₿ BTC RSI: "
        f"{market['BTCUSDT']['rsi']:.1f}\n"

        f"Ξ ETH momentum: "
        f"{market['ETHUSDT']['momentum']:+.2f}%\n"

        f"Ξ ETH RSI: "
        f"{market['ETHUSDT']['rsi']:.1f}\n\n"

        f"📊 Piyasa skoru: "
        f"{mscore}/5\n\n"
    )

    # =====================================================
    # ERKEN HAREKET
    # =====================================================

    candidates = [
        x
        for x in results
        if x["score"] >= 65
    ]

    candidates = candidates[:5]

    message += (
        "🟣 ERKEN HAREKET / İZLE\n\n"
    )

    if not candidates:

        message += (
            "🟡 Şu anda yeterince güçlü "
            "erken hareket adayı yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            candidates,
            1
        ):

            if coin.get(
                "laggard"
            ):

                status = (
                    "🔵 GERİDE KALAN ADAY"
                )

            elif coin["score"] >= 80:

                status = (
                    "🟢 GÜÇLÜ ERKEN SİNYAL"
                )

            else:

                status = (
                    "🟡 İZLE"
                )

            message += (

                f"🏆 {i}. "
                f"{coin['symbol']}\n"

                f"{status}\n"

                f"⭐ Skor: "
                f"{coin['score']}/100\n"

                f"🏷️ Sektör: "
                f"{coin['sector']}\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"📈 Momentum: "
                f"{coin['momentum']:+.2f}%\n"

                f"⚡ Momentum ivmesi: "
                f"{coin['momentum_acc']:+.2f}%\n"

                f"🔥 Hacim: "
                f"x{coin['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{coin['volume_acc']:.1f}\n"

                f"📊 RSI: "
                f"{coin['rsi']:.1f} "
                f"(Δ {coin['rsi_delta']:+.1f})\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"🛒 Alıcı baskısı: "
                f"%{coin['taker']:.1f}\n"

                f"📏 BB genişliği: "
                f"%{coin['bb_width']:.2f}\n"
            )

            if coin.get(
                "laggard"
            ):

                message += (
                    "🔵 SEKTÖR YÜKSELİYOR, "
                    "BU COIN GERİDE\n"
                )

            if coin["reasons"]:

                message += (
                    "🧠 "
                    + ", ".join(
                        coin["reasons"][:8]
                    )
                    + "\n"
                )

            message += (
                "\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # =====================================================
    # SEKTÖR ROTASYONU
    # =====================================================

    message += (
        "🔄 SEKTÖR ROTASYONU\n\n"
    )

    active_sectors = sorted(
        statistics.items(),
        key=lambda x:
        x[1]["momentum"],
        reverse=True
    )[:5]

    if not active_sectors:

        message += (
            "🟡 Yeterli sektör verisi yok.\n"
        )

    else:

        for (
            sector_name,
            data
        ) in active_sectors:

            if data[
                "momentum"
            ] > 0.5:

                icon = "🔥"

            elif data[
                "momentum"
            ] > 0:

                icon = "🟢"

            else:

                icon = "🔴"

            message += (
                f"{icon} "
                f"{sector_name}: "
                f"{data['momentum']:+.2f}% "
                f"| Hacim x"
                f"{data['volume']:.1f}\n"
            )

    # =====================================================
    # SOSYAL
    # =====================================================

    message += (
        "\n"
        "📱 SOSYAL RADAR\n\n"

        "⚪ Pasif.\n"

        "X/Twitter verisi için "
        "ayrı API erişimi gerekir. "
        "Anahtar olmadan sosyal sinyal "
        "uydurmuyorum.\n\n"
    )

    # =====================================================
    # FİLTRELER
    # =====================================================

    message += (

        "🛡️ KULLANILAN FİLTRELER\n\n"

        "• Aşırı yükselmiş coin ceza alır\n"

        "• RSI aşırı yüksekse ceza alır\n"

        "• Zayıf ADX güçlü trend sayılmaz\n"

        "• Hacim artışı aranır\n"

        "• Alıcı baskısı aranır\n"

        "• Momentumun hızlanması aranır\n"

        "• OBV teyidi aranır\n"

        "• Yükselen sektörde geride kalanlar ayrıca aranır\n"

        "• Henüz kırılmamış hareketler önceliklendirilir\n\n"

        "⚠️ Teknik tarama sistemidir. "
        "Yatırım tavsiyesi değildir."
    )

    return message


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "🚀 BİNANCE ERKEN HAREKET BOTU BAŞLADI"
    )

    try:

        (
            market,
            results,
            statistics
        ) = scan()

        message = build_message(
            market,
            results,
            statistics
        )

        print(
            message
        )

        sent = telegram_send(
            message
        )

        if not sent:

            print(
                "Telegram mesajı gönderilemedi."
            )

    except Exception as e:

        print(
            "ANA HATA:",
            repr(e)
        )

        telegram_send(
            "🚨 BOT HATASI\n\n"
            + str(e)
        )


if __name__ == "__main__":

    main()
