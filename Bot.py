import os
import json
import urllib.request
import urllib.parse
import math
from datetime import datetime, timezone


# =========================================================
# CONFIG
# =========================================================

BINANCE = "https://data-api.binance.vision"
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

MIN_24H_VOLUME = 10_000_000
MAX_COINS = 120

STABLECOINS = {
    "USDT", "USDC", "FDUSD", "USDE",
    "TUSD", "DAI", "RLUSD", "USD1", "USDD"
}

EXCLUDED_SUFFIXES = (
    "UPUSDT",
    "DOWNUSDT",
    "BULLUSDT",
    "BEARUSDT"
)


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

    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(
            response.read().decode()
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

    request = urllib.request.Request(
        url,
        data=data,
        method="POST"
    )

    with urllib.request.urlopen(
        request,
        timeout=20
    ):

        print(
            "Telegram mesajı gönderildi."
        )


# =========================================================
# BINANCE
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

    return (
        close,
        high,
        low,
        volume
    )


# =========================================================
# EMA
# =========================================================

def ema(values, period):

    if not values:
        return 0

    if len(values) < period:
        return values[-1]

    multiplier = (
        2 / (period + 1)
    )

    result = sum(
        values[:period]
    ) / period

    for value in values[period:]:

        result = (
            value * multiplier
            +
            result * (
                1 - multiplier
            )
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

    for i in range(
        1,
        len(values)
    ):

        change = (
            values[i]
            -
            values[i - 1]
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    avg_gain = (
        sum(gains[:period])
        /
        period
    )

    avg_loss = (
        sum(losses[:period])
        /
        period
    )

    for i in range(
        period,
        len(gains)
    ):

        avg_gain = (
            (
                avg_gain
                * (period - 1)
            )
            +
            gains[i]
        ) / period

        avg_loss = (
            (
                avg_loss
                * (period - 1)
            )
            +
            losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = (
        avg_gain
        /
        avg_loss
    )

    return (
        100
        -
        (
            100
            /
            (1 + rs)
        )
    )


# =========================================================
# STOCH RSI
# =========================================================

def stoch_rsi(
    values,
    period=14
):

    if len(values) < 40:
        return 50

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

    recent = rsi_values[
        -period:
    ]

    lowest = min(recent)
    highest = max(recent)

    if highest == lowest:
        return 50

    return (
        (
            rsi_values[-1]
            -
            lowest
        )
        /
        (
            highest
            -
            lowest
        )
    ) * 100


# =========================================================
# MACD
# =========================================================

def macd(values):

    if len(values) < 50:
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

    previous_hist = (
        macd_values[-2]
        -
        ema(
            macd_values[:-1],
            9
        )
    )

    return (
        line,
        signal,
        histogram
    )


# =========================================================
# BOLLINGER
# =========================================================

def bollinger(
    values,
    period=20
):

    if len(values) < period:
        return (
            values[-1],
            values[-1],
            values[-1],
            0
        )

    recent = values[
        -period:
    ]

    middle = (
        sum(recent)
        /
        period
    )

    variance = (
        sum(
            (
                x - middle
            ) ** 2
            for x in recent
        )
        /
        period
    )

    std = math.sqrt(
        variance
    )

    upper = (
        middle
        +
        2 * std
    )

    lower = (
        middle
        -
        2 * std
    )

    width = (
        (
            upper - lower
        )
        /
        middle
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

        if (
            values[i]
            >
            values[i - 1]
        ):

            result += volumes[i]

        elif (
            values[i]
            <
            values[i - 1]
        ):

            result -= volumes[i]

        output.append(result)

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
                -
                close[i - 1]
            ),
            abs(
                low[i]
                -
                close[i - 1]
            )
        )

        trs.append(tr)

    return (
        sum(
            trs[-period:]
        )
        /
        period
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
            -
            high[i - 1]
        )

        down_move = (
            low[i - 1]
            -
            low[i]
        )

        tr = max(
            high[i] - low[i],
            abs(
                high[i]
                -
                close[i - 1]
            ),
            abs(
                low[i]
                -
                close[i - 1]
            )
        )

        tr_list.append(tr)

        plus_dm.append(
            up_move
            if (
                up_move > down_move
                and
                up_move > 0
            )
            else 0
        )

        minus_dm.append(
            down_move
            if (
                down_move > up_move
                and
                down_move > 0
            )
            else 0
        )

    atr_value = (
        sum(
            tr_list[-period:]
        )
        /
        period
    )

    if atr_value <= 0:
        return 0, 0, 0

    plus_di = (
        sum(
            plus_dm[-period:]
        )
        /
        period
        /
        atr_value
        * 100
    )

    minus_di = (
        sum(
            minus_dm[-period:]
        )
        /
        period
        /
        atr_value
        * 100
    )

    dx_values = []

    for i in range(
        period,
        len(tr_list)
    ):

        tr_sum = sum(
            tr_list[
                i - period + 1:
                i + 1
            ]
        )

        if tr_sum <= 0:
            continue

        pdi = (
            sum(
                plus_dm[
                    i - period + 1:
                    i + 1
                ]
            )
            /
            tr_sum
            * 100
        )

        mdi = (
            sum(
                minus_dm[
                    i - period + 1:
                    i + 1
                ]
            )
            /
            tr_sum
            * 100
        )

        denominator = (
            pdi + mdi
        )

        if denominator <= 0:
            continue

        dx_values.append(
            abs(
                pdi - mdi
            )
            /
            denominator
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
            +
            low[i]
            +
            close[i]
        ) / 3

        pv += (
            typical
            *
            volume[i]
        )

        total_volume += volume[i]

    if total_volume <= 0:
        return close[-1]

    return (
        pv
        /
        total_volume
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

    if len(close) < period + 5:
        return None

    trs = []

    for i in range(
        1,
        len(close)
    ):

        trs.append(
            max(
                high[i] - low[i],
                abs(
                    high[i]
                    -
                    close[i - 1]
                ),
                abs(
                    low[i]
                    -
                    close[i - 1]
                )
            )
        )

    atr_value = (
        sum(
            trs[-period:]
        )
        /
        period
    )

    hl2 = (
        high[-1]
        +
        low[-1]
    ) / 2

    upper = (
        hl2
        +
        multiplier
        * atr_value
    )

    lower = (
        hl2
        -
        multiplier
        * atr_value
    )

    return {
        "bull": close[-1] > lower,
        "bear": close[-1] < upper,
        "upper": upper,
        "lower": lower
    }


# =========================================================
# TDI
# =========================================================

def tdi(
    values
):

    if len(values) < 40:
        return 50, 50

    rsi_values = []

    for i in range(
        14,
        len(values)
    ):

        rsi_values.append(
            rsi(
                values[:i + 1],
                14
            )
        )

    if len(rsi_values) < 15:
        return 50, 50

    rsi_line = rsi_values[-1]

    signal_line = ema(
        rsi_values,
        7
    )

    return (
        rsi_line,
        signal_line
    )


# =========================================================
# BREAKOUT
# =========================================================

def breakout_data(
    close,
    high,
    low,
    volume
):

    if len(close) < 40:
        return {
            "long": False,
            "short": False,
            "resistance": 0,
            "support": 0,
            "volume_ratio": 0
        }

    resistance = max(
        high[-21:-1]
    )

    support = min(
        low[-21:-1]
    )

    avg_volume = (
        sum(
            volume[-21:-1]
        )
        /
        20
    )

    volume_ratio = (
        volume[-1]
        /
        avg_volume
        if avg_volume > 0
        else 0
    )

    return {
        "long": (
            close[-1] > resistance
            and
            volume_ratio >= 1.8
        ),
        "short": (
            close[-1] < support
            and
            volume_ratio >= 1.8
        ),
        "resistance": resistance,
        "support": support,
        "volume_ratio": volume_ratio
    }


# =========================================================
# PATTERNS
# =========================================================

def detect_patterns(
    close,
    high,
    low,
    volume
):

    patterns = []

    if len(close) < 60:
        return patterns

    avg_volume = (
        sum(
            volume[-21:-1]
        )
        /
        20
    )

    if avg_volume <= 0:
        return patterns

    vr = (
        volume[-1]
        /
        avg_volume
    )

    current = close[-1]

    # -----------------------------------------------------
    # BULL FLAG
    # -----------------------------------------------------

    pole_start = close[-35]
    pole_end = close[-20]

    pole_gain = (
        pole_end
        /
        pole_start
        - 1
    ) * 100

    flag_high = max(
        high[-20:-1]
    )

    flag_low = min(
        low[-20:-1]
    )

    flag_range = (
        (
            flag_high
            -
            flag_low
        )
        /
        flag_high
        * 100
    )

    if (
        pole_gain >= 4
        and flag_range <= 8
        and current > flag_high
        and vr >= 1.8
    ):

        patterns.append({
            "name":
                "🚩 BULL FLAG KIRILDI",
            "direction":
                "LONG",
            "level":
                flag_high
        })

    # -----------------------------------------------------
    # BEAR FLAG
    # -----------------------------------------------------

    pole_drop = (
        1
        -
        pole_end
        /
        pole_start
    ) * 100

    if (
        pole_drop >= 4
        and flag_range <= 8
        and current < flag_low
        and vr >= 1.8
    ):

        patterns.append({
            "name":
                "🚩 BEAR FLAG KIRILDI",
            "direction":
                "SHORT",
            "level":
                flag_low
        })

    # -----------------------------------------------------
    # RANGE BREAKOUT
    # -----------------------------------------------------

    resistance = max(
        high[-25:-1]
    )

    support = min(
        low[-25:-1]
    )

    if (
        current > resistance
        and vr >= 2
    ):

        patterns.append({
            "name":
                "📦 RANGE BREAKOUT KIRILDI",
            "direction":
                "LONG",
            "level":
                resistance
        })

    if (
        current < support
        and vr >= 2
    ):

        patterns.append({
            "name":
                "📦 RANGE BREAKDOWN KIRILDI",
            "direction":
                "SHORT",
            "level":
                support
        })

    # -----------------------------------------------------
    # ASCENDING TRIANGLE
    # -----------------------------------------------------

    high_old = max(
        high[-30:-15]
    )

    high_new = max(
        high[-15:-1]
    )

    low_old = min(
        low[-30:-15]
    )

    low_new = min(
        low[-15:-1]
    )

    if (
        abs(
            high_new
            -
            high_old
        )
        /
        max(high_old, 1e-12)
        < 0.025
        and
        low_new > low_old
        and
        current > high_new
        and
        vr >= 1.8
    ):

        patterns.append({
            "name":
                "🔺 ASCENDING TRIANGLE KIRILDI",
            "direction":
                "LONG",
            "level":
                high_new
        })

    # -----------------------------------------------------
    # DESCENDING TRIANGLE
    # -----------------------------------------------------

    if (
        abs(
            low_new
            -
            low_old
        )
        /
        max(low_old, 1e-12)
        < 0.025
        and
        high_new < high_old
        and
        current < low_new
        and
        vr >= 1.8
    ):

        patterns.append({
            "name":
                "🔻 DESCENDING TRIANGLE KIRILDI",
            "direction":
                "SHORT",
            "level":
                low_new
        })

    # -----------------------------------------------------
    # CUP & HANDLE
    # -----------------------------------------------------

    if len(close) >= 80:

        window = close[-70:]

        left = max(
            window[:20]
        )

        middle = min(
            window[20:50]
        )

        right = max(
            window[50:60]
        )

        neckline = min(
            left,
            right
        )

        depth = (
            neckline
            -
            middle
        ) / neckline

        if (
            depth >= 0.08
            and
            depth <= 0.40
            and
            abs(
                left - right
            )
            /
            neckline
            <= 0.06
            and
            current > neckline
            and
            vr >= 1.8
        ):

            patterns.append({
                "name":
                    "🥣 CUP & HANDLE KIRILDI",
                "direction":
                    "LONG",
                "level":
                    neckline
            })

    return patterns


# =========================================================
# MOMENTUM
# =========================================================

def momentum_percent(
    close,
    bars=5
):

    if len(close) <= bars:
        return 0

    return (
        close[-1]
        /
        close[-1 - bars]
        - 1
    ) * 100


# =========================================================
# PUMP / DUMP RADAR
# =========================================================

def pump_dump_radar(
    close,
    high,
    low,
    volume,
    adx_value,
    plus_di,
    minus_di
):

    if len(close) < 40:
        return None

    price = close[-1]

    mom5 = momentum_percent(
        close,
        5
    )

    mom3 = momentum_percent(
        close,
        3
    )

    avg_volume = (
        sum(
            volume[-21:-1]
        )
        /
        20
    )

    if avg_volume <= 0:
        return None

    volume_ratio = (
        volume[-1]
        /
        avg_volume
    )

    previous_avg = (
        sum(
            volume[-11:-1]
        )
        /
        10
    )

    acceleration = (
        volume[-1]
        /
        previous_avg
        if previous_avg > 0
        else 1
    )

    breakout = breakout_data(
        close,
        high,
        low,
        volume
    )

    # =====================================================
    # PUMP
    # =====================================================

    pump = 0
    pump_reasons = []

    if mom5 >= 5:
        pump += 25
        pump_reasons.append(
            "5m+ momentum"
        )

    elif mom5 >= 3:
        pump += 18
        pump_reasons.append(
            "momentum"
        )

    elif mom5 >= 2:
        pump += 10

    if mom3 >= 2:
        pump += 10

    if volume_ratio >= 5:
        pump += 25
        pump_reasons.append(
            "volume explosion"
        )

    elif volume_ratio >= 3:
        pump += 18
        pump_reasons.append(
            "strong volume"
        )

    elif volume_ratio >= 2:
        pump += 10

    if acceleration >= 5:
        pump += 20
        pump_reasons.append(
            "volume acceleration"
        )

    elif acceleration >= 3:
        pump += 14
        pump_reasons.append(
            "volume acceleration"
        )

    elif acceleration >= 2:
        pump += 8

    if adx_value >= 35:
        pump += 10
        pump_reasons.append(
            "ADX strong"
        )

    if plus_di > minus_di:
        pump += 8

    if breakout["long"]:
        pump += 15
        pump_reasons.append(
            "breakout"
        )

    # aşırı şişmiş hareketleri ayrıca işaretle
    if mom5 >= 10:
        pump -= 10

    pump = max(
        0,
        min(100, pump)
    )

    if (
        pump >= 70
        and
        mom5 >= 2
        and
        volume_ratio >= 2
        and
        acceleration >= 1.5
    ):

        return {
            "type":
                "PUMP",
            "score":
                pump,
            "momentum":
                mom5,
            "volume":
                volume_ratio,
            "acceleration":
                acceleration,
            "adx":
                adx_value,
            "reasons":
                pump_reasons
        }

    # =====================================================
    # DUMP
    # =====================================================

    dump = 0
    dump_reasons = []

    if mom5 <= -5:
        dump += 25
        dump_reasons.append(
            "negative momentum"
        )

    elif mom5 <= -3:
        dump += 18
        dump_reasons.append(
            "negative momentum"
        )

    elif mom5 <= -2:
        dump += 10

    if mom3 <= -2:
        dump += 10

    if volume_ratio >= 5:
        dump += 25
        dump_reasons.append(
            "volume explosion"
        )

    elif volume_ratio >= 3:
        dump += 18
        dump_reasons.append(
            "strong volume"
        )

    elif volume_ratio >= 2:
        dump += 10

    if acceleration >= 5:
        dump += 20
        dump_reasons.append(
            "volume acceleration"
        )

    elif acceleration >= 3:
        dump += 14
        dump_reasons.append(
            "volume acceleration"
        )

    elif acceleration >= 2:
        dump += 8

    if adx_value >= 35:
        dump += 10
        dump_reasons.append(
            "ADX strong"
        )

    if minus_di > plus_di:
        dump += 8

    if breakout["short"]:
        dump += 15
        dump_reasons.append(
            "breakdown"
        )

    dump = max(
        0,
        min(100, dump)
    )

    if (
        dump >= 70
        and
        mom5 <= -2
        and
        volume_ratio >= 2
        and
        acceleration >= 1.5
    ):

        return {
            "type":
                "DUMP",
            "score":
                dump,
            "momentum":
                mom5,
            "volume":
                volume_ratio,
            "acceleration":
                acceleration,
            "adx":
                adx_value,
            "reasons":
                dump_reasons
        }

    return None


# =========================================================
# PRICE FORMAT
# =========================================================

def price_format(
    value
):

    if value >= 100:
        return f"{value:.2f}"

    if value >= 1:
        return f"{value:.4f}"

    if value >= 0.01:
        return f"{value:.6f}"

    return f"{value:.10f}"


def stablecoin_pair(
    symbol
):

    base = symbol.replace(
        "USDT",
        ""
    )

    return (
        base
        in STABLECOINS
    )


# =========================================================
# ANALYZE
# =========================================================

def analyze(
    symbol
):

    try:

        c15, h15, l15, v15 = get_klines(
            symbol,
            "15m"
        )

        c1h, h1h, l1h, v1h = get_klines(
            symbol,
            "1h"
        )

        c4h, h4h, l4h, v4h = get_klines(
            symbol,
            "4h"
        )

        price = c15[-1]

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        r15 = rsi(c15)
        r1h = rsi(c1h)
        r4h = rsi(c4h)

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        e9 = ema(c15, 9)
        e21 = ema(c15, 21)
        e50 = ema(c15, 50)

        e21_1h = ema(c1h, 21)
        e50_1h = ema(c1h, 50)

        e21_4h = ema(c4h, 21)
        e50_4h = ema(c4h, 50)

        # -------------------------------------------------
        # MACD
        # -------------------------------------------------

        m15, s15, hmacd15 = macd(c15)
        m1h, s1h, hmacd1h = macd(c1h)

        macd_bull = (
            m1h > s1h
            and
            hmacd1h > 0
        )

        macd_bear = (
            m1h < s1h
            and
            hmacd1h < 0
        )

        # -------------------------------------------------
        # STOCH RSI
        # -------------------------------------------------

        stoch = stoch_rsi(
            c15
        )

        # -------------------------------------------------
        # BOLLINGER
        # -------------------------------------------------

        upper, middle, lower, bb_width = bollinger(
            c15
        )

        bb_break_long = (
            price > upper
        )

        bb_break_short = (
            price < lower
        )

        # -------------------------------------------------
        # OBV
        # -------------------------------------------------

        obv_values = obv(
            c15,
            v15
        )

        obv_bull = (
            obv_values[-1]
            >
            obv_values[-5]
        )

        obv_bear = (
            obv_values[-1]
            <
            obv_values[-5]
        )

        # -------------------------------------------------
        # ATR
        # -------------------------------------------------

        atr_value = atr(
            h15,
            l15,
            c15
        )

        if atr_value <= 0:
            return None

        atr_percent = (
            atr_value
            /
            price
            * 100
        )

        # -------------------------------------------------
        # ADX
        # -------------------------------------------------

        adx_value, plus_di, minus_di = adx_di(
            h15,
            l15,
            c15
        )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        current_vwap = vwap(
            h15,
            l15,
            c15,
            v15
        )

        # -------------------------------------------------
        # SUPERTREND
        # -------------------------------------------------

        st = supertrend(
            h15,
            l15,
            c15
        )

        st_bull = (
            st is not None
            and
            st["bull"]
            and
            price > st["lower"]
        )

        st_bear = (
            st is not None
            and
            st["bear"]
            and
            price < st["upper"]
        )

        # -------------------------------------------------
        # TDI
        # -------------------------------------------------

        tdi_rsi, tdi_signal = tdi(
            c15
        )

        tdi_bull = (
            tdi_rsi
            >
            tdi_signal
            and
            tdi_rsi >= 50
        )

        tdi_bear = (
            tdi_rsi
            <
            tdi_signal
            and
            tdi_rsi <= 50
        )

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        avg_volume = (
            sum(
                v15[-21:-1]
            )
            /
            20
        )

        if avg_volume <= 0:
            return None

        volume_ratio = (
            v15[-1]
            /
            avg_volume
        )

        previous_avg = (
            sum(
                v15[-11:-1]
            )
            /
            10
        )

        acceleration = (
            v15[-1]
            /
            previous_avg
            if previous_avg > 0
            else 1
        )

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        mom3 = momentum_percent(
            c15,
            3
        )

        mom5 = momentum_percent(
            c15,
            5
        )

        mom15 = momentum_percent(
            c15,
            15
        )

        # -------------------------------------------------
        # BREAKOUT
        # -------------------------------------------------

        breakout = breakout_data(
            c15,
            h15,
            l15,
            v15
        )

        # -------------------------------------------------
        # PATTERNS
        # -------------------------------------------------

        patterns = detect_patterns(
            c15,
            h15,
            l15,
            v15
        )

        long_patterns = [
            x for x in patterns
            if x["direction"] == "LONG"
        ]

        short_patterns = [
            x for x in patterns
            if x["direction"] == "SHORT"
        ]

        # =================================================
        # LONG
        # =================================================

        long_score = 0
        long_reasons = []

        # Trend 15m
        if (
            price > e9 > e21 > e50
        ):

            long_score += 15
            long_reasons.append(
                "15m EMA trend"
            )

        elif (
            price > e21
            and
            e21 > e50
        ):

            long_score += 8

        # 1h trend
        if (
            price > e21_1h
            and
            e21_1h > e50_1h
        ):

            long_score += 12
            long_reasons.append(
                "1h trend"
            )

        # 4h trend
        if (
            price > e21_4h
            and
            e21_4h > e50_4h
        ):

            long_score += 15
            long_reasons.append(
                "4h trend"
            )

        # RSI
        if (
            52 <= r15 <= 68
        ):

            long_score += 8
            long_reasons.append(
                "RSI"
            )

        # 1h RSI
        if (
            50 <= r1h <= 70
        ):

            long_score += 5

        # MACD
        if macd_bull:

            long_score += 10
            long_reasons.append(
                "MACD"
            )

        # TDI
        if tdi_bull:

            long_score += 6
            long_reasons.append(
                "TDI"
            )

        # OBV
        if obv_bull:

            long_score += 6
            long_reasons.append(
                "OBV"
            )

        # VWAP
        if price > current_vwap:

            long_score += 7
            long_reasons.append(
                "VWAP"
            )

        # ADX
        if (
            adx_value >= 25
            and
            plus_di > minus_di
        ):

            long_score += 10
            long_reasons.append(
                "ADX/DI"
            )

        # Supertrend
        if st_bull:

            long_score += 8
            long_reasons.append(
                "Supertrend"
            )

        # Momentum
        if (
            0.8 <= mom5 <= 6
        ):

            long_score += 8
            long_reasons.append(
                "Momentum"
            )

        # Volume
        if volume_ratio >= 3:

            long_score += 10
            long_reasons.append(
                "Volume x3+"
            )

        elif volume_ratio >= 2:

            long_score += 7

        elif volume_ratio >= 1.5:

            long_score += 4

        # Acceleration
        if acceleration >= 3:

            long_score += 7
            long_reasons.append(
                "Volume acceleration"
            )

        # Breakout
        if breakout["long"]:

            long_score += 12
            long_reasons.append(
                "BREAKOUT"
            )

        # Pattern
        if long_patterns:

            long_score += 8
            long_reasons.append(
                long_patterns[0]["name"]
            )

        # Bollinger
        if (
            bb_break_long
            and
            volume_ratio >= 2
        ):

            long_score += 8
            long_reasons.append(
                "BB breakout"
            )

        # =================================================
        # SHORT
        # =================================================

        short_score = 0
        short_reasons = []

        if (
            price < e9 < e21 < e50
        ):

            short_score += 15
            short_reasons.append(
                "15m EMA downtrend"
            )

        elif (
            price < e21
            and
            e21 < e50
        ):

            short_score += 8

        if (
            price < e21_1h
            and
            e21_1h < e50_1h
        ):

            short_score += 12
            short_reasons.append(
                "1h downtrend"
            )

        if (
            price < e21_4h
            and
            e21_4h < e50_4h
        ):

            short_score += 15
            short_reasons.append(
                "4h downtrend"
            )

        if (
            32 <= r15 <= 48
        ):

            short_score += 8
            short_reasons.append(
                "RSI weakness"
            )

        if (
            30 <= r1h <= 50
        ):

            short_score += 5

        if macd_bear:

            short_score += 10
            short_reasons.append(
                "MACD"
            )

        if tdi_bear:

            short_score += 6
            short_reasons.append(
                "TDI"
            )

        if obv_bear:

            short_score += 6
            short_reasons.append(
                "OBV"
            )

        if price < current_vwap:

            short_score += 7
            short_reasons.append(
                "VWAP"
            )

        if (
            adx_value >= 25
            and
            minus_di > plus_di
        ):

            short_score += 10
            short_reasons.append(
                "ADX/DI"
            )

        if st_bear:

            short_score += 8
            short_reasons.append(
                "Supertrend"
            )

        if (
            -6 <= mom5 <= -0.8
        ):

            short_score += 8
            short_reasons.append(
                "Momentum"
            )

        if volume_ratio >= 3:

            short_score += 10
            short_reasons.append(
                "Volume x3+"
            )

        elif volume_ratio >= 2:

            short_score += 7

        elif volume_ratio >= 1.5:

            short_score += 4

        if acceleration >= 3:

            short_score += 7
            short_reasons.append(
                "Volume acceleration"
            )

        if breakout["short"]:

            short_score += 12
            short_reasons.append(
                "BREAKDOWN"
            )

        if short_patterns:

            short_score += 8
            short_reasons.append(
                short_patterns[0]["name"]
            )

        if (
            bb_break_short
            and
            volume_ratio >= 2
        ):

            short_score += 8
            short_reasons.append(
                "BB breakdown"
            )

        # =================================================
        # ANTI FALSE SIGNAL
        # =================================================

        # Çok düşük momentum varsa güçlü AL/SAT olmasın
        if abs(mom5) < 0.5:

            long_score -= 15
            short_score -= 15

        # Çok düşük hacim
        if volume_ratio < 1.2:

            long_score -= 15
            short_score -= 15

        # Çok düşük trend gücü
        if adx_value < 18:

            long_score -= 12
            short_score -= 12

        # Aşırı alımda AL engelle
        if stoch > 94:

            long_score -= 12

        # Aşırı satımda SHORT engelle
        if stoch < 6:

            short_score -= 12

        long_score = max(
            0,
            min(100, long_score)
        )

        short_score = max(
            0,
            min(100, short_score)
        )

        # =================================================
        # STRONG SIGNAL
        # =================================================

        long_signal = None
        short_signal = None

        # Güçlü AL için minimum bağımsız teyit
        long_confirmations = sum([
            price > e21,
            price > e50,
            price > e21_4h,
            macd_bull,
            tdi_bull,
            obv_bull,
            price > current_vwap,
            plus_di > minus_di,
            st_bull,
            volume_ratio >= 1.8,
            mom5 >= 0.8
        ])

        short_confirmations = sum([
            price < e21,
            price < e50,
            price < e21_4h,
            macd_bear,
            tdi_bear,
            obv_bear,
            price < current_vwap,
            minus_di > plus_di,
            st_bear,
            volume_ratio >= 1.8,
            mom5 <= -0.8
        ])

        if (
            long_score >= 72
            and
            long_confirmations >= 8
            and
            volume_ratio >= 1.8
            and
            adx_value >= 20
            and
            plus_di > minus_di
            and
            mom5 >= 0.8
            and
            price > current_vwap
        ):

            long_signal = (
                "🟢 GÜÇLÜ AL"
            )

        if (
            short_score >= 72
            and
            short_confirmations >= 8
            and
            volume_ratio >= 1.8
            and
            adx_value >= 20
            and
            minus_di > plus_di
            and
            mom5 <= -0.8
            and
            price < current_vwap
        ):

            short_signal = (
                "🔴 GÜÇLÜ SAT"
            )

        # =================================================
        # RADAR
        # =================================================

        radar = pump_dump_radar(
            c15,
            h15,
            l15,
            v15,
            adx_value,
            plus_di,
            minus_di
        )

        # =================================================
        # REAL RISK / REWARD
        # =================================================

        risk_distance = (
            atr_value * 1.35
        )

        long_sl = (
            price
            -
            risk_distance
        )

        short_sl = (
            price
            +
            risk_distance
        )

        long_tp1 = (
            price
            +
            risk_distance
            * 1.0
        )

        long_tp2 = (
            price
            +
            risk_distance
            * 1.5
        )

        long_tp3 = (
            price
            +
            risk_distance
            * 2.0
        )

        short_tp1 = (
            price
            -
            risk_distance
            * 1.0
        )

        short_tp2 = (
            price
            -
            risk_distance
            * 1.5
        )

        short_tp3 = (
            price
            -
            risk_distance
            * 2.0
        )

        return {
            "symbol": symbol,
            "price": price,

            "long_score": long_score,
            "short_score": short_score,

            "long_signal": long_signal,
            "short_signal": short_signal,

            "long_confirmations":
                long_confirmations,

            "short_confirmations":
                short_confirmations,

            "long_reasons":
                long_reasons,

            "short_reasons":
                short_reasons,

            "rsi15": r15,
            "rsi1h": r1h,
            "rsi4h": r4h,

            "stoch": stoch,

            "volume":
                volume_ratio,

            "acceleration":
                acceleration,

            "momentum":
                mom5,

            "momentum15":
                mom15,

            "adx":
                adx_value,

            "plus_di":
                plus_di,

            "minus_di":
                minus_di,

            "vwap":
                current_vwap,

            "bb_width":
                bb_width,

            "atr_percent":
                atr_percent,

            "patterns":
                patterns,

            "breakout":
                breakout,

            "radar":
                radar,

            "long_sl":
                long_sl,

            "long_tp1":
                long_tp1,

            "long_tp2":
                long_tp2,

            "long_tp3":
                long_tp3,

            "short_sl":
                short_sl,

            "short_tp1":
                short_tp1,

            "short_tp2":
                short_tp2,

            "short_tp3":
                short_tp3
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
        "🚀 GELİŞMİŞ BINANCE SCANNER"
    )

    tickers = get(
        BINANCE
        +
        "/api/v3/ticker/24hr"
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

        if stablecoin_pair(
            symbol
        ):
            continue

        if any(
            symbol.endswith(x)
            for x in EXCLUDED_SUFFIXES
        ):
            continue

        try:

            quote_volume = float(
                ticker[
                    "quoteVolume"
                ]
            )

            if (
                quote_volume
                <
                MIN_24H_VOLUME
            ):
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
        :MAX_COINS
    ]

    print(
        f"{len(candidates)} coin analiz edilecek."
    )

    results = []

    for symbol, _ in candidates:

        print(
            "Analiz:",
            symbol
        )

        result = analyze(
            symbol
        )

        if result:
            results.append(
                result
            )

    # =====================================================
    # STRONG LONG
    # =====================================================

    longs = [
        x for x in results
        if x["long_signal"]
        ==
        "🟢 GÜÇLÜ AL"
    ]

    longs.sort(
        key=lambda x: (
            x["long_score"],
            x["volume"],
            x["momentum"]
        ),
        reverse=True
    )

    longs = longs[:3]

    # =====================================================
    # STRONG SHORT
    # =====================================================

    shorts = [
        x for x in results
        if x["short_signal"]
        ==
        "🔴 GÜÇLÜ SAT"
    ]

    shorts.sort(
        key=lambda x: (
            x["short_score"],
            x["volume"],
            abs(x["momentum"])
        ),
        reverse=True
    )

    shorts = shorts[:3]

    # =====================================================
    # PUMP
    # =====================================================

    pumps = [
        x for x in results
        if (
            x["radar"]
            and
            x["radar"]["type"]
            ==
            "PUMP"
        )
    ]

    pumps.sort(
        key=lambda x:
            x["radar"]["score"],
        reverse=True
    )

    pumps = pumps[:3]

    # =====================================================
    # DUMP
    # =====================================================

    dumps = [
        x for x in results
        if (
            x["radar"]
            and
            x["radar"]["type"]
            ==
            "DUMP"
        )
    ]

    dumps.sort(
        key=lambda x:
            x["radar"]["score"],
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

        "🚩 Flag / Triangle\n"

        "🥣 Cup & Handle\n"

        "🎯 ATR + gerçek R/R\n"

        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    # =====================================================
    # LONG
    # =====================================================

    message += (
        "📈 LONG FIRSATLARI\n\n"
    )

    if not longs:

        message += (
            "🟡 Şu anda trade edilebilir "
            "GÜÇLÜ LONG sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            longs,
            1
        ):

            message += (
                f"🏆 {i}. "
                f"{coin['symbol']}\n"

                f"🟢 GÜÇLÜ AL\n"

                f"⭐ Sinyal: "
                f"{coin['long_score']}/100\n"

                f"🔎 Teyit: "
                f"{coin['long_confirmations']}/11\n\n"

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
                f"x{coin['acceleration']:.1f}\n"

                f"🚀 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"
            )

            if coin["long_reasons"]:

                message += (
                    "🧠 Teyitler: "
                    +
                    ", ".join(
                        coin[
                            "long_reasons"
                        ][:8]
                    )
                    +
                    "\n"
                )

            for pattern in coin[
                "patterns"
            ]:

                if (
                    pattern["direction"]
                    ==
                    "LONG"
                ):

                    message += (
                        "\n💥 FORMASYON KIRILDI\n"
                        f"{pattern['name']}\n"
                        f"📍 Seviye: "
                        f"{price_format(pattern['level'])}\n"
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

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # =====================================================
    # SHORT
    # =====================================================

    message += (
        "📉 SHORT FIRSATLARI\n\n"
    )

    if not shorts:

        message += (
            "🟡 Şu anda trade edilebilir "
            "GÜÇLÜ SHORT sinyali yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            shorts,
            1
        ):

            message += (
                f"🏆 {i}. "
                f"{coin['symbol']}\n"

                f"🔴 GÜÇLÜ SAT\n"

                f"⭐ Sinyal: "
                f"{coin['short_score']}/100\n"

                f"🔎 Teyit: "
                f"{coin['short_confirmations']}/11\n\n"

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
                f"x{coin['acceleration']:.1f}\n"

                f"📉 Momentum: "
                f"{coin['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{coin['adx']:.1f}\n"

                f"📍 VWAP: "
                f"{price_format(coin['vwap'])}\n"
            )

            if coin["short_reasons"]:

                message += (
                    "🧠 Teyitler: "
                    +
                    ", ".join(
                        coin[
                            "short_reasons"
                        ][:8]
                    )
                    +
                    "\n"
                )

            for pattern in coin[
                "patterns"
            ]:

                if (
                    pattern["direction"]
                    ==
                    "SHORT"
                ):

                    message += (
                        "\n💥 FORMASYON KIRILDI\n"
                        f"{pattern['name']}\n"
                        f"📍 Seviye: "
                        f"{price_format(pattern['level'])}\n"
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

                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    # =====================================================
    # PUMP
    # =====================================================

    message += (
        "🚀 PUMP RADAR\n\n"
    )

    if not pumps:

        message += (
            "🟡 Şu anda güçlü pump "
            "hareketi yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            pumps,
            1
        ):

            radar = coin[
                "radar"
            ]

            message += (
                f"🚀 {i}. "
                f"{coin['symbol']}\n"

                "⚡ HAREKETLENİYOR\n"

                f"⭐ Pump gücü: "
                f"{radar['score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{radar['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{radar['acceleration']:.1f}\n"

                f"🚀 Momentum: "
                f"{radar['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{radar['adx']:.1f}\n"
            )

            if radar["reasons"]:

                message += (
                    "🧠 Neden: "
                    +
                    ", ".join(
                        radar["reasons"]
                    )
                    +
                    "\n"
                )

            message += "\n"

    # =====================================================
    # DUMP
    # =====================================================

    message += (
        "💣 DUMP RADAR\n\n"
    )

    if not dumps:

        message += (
            "🟡 Şu anda güçlü dump "
            "hareketi yok.\n\n"
        )

    else:

        for i, coin in enumerate(
            dumps,
            1
        ):

            radar = coin[
                "radar"
            ]

            message += (
                f"💣 {i}. "
                f"{coin['symbol']}\n"

                "⚡ DÜŞÜŞ HIZLANIYOR\n"

                f"⭐ Dump gücü: "
                f"{radar['score']}/100\n\n"

                f"💰 Fiyat: "
                f"{price_format(coin['price'])}\n"

                f"🔥 Hacim: "
                f"x{radar['volume']:.1f}\n"

                f"⚡ Hacim ivmesi: "
                f"x{radar['acceleration']:.1f}\n"

                f"📉 Momentum: "
                f"{radar['momentum']:+.1f}%\n"

                f"📐 ADX: "
                f"{radar['adx']:.1f}\n"
            )

            if radar["reasons"]:

                message += (
                    "🧠 Neden: "
                    +
                    ", ".join(
                        radar["reasons"]
                    )
                    +
                    "\n"
                )

            message += "\n"

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "⚠️ Teknik sinyal sistemidir. "
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
