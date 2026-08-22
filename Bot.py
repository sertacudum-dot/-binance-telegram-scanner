import os
import json
import urllib.request
import urllib.parse
import math
import statistics
from datetime import datetime, timezone

# =========================================================
# CONFIG
# =========================================================

BINANCE = "https://data-api.binance.vision"

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

LUNAR_KEY = os.environ.get("LUNARCRUSH_API_KEY", "").strip()
LUNAR_BASE = "https://lunarcrush.com/api4"

STABLECOINS = {
    "USDT", "USDC", "FDUSD", "USDE",
    "TUSD", "DAI", "RLUSD", "USD1", "USDD"
}

MIN_24H_QUOTE_VOLUME = 5_000_000

MAX_TECH_COINS = 120
MAX_FOLLOWER_COINS = 35

# =========================================================
# SECTOR KEYWORDS
# =========================================================

SECTOR_KEYWORDS = {
    "DEFI": [
        "defi", "aave", "uniswap", "chainlink", "maker",
        "lido", "curve", "compound", "jupiter", "raydium",
        "pancakeswap", "sushiswap", "morpho"
    ],

    "GAMING": [
        "gaming", "game", "immutable", "gala", "beam",
        "ronin", "axie", "sandbox", "decentraland",
        "illuvium", "pixels"
    ],

    "AI": [
        "ai", "artificial intelligence", "render",
        "fetch", "bittensor", "near", "akash",
        "virtual", "grass", "io.net"
    ],

    "MEME": [
        "meme", "doge", "shib", "pepe", "bonk",
        "floki", "wif", "mew", "brett"
    ],

    "L1": [
        "layer 1", "layer1", "ethereum", "solana",
        "avalanche", "sui", "aptos", "sei", "injective",
        "cosmos", "cardano", "near", "ton"
    ],

    "L2": [
        "layer 2", "layer2", "arbitrum", "optimism",
        "base", "zksync", "starknet", "scroll",
        "mantle", "blast"
    ],

    "RWA": [
        "rwa", "real world asset", "ondo", "tokenized",
        "centrifuge", "mantra"
    ],

    "DEPIN": [
        "depin", "decentralized physical",
        "helium", "filecoin", "arweave",
        "akash", "render"
    ]
}


# =========================================================
# HTTP
# =========================================================

def get(url, headers=None, timeout=20):

    req_headers = {
        "User-Agent": "Mozilla/5.0"
    }

    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(
        url,
        headers=req_headers
    )

    with urllib.request.urlopen(
        req,
        timeout=timeout
    ) as r:

        return json.loads(
            r.read().decode()
        )


# =========================================================
# TELEGRAM
# =========================================================

def get_chat_id():

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{TOKEN}/getUpdates"
        )

        data = get(url)

        for update in reversed(
            data.get("result", [])
        ):

            message = update.get("message")

            if message and message.get("chat"):
                return str(
                    message["chat"]["id"]
                )

    except Exception as e:

        print(
            "Chat ID error:",
            e
        )

    return None


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

    req = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )

    with urllib.request.urlopen(
        req,
        timeout=20
    ):

        print(
            "Telegram mesajı gönderildi."
        )


# =========================================================
# BINANCE KLINES
# =========================================================

def get_klines(
    symbol,
    interval,
    limit=200
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

    taker_buy_volume = [
        float(x[9])
        for x in data
    ]

    return (
        close,
        high,
        low,
        volume,
        taker_buy_volume
    )


# =========================================================
# INDICATORS
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

    rs = (
        avg_gain
        / avg_loss
    )

    return (
        100
        - 100 / (1 + rs)
    )


def rsi_series(values, period=14):

    result = []

    for i in range(
        period,
        len(values)
    ):

        result.append(
            rsi(
                values[:i + 1],
                period
            )
        )

    return result


def rsi_slope(values):

    rs = rsi_series(values)

    if len(rs) < 5:
        return 0

    return (
        rs[-1]
        - rs[-5]
    )


def stoch_rsi(
    values,
    period=14
):

    rs = rsi_series(
        values,
        period
    )

    if len(rs) < period:
        return 50

    recent = rs[-period:]

    low = min(recent)
    high = max(recent)

    if high == low:
        return 50

    return (
        (rs[-1] - low)
        /
        (high - low)
    ) * 100


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


def macd_hist_acceleration(values):

    if len(values) < 60:
        return 0

    histograms = []

    for i in range(
        35,
        len(values)
    ):

        _, _, hist = macd(
            values[:i]
        )

        histograms.append(
            hist
        )

    if len(histograms) < 5:
        return 0

    return (
        histograms[-1]
        - histograms[-5]
    )


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
        (x - middle) ** 2
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

    return (
        upper,
        middle,
        lower
    )


def bb_width(values):

    upper, middle, lower = bollinger(
        values
    )

    if middle == 0:
        return 0

    return (
        (upper - lower)
        / middle
    ) * 100


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

    if len(close) < 40:
        return 0, 0, 0

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

    atr_value = (
        sum(tr_list[-period:])
        / period
    )

    if atr_value == 0:
        return 0, 0, 0

    plus_di = (
        sum(plus_dm[-period:])
        / period
    ) / atr_value * 100

    minus_di = (
        sum(minus_dm[-period:])
        / period
    ) / atr_value * 100

    dx_values = []

    start = max(
        0,
        len(tr_list)
        - period * 3
    )

    for i in range(
        start,
        len(tr_list)
    ):

        a = max(
            0,
            i - period + 1
        )

        tr_sum = sum(
            tr_list[a:i + 1]
        )

        p_sum = sum(
            plus_dm[a:i + 1]
        )

        m_sum = sum(
            minus_dm[a:i + 1]
        )

        if tr_sum == 0:
            continue

        pdi = (
            p_sum
            / tr_sum
            * 100
        )

        mdi = (
            m_sum
            / tr_sum
            * 100
        )

        den = pdi + mdi

        if den == 0:
            continue

        dx_values.append(
            abs(pdi - mdi)
            / den
            * 100
        )

    if not dx_values:
        return (
            0,
            plus_di,
            minus_di
        )

    adx_value = (
        sum(
            dx_values[-period:]
        )
        /
        min(
            period,
            len(dx_values)
        )
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

    pv = 0
    total_volume = 0

    for i in range(
        start,
        len(close)
    ):

        typical = (
            high[i]
            + low[i]
            + close[i]
        ) / 3

        pv += (
            typical
            * volume[i]
        )

        total_volume += (
            volume[i]
        )

    if total_volume == 0:
        return close[-1]

    return (
        pv
        / total_volume
    )


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

    atr_value = atr(
        high,
        low,
        close,
        period
    )

    if atr_value <= 0:
        return False

    hl2 = (
        high[-1]
        + low[-1]
    ) / 2

    lower = (
        hl2
        - multiplier * atr_value
    )

    return close[-1] > lower


# =========================================================
# TAKER BUY PRESSURE
# =========================================================

def taker_buy_ratio(
    volume,
    taker_buy
):

    if not volume:
        return 0.5

    total = sum(
        volume[-5:]
    )

    buy = sum(
        taker_buy[-5:]
    )

    if total <= 0:
        return 0.5

    return buy / total


# =========================================================
# MOMENTUM
# =========================================================

def momentum(values, bars=5):

    if len(values) <= bars:
        return 0

    return (
        values[-1]
        / values[-1 - bars]
        - 1
    ) * 100


def momentum_acceleration(values):

    if len(values) < 15:
        return 0

    m1 = momentum(
        values,
        5
    )

    m2 = momentum(
        values[:-5],
        5
    )

    return m1 - m2


# =========================================================
# CORRELATION
# =========================================================

def correlation(a, b):

    n = min(
        len(a),
        len(b)
    )

    if n < 20:
        return 0

    a = a[-n:]
    b = b[-n:]

    ma = statistics.mean(a)
    mb = statistics.mean(b)

    numerator = sum(
        (x - ma)
        * (y - mb)
        for x, y in zip(a, b)
    )

    den_a = math.sqrt(
        sum(
            (x - ma) ** 2
            for x in a
        )
    )

    den_b = math.sqrt(
        sum(
            (y - mb) ** 2
            for y in b
        )
    )

    denominator = (
        den_a
        * den_b
    )

    if denominator == 0:
        return 0

    return (
        numerator
        / denominator
    )


# =========================================================
# LEADER / FOLLOWER
# =========================================================

def detect_leader_follower(
    leader_close,
    follower_close
):

    if (
        len(leader_close) < 80
        or len(follower_close) < 80
    ):
        return None

    best_corr = 0
    best_lag = 0

    # 1 candle = 15 minutes
    for lag in range(
        1,
        9
    ):

        leader_returns = []

        follower_returns = []

        for i in range(
            1,
            min(
                len(leader_close),
                len(follower_close)
            )
            - lag
        ):

            lr = (
                leader_close[i]
                / leader_close[i - 1]
                - 1
            )

            fr = (
                follower_close[i + lag]
                / follower_close[i + lag - 1]
                - 1
            )

            leader_returns.append(lr)
            follower_returns.append(fr)

        corr = correlation(
            leader_returns,
            follower_returns
        )

        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_corr < 0.55:
        return None

    leader_mom = momentum(
        leader_close,
        4
    )

    follower_mom = momentum(
        follower_close,
        4
    )

    if leader_mom < 1:
        return None

    if follower_mom > leader_mom * 0.8:
        return None

    return {
        "correlation": best_corr,
        "lag": best_lag * 15,
        "leader_momentum": leader_mom,
        "follower_momentum": follower_mom
    }


# =========================================================
# LUNARCRUSH
# =========================================================

def lunar_get(
    endpoint,
    params=None
):

    if not LUNAR_KEY:
        return None

    try:

        if params:

            endpoint += (
                "?"
                + urllib.parse.urlencode(
                    params
                )
            )

        url = (
            LUNAR_BASE
            + endpoint
        )

        return get(
            url,
            headers={
                "Authorization":
                f"Bearer {LUNAR_KEY}"
            }
        )

    except Exception as e:

        print(
            "LunarCrush error:",
            e
        )

        return None


def load_social_data():

    if not LUNAR_KEY:
        return {}

    data = lunar_get(
        "/public/coins/list/v1"
    )

    if not data:
        return {}

    rows = data.get(
        "data",
        []
    )

    result = {}

    for row in rows:

        symbol = str(
            row.get(
                "symbol",
                ""
            )
        ).upper()

        if not symbol:
            continue

        result[symbol] = row

    print(
        f"LunarCrush: "
        f"{len(result)} coin sosyal verisi."
    )

    return result


# =========================================================
# SECTOR
# =========================================================

def detect_sector(
    symbol,
    social=None
):

    if social:

        categories = social.get(
            "categories",
            []
        )

        text = " ".join(
            str(x).lower()
            for x in categories
        )

        for sector, keywords in (
            SECTOR_KEYWORDS.items()
        ):

            for keyword in keywords:

                if keyword.lower() in text:
                    return sector

    upper = symbol.upper()

    for sector, keywords in (
        SECTOR_KEYWORDS.items()
    ):

        for keyword in keywords:

            key = (
                keyword
                .upper()
                .replace(" ", "")
            )

            if (
                key
                and key in upper
            ):
                return sector

    return "OTHER"


# =========================================================
# SOCIAL SCORE
# =========================================================

def social_score(row):

    if not row:
        return 0

    sentiment = float(
        row.get(
            "sentiment",
            50
        ) or 50
    )

    social_volume = float(
        row.get(
            "social_volume_24h",
            0
        ) or 0
    )

    interactions = float(
        row.get(
            "interactions_24h",
            0
        ) or 0
    )

    galaxy = float(
        row.get(
            "galaxy_score",
            0
        ) or 0
    )

    score = 0

    if sentiment >= 70:
        score += 20
    elif sentiment >= 60:
        score += 12
    elif sentiment >= 55:
        score += 6

    if galaxy >= 70:
        score += 20
    elif galaxy >= 60:
        score += 14
    elif galaxy >= 50:
        score += 8

    if social_volume > 0:
        score += 10

    if interactions > 0:
        score += 10

    return min(
        60,
        score
    )


# =========================================================
# TECHNICAL ANALYSIS
# =========================================================

def technical_analysis(
    symbol
):

    try:

        (
            close,
            high,
            low,
            volume,
            taker_buy
        ) = get_klines(
            symbol,
            "15m",
            200
        )

        (
            close1h,
            high1h,
            low1h,
            vol1h,
            taker1h
        ) = get_klines(
            symbol,
            "1h",
            120
        )

        (
            close4h,
            high4h,
            low4h,
            vol4h,
            taker4h
        ) = get_klines(
            symbol,
            "4h",
            120
        )

        price = close[-1]

        # RSI
        r15 = rsi(close)
        r1h = rsi(close1h)
        r4h = rsi(close4h)

        rsi_change = rsi_slope(
            close
        )

        # EMA
        e9 = ema(
            close,
            9
        )

        e21 = ema(
            close,
            21
        )

        e50 = ema(
            close,
            50
        )

        e21_4h = ema(
            close4h,
            21
        )

        e50_4h = ema(
            close4h,
            50
        )

        # MACD
        macd_line, macd_signal, macd_hist = macd(
            close
        )

        macd_acc = macd_hist_acceleration(
            close
        )

        # BB
        upper, middle, lower = bollinger(
            close
        )

        bb_width_now = bb_width(
            close
        )

        bb_width_old = bb_width(
            close[:-10]
        )

        bb_squeeze = (
            bb_width_now
            < bb_width_old
        )

        # OBV
        obv_values = obv(
            close,
            volume
        )

        obv_rising = (
            obv_values[-1]
            > obv_values[-10]
        )

        # ATR
        atr_value = atr(
            high,
            low,
            close
        )

        # ADX
        adx_value, plus_di, minus_di = adx_di(
            high,
            low,
            close
        )

        # VWAP
        current_vwap = vwap(
            high,
            low,
            close,
            volume
        )

        # Volume
        avg_volume = (
            sum(volume[-21:-1])
            / 20
        )

        volume_ratio = (
            volume[-1]
            / avg_volume
            if avg_volume > 0
            else 1
        )

        previous_avg = (
            sum(volume[-11:-1])
            / 10
        )

        volume_acceleration = (
            volume[-1]
            / previous_avg
            if previous_avg > 0
            else 1
        )

        # Momentum
        mom = momentum(
            close,
            5
        )

        mom_acc = momentum_acceleration(
            close
        )

        # Taker buy
        taker_ratio = taker_buy_ratio(
            volume,
            taker_buy
        )

        # Stoch
        stoch = stoch_rsi(
            close
        )

        # Supertrend
        supertrend_up = supertrend(
            high,
            low,
            close
        )

        # Fresh breakout
        resistance = max(
            high[-25:-1]
        )

        support = min(
            low[-25:-1]
        )

        fresh_long = (
            price > resistance
            and volume_ratio >= 1.5
        )

        fresh_short = (
            price < support
            and volume_ratio >= 1.5
        )

        # Early long
        early_score = 0
        early_reasons = []

        if (
            50 <= r15 <= 65
            and rsi_change > 2
        ):

            early_score += 12
            early_reasons.append(
                "RSI yükseliyor"
            )

        if (
            price > e21
            and e9 > e21
        ):

            early_score += 10
            early_reasons.append(
                "EMA trend"
            )

        if macd_acc > 0:

            early_score += 10
            early_reasons.append(
                "MACD hızlanıyor"
            )

        if obv_rising:

            early_score += 10
            early_reasons.append(
                "OBV yükseliyor"
            )

        if (
            volume_ratio >= 1.3
            and volume_acceleration >= 1.3
        ):

            early_score += 12
            early_reasons.append(
                "Hacim uyanıyor"
            )

        if taker_ratio >= 0.53:

            early_score += 10
            early_reasons.append(
                "Taker buy baskısı"
            )

        if bb_squeeze:

            early_score += 8
            early_reasons.append(
                "BB sıkışması"
            )

        if (
            mom > 0
            and mom < 3
            and mom_acc > 0
        ):

            early_score += 10
            early_reasons.append(
                "Momentum hızlanıyor"
            )

        if (
            price > current_vwap
        ):

            early_score += 8
            early_reasons.append(
                "VWAP üstü"
            )

        if (
            adx_value >= 20
            and plus_di > minus_di
        ):

            early_score += 8
            early_reasons.append(
                "ADX/DI"
            )

        if (
            r4h > 50
            and price > e50
        ):

            early_score += 8
            early_reasons.append(
                "Üst zaman trendi"
            )

        early_score = min(
            100,
            early_score
        )

        return {
            "symbol": symbol,
            "price": price,

            "rsi15": r15,
            "rsi1h": r1h,
            "rsi4h": r4h,
            "rsi_change": rsi_change,

            "ema9": e9,
            "ema21": e21,
            "ema50": e50,

            "macd_hist": macd_hist,
            "macd_acc": macd_acc,

            "bb_width": bb_width_now,
            "bb_squeeze": bb_squeeze,

            "obv_rising": obv_rising,

            "atr": atr_value,

            "adx": adx_value,
            "plus_di": plus_di,
            "minus_di": minus_di,

            "vwap": current_vwap,

            "volume": volume_ratio,
            "volume_acceleration":
                volume_acceleration,

            "momentum": mom,
            "momentum_acceleration":
                mom_acc,

            "taker_ratio":
                taker_ratio,

            "stoch": stoch,

            "supertrend":
                supertrend_up,

            "fresh_long":
                fresh_long,

            "fresh_short":
                fresh_short,

            "early_score":
                early_score,

            "early_reasons":
                early_reasons,

            "close15":
                close,

            "close1h":
                close1h,

            "close4h":
                close4h
        }

    except Exception as e:

        print(
            f"{symbol} teknik hata:",
            e
        )

        return None


# =========================================================
# MARKET REGIME
# =========================================================

def market_regime():

    try:

        btc = technical_analysis(
            "BTCUSDT"
        )

        eth = technical_analysis(
            "ETHUSDT"
        )

        if not btc or not eth:
            return None

        score = 0

        if btc["momentum"] > 0:
            score += 1

        if btc["price"] > btc["ema21"]:
            score += 1

        if btc["rsi15"] > 50:
            score += 1

        if btc["plus_di"] > btc["minus_di"]:
            score += 1

        if eth["momentum"] > 0:
            score += 1

        return {
            "score": score,
            "btc": btc,
            "eth": eth
        }

    except Exception:

        return None


# =========================================================
# SECTOR ROTATION
# =========================================================

def sector_rotation(
    results,
    social_data
):

    sectors = {}

    for result in results:

        symbol = result["symbol"]

        base = symbol.replace(
            "USDT",
            ""
        )

        social = social_data.get(
            base,
            {}
        )

        sector = detect_sector(
            base,
            social
        )

        if sector == "OTHER":
            continue

        if sector not in sectors:
            sectors[sector] = []

        sectors[sector].append(
            result
        )

    sector_stats = {}

    for sector, coins in sectors.items():

        if len(coins) < 3:
            continue

        avg_momentum = statistics.mean(
            x["momentum"]
            for x in coins
        )

        avg_volume = statistics.mean(
            x["volume"]
            for x in coins
        )

        sector_stats[sector] = {
            "momentum":
                avg_momentum,
            "volume":
                avg_volume,
            "coins":
                coins
        }

    return sector_stats


# =========================================================
# EARLY RADAR
# =========================================================

def build_early_radar(
    results,
    social_data,
    sector_stats,
    market
):

    radar = []

    market_bonus = 0

    if market:

        if market["score"] >= 4:
            market_bonus = 10

        elif market["score"] >= 3:
            market_bonus = 6

    for result in results:

        symbol = result["symbol"]

        base = symbol.replace(
            "USDT",
            ""
        )

        social = social_data.get(
            base
        )

        score = (
            result["early_score"]
        )

        reasons = list(
            result["early_reasons"]
        )

        # Market
        score += market_bonus

        if market_bonus:
            reasons.append(
                "Market rejimi pozitif"
            )

        # Sector
        sector = detect_sector(
            base,
            social
        )

        stats = sector_stats.get(
            sector
        )

        if stats:

            sector_momentum = (
                stats["momentum"]
            )

            # Sector güçlü,
            # coin henüz gerideyse
            if (
                sector_momentum >= 1.5
                and result["momentum"]
                < sector_momentum * 0.65
            ):

                score += 15

                reasons.append(
                    f"{sector} sektör gerisinde"
                )

            elif (
                sector_momentum >= 2
                and result["momentum"]
                > 0
            ):

                score += 6

                reasons.append(
                    f"{sector} güçlü"
                )

        # Social
        s_score = social_score(
            social
        )

        if s_score >= 25:

            score += min(
                15,
                s_score // 2
            )

            reasons.append(
                "Sosyal aktivite"
            )

        # Overextension filter
        if (
            result["momentum"] > 7
            or result["rsi15"] > 75
        ):

            score -= 20

        # Need minimum movement
        if result["momentum"] < -3:
            score -= 10

        score = max(
            0,
            min(100, score)
        )

        if score >= 65:

            radar.append({
                "symbol":
                    symbol,

                "score":
                    score,

                "sector":
                    sector,

                "momentum":
                    result["momentum"],

                "volume":
                    result["volume"],

                "reasons":
                    reasons[:8],

                "social":
                    social,

                "technical":
                    result
            })

    radar.sort(
        key=lambda x:
        x["score"],
        reverse=True
    )

    return radar[:5]


# =========================================================
# FOLLOWER RADAR
# =========================================================

def follower_radar(
    results
):

    if len(results) < 5:
        return []

    leaders = sorted(
        results,
        key=lambda x:
        x["momentum"],
        reverse=True
    )[:12]

    followers = sorted(
        results,
        key=lambda x:
        x["momentum"]
    )[:MAX_FOLLOWER_COINS]

    output = []

    cache = {}

    for leader in leaders:

        if leader["momentum"] < 1:
            continue

        for follower in followers:

            if (
                leader["symbol"]
                == follower["symbol"]
            ):
                continue

            key = (
                leader["symbol"],
                follower["symbol"]
            )

            try:

                lc = cache.get(
                    leader["symbol"]
                )

                if lc is None:

                    lc = get_klines(
                        leader["symbol"],
                        "15m",
                        100
                    )[0]

                    cache[
                        leader["symbol"]
                    ] = lc

                fc = cache.get(
                    follower["symbol"]
                )

                if fc is None:

                    fc = get_klines(
                        follower["symbol"],
                        "15m",
                        100
                    )[0]

                    cache[
                        follower["symbol"]
                    ] = fc

                relation = detect_leader_follower(
                    lc,
                    fc
                )

                if not relation:
                    continue

                output.append({
                    "leader":
                        leader["symbol"],

                    "follower":
                        follower["symbol"],

                    "correlation":
                        relation[
                            "correlation"
                        ],

                    "lag":
                        relation["lag"],

                    "leader_momentum":
                        relation[
                            "leader_momentum"
                        ],

                    "follower_momentum":
                        relation[
                            "follower_momentum"
                        ]
                })

            except Exception as e:

                print(
                    "Follower error:",
                    key,
                    e
                )

    output.sort(
        key=lambda x:
        (
            x["correlation"],
            x["leader_momentum"]
        ),
        reverse=True
    )

    return output[:5]


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
# MAIN
# =========================================================

def main():

    print(
        "🚀 EARLY BINANCE "
        "INTELLIGENCE SCANNER"
    )

    # -----------------------------------------------------
    # MARKET
    # -----------------------------------------------------

    market = market_regime()

    # -----------------------------------------------------
    # SOCIAL
    # -----------------------------------------------------

    social_data = load_social_data()

    # -----------------------------------------------------
    # BINANCE 24H
    # -----------------------------------------------------

    tickers = get(
        BINANCE
        + "/api/v3/ticker/24hr"
    )

    candidates = []

    for ticker in tickers:

        symbol = ticker["symbol"]

        if not symbol.endswith(
            "USDT"
        ):
            continue

        if symbol in {
            "BTCUSDT",
            "ETHUSDT"
        }:
            continue

        if (
            symbol.replace(
                "USDT",
                ""
            )
            in STABLECOINS
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

        try:

            qv = float(
                ticker[
                    "quoteVolume"
                ]
            )

            if qv < MIN_24H_QUOTE_VOLUME:
                continue

            candidates.append(
                (
                    symbol,
                    qv
                )
            )

        except Exception:
            continue

    candidates.sort(
        key=lambda x:
        x[1],
        reverse=True
    )

    candidates = candidates[
        :MAX_TECH_COINS
    ]

    print(
        f"{len(candidates)} "
        "coin analiz edilecek."
    )

    results = []

    # -----------------------------------------------------
    # TECHNICAL SCAN
    # -----------------------------------------------------

    for symbol, _ in candidates:

        print(
            "Analiz:",
            symbol
        )

        result = technical_analysis(
            symbol
        )

        if result:
            results.append(
                result
            )

    # -----------------------------------------------------
    # SECTOR
    # -----------------------------------------------------

    sectors = sector_rotation(
        results,
        social_data
    )

    # -----------------------------------------------------
    # EARLY
    # -----------------------------------------------------

    early = build_early_radar(
        results,
        social_data,
        sectors,
        market
    )

    # -----------------------------------------------------
    # FOLLOWER
    # -----------------------------------------------------

    followers = follower_radar(
        results
    )

    # -----------------------------------------------------
    # LONG / SHORT
    # -----------------------------------------------------

    longs = []

    shorts = []

    for r in results:

        long_score = 0
        short_score = 0

        # LONG
        if (
            r["rsi15"] >= 50
            and r["rsi15"] <= 68
        ):
            long_score += 10

        if r["rsi_change"] > 2:
            long_score += 10

        if (
            r["ema9"]
            > r["ema21"]
        ):
            long_score += 10

        if (
            r["price"]
            > r["ema50"]
        ):
            long_score += 8

        if r["macd_acc"] > 0:
            long_score += 10

        if r["obv_rising"]:
            long_score += 8

        if r["volume"] >= 1.5:
            long_score += 8

        if r["taker_ratio"] >= 0.53:
            long_score += 8

        if (
            r["adx"] >= 20
            and r["plus_di"]
            > r["minus_di"]
        ):
            long_score += 10

        if r["price"] > r["vwap"]:
            long_score += 8

        if r["supertrend"]:
            long_score += 8

        if r["fresh_long"]:
            long_score += 12

        # SHORT
        if (
            r["rsi15"] >= 32
            and r["rsi15"] <= 50
        ):
            short_score += 10

        if r["rsi_change"] < -2:
            short_score += 10

        if (
            r["ema9"]
            < r["ema21"]
        ):
            short_score += 10

        if (
            r["price"]
            < r["ema50"]
        ):
            short_score += 8

        if r["macd_acc"] < 0:
            short_score += 10

        if not r["obv_rising"]:
            short_score += 8

        if r["volume"] >= 1.5:
            short_score += 8

        if r["taker_ratio"] <= 0.47:
            short_score += 8

        if (
            r["adx"] >= 20
            and r["minus_di"]
            > r["plus_di"]
        ):
            short_score += 10

        if r["price"] < r["vwap"]:
            short_score += 8

        if not r["supertrend"]:
            short_score += 8

        if r["fresh_short"]:
            short_score += 12

        if (
            long_score >= 85
            and r["fresh_long"]
            and r["momentum"] > 0
            and r["rsi15"] < 72
        ):

            longs.append(
                (
                    long_score,
                    r
                )
            )

        if (
            short_score >= 85
            and r["fresh_short"]
            and r["momentum"] < 0
            and r["rsi15"] > 28
        ):

            shorts.append(
                (
                    short_score,
                    r
                )
            )

    longs.sort(
        key=lambda x:
        x[0],
        reverse=True
    )

    shorts.sort(
        key=lambda x:
        x[0],
        reverse=True
    )

    longs = longs[:3]
    shorts = shorts[:3]

    # -----------------------------------------------------
    # MESSAGE
    # -----------------------------------------------------

    now = datetime.now(
        timezone.utc
    ).strftime(
        "%d.%m.%Y %H:%M UTC"
    )

    message = (
        "🧠 BINANCE EARLY "
        "INTELLIGENCE SCANNER\n\n"

        f"🕐 {now}\n"

        "📊 15m + 1h + 4h\n"

        "🧠 RSI • EMA • MACD • BB\n"

        "📈 OBV • ADX • DI • VWAP\n"

        "🔥 Volume + Taker Buy\n"

        "⚡ Momentum Acceleration\n"

        "🟣 Sector Rotation\n"

        "🔗 Leader → Follower\n"

        "📱 Social Radar\n"

        "🚀 Early Breakout Engine\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # -----------------------------------------------------
    # MARKET
    # -----------------------------------------------------

    message += (
        "🌍 MARKET REGIME\n\n"
    )

    if market:

        message += (
            f"BTC Momentum: "
            f"{market['btc']['momentum']:+.2f}%\n"

            f"BTC RSI: "
            f"{market['btc']['rsi15']:.1f}\n"

            f"ETH Momentum: "
            f"{market['eth']['momentum']:+.2f}%\n"

            f"Market Score: "
            f"{market['score']}/5\n\n"
        )

    else:

        message += (
            "Market verisi alınamadı.\n\n"
        )

    # -----------------------------------------------------
    # EARLY RADAR
    # -----------------------------------------------------

    message += (
        "🟣 EARLY BREAKOUT RADAR\n\n"
    )

    if not early:

        message += (
            "🟡 Şu anda erken hareket "
            "adayı yok.\n\n"
        )

    else:

        for i, item in enumerate(
            early,
            1
        ):

            r = item["technical"]

            message += (
                f"🏆 {i}. "
                f"{item['symbol']}\n"

                f"🟣 EARLY SCORE: "
                f"{item['score']}/100\n"

                f"🏷️ Sektör: "
                f"{item['sector']}\n"

                f"💰 Fiyat: "
                f"{price_format(r['price'])}\n"

                f"📈 Momentum: "
                f"{r['momentum']:+.2f}%\n"

                f"🔥 Hacim: "
                f"x{r['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{r['volume_acceleration']:.1f}\n"

                f"📊 RSI: "
                f"{r['rsi15']:.1f} "
                f"(Δ {r['rsi_change']:+.1f})\n"

                f"📐 ADX: "
                f"{r['adx']:.1f}\n"

                f"🛒 Taker Buy: "
                f"{r['taker_ratio']*100:.1f}%\n"

                f"📊 BB Width: "
                f"{r['bb_width']:.2f}%\n"

                f"🧠 "
                + ", ".join(
                    item["reasons"]
                )
                + "\n"
            )

            social = item["social"]

            if social:

                message += (
                    f"📱 Social sentiment: "
                    f"{float(social.get('sentiment', 0)):.0f}\n"

                    f"🌐 Social volume: "
                    f"{social.get('social_volume_24h', 0)}\n"
                )

            message += (
                "\n━━━━━━━━━━━━━━━━━━\n\n"
            )

    # -----------------------------------------------------
    # FOLLOWER
    # -----------------------------------------------------

    message += (
        "🔗 LEADER → FOLLOWER RADAR\n\n"
    )

    if not followers:

        message += (
            "🟡 Güçlü gecikmeli korelasyon "
            "bulunamadı.\n\n"
        )

    else:

        for item in followers:

            message += (
                f"🚀 Leader: "
                f"{item['leader']}\n"

                f"🎯 Follower: "
                f"{item['follower']}\n"

                f"📊 Korelasyon: "
                f"{item['correlation']:.2f}\n"

                f"⏱️ Tarihsel gecikme: "
                f"{item['lag']} dk\n"

                f"🔥 Leader momentum: "
                f"{item['leader_momentum']:+.2f}%\n"

                f"📈 Follower momentum: "
                f"{item['follower_momentum']:+.2f}%\n\n"
            )

    # -----------------------------------------------------
    # SECTOR ROTATION
    # -----------------------------------------------------

    message += (
        "🔄 SECTOR ROTATION\n\n"
    )

    ranked_sectors = sorted(
        sectors.items(),
        key=lambda x:
        x[1]["momentum"],
        reverse=True
    )

    if not ranked_sectors:

        message += (
            "🟡 Yeterli sektör verisi yok.\n\n"
        )

    else:

        for sector, stats in (
            ranked_sectors[:5]
        ):

            message += (
                f"🔥 {sector}: "
                f"{stats['momentum']:+.2f}% "
                f"| Hacim x"
                f"{stats['volume']:.1f}\n"
            )

        message += "\n"

    # -----------------------------------------------------
    # LONG
    # -----------------------------------------------------

    message += (
        "📈 GÜÇLÜ LONG\n\n"
    )

    if not longs:

        message += (
            "🟡 Fresh breakout şartlarını "
            "karşılayan LONG yok.\n\n"
        )

    else:

        for score, r in longs:

            risk = (
                r["atr"] * 1.5
            )

            sl = (
                r["price"]
                - risk
            )

            tp1 = (
                r["price"]
                + risk
            )

            tp2 = (
                r["price"]
                + risk * 1.5
            )

            tp3 = (
                r["price"]
                + risk * 2
            )

            message += (
                f"🟢 {r['symbol']}\n"

                f"⭐ Sinyal: "
                f"{score}/100\n"

                f"💰 Giriş: "
                f"{price_format(r['price'])}\n"

                f"📊 RSI: "
                f"{r['rsi15']:.1f}\n"

                f"🔥 Hacim: "
                f"x{r['volume']:.1f}\n"

                f"⚡ Momentum: "
                f"{r['momentum']:+.2f}%\n"

                f"📐 ADX: "
                f"{r['adx']:.1f}\n"

                f"🛒 Taker Buy: "
                f"{r['taker_ratio']*100:.1f}%\n"

                f"🛑 SL: "
                f"{price_format(sl)}\n"

                f"🎯 TP1: "
                f"{price_format(tp1)}\n"

                f"🎯 TP2: "
                f"{price_format(tp2)}\n"

                f"🎯 TP3: "
                f"{price_format(tp3)}\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # -----------------------------------------------------
    # SHORT
    # -----------------------------------------------------

    message += (
        "📉 GÜÇLÜ SHORT\n\n"
    )

    if not shorts:

        message += (
            "🟡 Fresh breakdown şartlarını "
            "karşılayan SHORT yok.\n\n"
        )

    else:

        for score, r in shorts:

            risk = (
                r["atr"] * 1.5
            )

            sl = (
                r["price"]
                + risk
            )

            tp1 = (
                r["price"]
                - risk
            )

            tp2 = (
                r["price"]
                - risk * 1.5
            )

            tp3 = (
                r["price"]
                - risk * 2
            )

            message += (
                f"🔴 {r['symbol']}\n"

                f"⭐ Sinyal: "
                f"{score}/100\n"

                f"💰 Giriş: "
                f"{price_format(r['price'])}\n"

                f"📊 RSI: "
                f"{r['rsi15']:.1f}\n"

                f"🔥 Hacim: "
                f"x{r['volume']:.1f}\n"

                f"📉 Momentum: "
                f"{r['momentum']:+.2f}%\n"

                f"📐 ADX: "
                f"{r['adx']:.1f}\n"

                f"🛒 Taker Buy: "
                f"{r['taker_ratio']*100:.1f}%\n"

                f"🛑 SL: "
                f"{price_format(sl)}\n"

                f"🎯 TP1: "
                f"{price_format(tp1)}\n"

                f"🎯 TP2: "
                f"{price_format(tp2)}\n"

                f"🎯 TP3: "
                f"{price_format(tp3)}\n\n"

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # -----------------------------------------------------
    # FOOTER
    # -----------------------------------------------------

    message += (
        "🧠 Mantık:\n"
        "Market → Sektör → Relative Strength → "
        "Leader/Follower → Sosyal → Teknik → Breakout\n\n"

        "📱 Social Radar: "
        + (
            "AKTİF"
            if LUNAR_KEY
            else "PASİF "
            "(LUNARCRUSH_API_KEY yok)"
        )
        + "\n\n"

        "⚠️ Teknik/sosyal sinyal sistemidir. "
        "Yatırım tavsiyesi değildir."
    )

    print(message)

    send_telegram(
        message
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
