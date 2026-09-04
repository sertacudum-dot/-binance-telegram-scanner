import os
import json
import time
import math
import csv
import argparse
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

# =========================================================
# CONFIG
# =========================================================

BINANCE = "https://data-api.binance.vision"
# .get() kullanıyoruz ki bu dosya (Bot.py) başka bir script tarafından
# (örn. backtest.py) TELEGRAM_BOT_TOKEN olmadan da import edilebilsin.
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID_ENV = os.environ.get("TELEGRAM_CHAT_ID")  # önerilen: sabit chat id

STABLECOINS = {
    "USDT", "USDC", "FDUSD", "USDE",
    "TUSD", "DAI", "RLUSD", "USD1", "USDD"
}

MIN_QUOTE_VOLUME = 5_000_000     # 24h min hacim (USDT)
TOP_N_CANDIDATES = 100           # hacme göre ilk N coin
REQUEST_SLEEP = 0.12             # istekler arası bekleme (rate-limit koruması)
MAX_RETRIES = 3

LONG_SIGNAL_THRESHOLD = 70
SHORT_SIGNAL_THRESHOLD = 70

TOP_LONG = 3
TOP_SHORT = 3
TOP_PUMP = 5
TOP_DUMP = 5


# =========================================================
# HTTP (retry + backoff)
# =========================================================

def get(url):
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())

        except urllib.error.HTTPError as e:
            last_error = e
            # 429 / 418 = rate limit -> daha uzun bekle
            wait = 1.5 * (attempt + 1)
            if e.code in (429, 418):
                wait = 3 * (attempt + 1)
            time.sleep(wait)

        except Exception as e:
            last_error = e
            time.sleep(1 * (attempt + 1))

    raise RuntimeError(f"GET başarısız: {url} -> {last_error}")


# =========================================================
# TELEGRAM
# =========================================================

def get_chat_id():
    if CHAT_ID_ENV:
        return CHAT_ID_ENV

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
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN ayarlanmamış, mesaj gönderilemiyor.")
        return

    chat_id = get_chat_id()

    if not chat_id:
        print("Chat ID bulunamadı. TELEGRAM_CHAT_ID env değişkenini "
              "ayarlamanı öneririm, yoksa botunuza en az bir kez "
              "mesaj atılmış olmalı.")
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    # Telegram mesaj limiti ~4096 karakter -> gerekirse parçala
    chunks = [message[i:i + 3800] for i in range(0, len(message), 3800)] or [message]

    for chunk in chunks:
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": chunk
        }).encode()

        req = urllib.request.Request(url, data=data, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=20):
                print("Telegram mesajı gönderildi.")
        except Exception as e:
            print("Telegram gönderme hatası:", e)

        time.sleep(0.3)


# =========================================================
# BINANCE
# =========================================================

def get_klines(symbol, interval, limit=210):
    """
    Sadece TAMAMLANMIŞ (kapanmış) mumları döndürür.
    Binance'ın son elemanı çoğu zaman hâlâ oluşmakta olan mumdur;
    bunu analiz dışı bırakıyoruz ki sinyaller her çalıştırmada
    titremesin (flip-flop yapmasın).
    """
    params = urllib.parse.urlencode({
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    })

    url = BINANCE + "/api/v3/klines?" + params
    data = get(url)
    time.sleep(REQUEST_SLEEP)

    # Binance kline: [openTime, open, high, low, close, volume, closeTime, ...]
    now_ms = int(time.time() * 1000)
    closed = [row for row in data if row[6] <= now_ms]

    if len(closed) < 2:
        raise ValueError(f"{symbol} {interval}: yetersiz kapanmış mum")

    close = [float(x[4]) for x in closed]
    high = [float(x[2]) for x in closed]
    low = [float(x[3]) for x in closed]
    volume = [float(x[5]) for x in closed]

    return close, high, low, volume


# =========================================================
# ROLLING INDICATORS (O(n), tek geçiş)
# =========================================================

def ema_series(values, period):
    """EMA'nın tüm serisini döndürür (values[period-1:] ile hizalı)."""
    if len(values) < period:
        return []

    multiplier = 2 / (period + 1)
    series = []

    seed = sum(values[:period]) / period
    series.append(seed)

    prev = seed
    for value in values[period:]:
        prev = value * multiplier + prev * (1 - multiplier)
        series.append(prev)

    return series


def ema(values, period):
    series = ema_series(values, period)
    return series[-1] if series else (values[-1] if values else 0)


def rsi_series(values, period=14):
    """
    Wilder RSI serisini döndürür.
    Dönen liste values[period:] ile hizalıdır (her mum için bir RSI).
    """
    if len(values) <= period:
        return []

    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, 0) for c in changes]
    losses = [max(-c, 0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    series = []

    def to_rsi(ag, al):
        if al == 0:
            return 100.0
        rs = ag / al
        return 100 - (100 / (1 + rs))

    series.append(to_rsi(avg_gain, avg_loss))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        series.append(to_rsi(avg_gain, avg_loss))

    return series


def rsi(values, period=14):
    series = rsi_series(values, period)
    return series[-1] if series else 50.0


def stoch_rsi(values, period=14):
    r_series = rsi_series(values, period)

    if len(r_series) < period:
        return 50.0

    recent = r_series[-period:]
    lowest = min(recent)
    highest = max(recent)

    if highest == lowest:
        return 50.0

    return (r_series[-1] - lowest) / (highest - lowest) * 100


def macd(values, fast=12, slow=26, signal_period=9):
    if len(values) < slow + signal_period:
        return 0.0, 0.0, 0.0

    ema_fast = ema_series(values, fast)
    ema_slow = ema_series(values, slow)

    # ema_fast, ema_slow farklı uzunlukta -> sondan hizala
    offset = len(ema_fast) - len(ema_slow)
    macd_line_series = [
        ema_fast[offset + i] - ema_slow[i]
        for i in range(len(ema_slow))
    ]

    if len(macd_line_series) < signal_period:
        return macd_line_series[-1], 0.0, macd_line_series[-1]

    signal_series = ema_series(macd_line_series, signal_period)
    line = macd_line_series[-1]
    sig = signal_series[-1]

    return line, sig, line - sig


def bollinger(values, period=20):
    recent = values[-period:]
    middle = sum(recent) / len(recent)
    variance = sum((x - middle) ** 2 for x in recent) / len(recent)
    std = math.sqrt(variance)

    return middle + 2 * std, middle, middle - 2 * std


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


def true_range_series(high, low, close):
    trs = []
    for i in range(1, len(close)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
        trs.append(tr)
    return trs


def atr(high, low, close, period=14):
    """Wilder ATR (son değer)."""
    trs = true_range_series(high, low, close)
    if len(trs) < period:
        return 0.0

    avg = sum(trs[:period]) / period
    for tr in trs[period:]:
        avg = (avg * (period - 1) + tr) / period

    return avg


def atr_series(high, low, close, period=14):
    trs = true_range_series(high, low, close)
    if len(trs) < period:
        return []

    series = [sum(trs[:period]) / period]
    prev = series[0]
    for tr in trs[period:]:
        prev = (prev * (period - 1) + tr) / period
        series.append(prev)

    return series


# =========================================================
# ADX / DI (Wilder standardı)
# =========================================================

def adx_di(high, low, close, period=14):
    n = len(close)
    if n < period * 2 + 1:
        return 0.0, 0.0, 0.0

    plus_dm = [0.0]
    minus_dm = [0.0]
    tr_list = [0.0]

    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]

        plus_dm.append(up_move if (up_move > down_move and up_move > 0) else 0.0)
        minus_dm.append(down_move if (down_move > up_move and down_move > 0) else 0.0)

        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
        tr_list.append(tr)

    # Wilder smoothing (ilk period'u topla, sonra smooth et)
    def wilder_smooth(values, period):
        smoothed = [sum(values[1:period + 1])]
        for i in range(period + 1, len(values)):
            smoothed.append(smoothed[-1] - (smoothed[-1] / period) + values[i])
        return smoothed

    tr_smooth = wilder_smooth(tr_list, period)
    plus_dm_smooth = wilder_smooth(plus_dm, period)
    minus_dm_smooth = wilder_smooth(minus_dm, period)

    plus_di_series = []
    minus_di_series = []
    dx_series = []

    for i in range(len(tr_smooth)):
        if tr_smooth[i] == 0:
            plus_di_series.append(0.0)
            minus_di_series.append(0.0)
            dx_series.append(0.0)
            continue

        pdi = 100 * plus_dm_smooth[i] / tr_smooth[i]
        mdi = 100 * minus_dm_smooth[i] / tr_smooth[i]

        plus_di_series.append(pdi)
        minus_di_series.append(mdi)

        denom = pdi + mdi
        dx = (abs(pdi - mdi) / denom * 100) if denom != 0 else 0.0
        dx_series.append(dx)

    if len(dx_series) < period:
        return 0.0, plus_di_series[-1] if plus_di_series else 0.0, \
               minus_di_series[-1] if minus_di_series else 0.0

    adx_first = sum(dx_series[:period]) / period
    adx_value = adx_first
    for dx in dx_series[period:]:
        adx_value = (adx_value * (period - 1) + dx) / period

    return adx_value, plus_di_series[-1], minus_di_series[-1]


# =========================================================
# VWAP
# =========================================================

def vwap(high, low, close, volume, period=50):
    start = max(0, len(close) - period)

    cum_pv = 0.0
    cum_v = 0.0

    for i in range(start, len(close)):
        typical_price = (high[i] + low[i] + close[i]) / 3
        cum_pv += typical_price * volume[i]
        cum_v += volume[i]

    return cum_pv / cum_v if cum_v > 0 else close[-1]


# =========================================================
# SUPERTREND (basit, tek yönlü kontrol için)
# =========================================================

def supertrend_bullish(high, low, close, period=10, multiplier=3):
    if len(close) < period + 2:
        return None

    atr_value = atr(high, low, close, period)
    if atr_value <= 0:
        return None

    hl2 = (high[-1] + low[-1]) / 2
    upper_band = hl2 + multiplier * atr_value
    lower_band = hl2 - multiplier * atr_value

    if close[-1] > upper_band:
        return True
    if close[-1] < lower_band:
        return False
    return None  # net bir yön yok


# =========================================================
# MOMENTUM
# =========================================================

def momentum_data(close):
    if len(close) < 20:
        return {"momentum": 0, "previous_momentum": 0, "acceleration": 0,
                "short_momentum": 0, "medium_momentum": 0}

    current = (close[-1] / close[-5] - 1) * 100
    previous = (close[-5] / close[-9] - 1) * 100
    short_momentum = (close[-1] / close[-3] - 1) * 100
    medium_momentum = (close[-1] / close[-10] - 1) * 100
    acceleration = current - previous

    return {
        "momentum": current,
        "previous_momentum": previous,
        "acceleration": acceleration,
        "short_momentum": short_momentum,
        "medium_momentum": medium_momentum
    }


def bollinger_width(close):
    upper, middle, lower = bollinger(close)
    if middle == 0:
        return 0
    return (upper - lower) / middle * 100


# =========================================================
# FRESH BREAKOUT
# =========================================================

def fresh_breakout(close, high, low, volume):
    if len(close) < 35:
        return None

    current = close[-1]
    resistance = max(high[-21:-1])
    support = min(low[-21:-1])
    avg_volume = sum(volume[-21:-1]) / 20

    if avg_volume <= 0:
        return None

    volume_ratio = volume[-1] / avg_volume

    if current > resistance and volume_ratio >= 1.5:
        return {"direction": "LONG", "level": resistance, "volume_ratio": volume_ratio}

    if current < support and volume_ratio >= 1.5:
        return {"direction": "SHORT", "level": support, "volume_ratio": volume_ratio}

    return None


# =========================================================
# OVEREXTENSION
# =========================================================

def overextension(close, atr_value, ema21, bollinger_upper, bollinger_lower):
    price = close[-1]

    if atr_value <= 0:
        return {"long": False, "short": False, "distance": 0}

    long_distance = (price - ema21) / atr_value
    short_distance = (ema21 - price) / atr_value

    long_over = long_distance >= 3 or price > bollinger_upper
    short_over = short_distance >= 3 or price < bollinger_lower

    return {
        "long": long_over,
        "short": short_over,
        "distance": max(long_distance, short_distance)
    }


# =========================================================
# PUMP / DUMP RADAR
# =========================================================

def pump_dump_radar(close, high, low, volume, adx_value, plus_di, minus_di, ema21):
    if len(close) < 40:
        return None

    price = close[-1]
    momentum_info = momentum_data(close)

    momentum = momentum_info["momentum"]
    previous_momentum = momentum_info["previous_momentum"]
    momentum_acceleration = momentum_info["acceleration"]

    avg_volume = sum(volume[-21:-1]) / 20
    if avg_volume <= 0:
        return None

    volume_ratio = volume[-1] / avg_volume
    previous_avg = sum(volume[-11:-1]) / 10
    volume_acceleration = volume[-1] / previous_avg if previous_avg > 0 else 1

    stoch = stoch_rsi(close)
    upper, middle, lower = bollinger(close)
    bb_width = bollinger_width(close)
    distance_from_ema = (price - ema21) / ema21 * 100

    # ---------------- PUMP ----------------
    pump_score = 0

    if momentum >= 5: pump_score += 20
    elif momentum >= 3: pump_score += 15
    elif momentum >= 2: pump_score += 10
    elif momentum >= 1: pump_score += 5

    if momentum_acceleration >= 3: pump_score += 20
    elif momentum_acceleration >= 2: pump_score += 15
    elif momentum_acceleration >= 1: pump_score += 10
    elif momentum_acceleration > 0: pump_score += 5

    if volume_ratio >= 5: pump_score += 20
    elif volume_ratio >= 3: pump_score += 15
    elif volume_ratio >= 2: pump_score += 10
    elif volume_ratio >= 1.5: pump_score += 5

    if volume_acceleration >= 5: pump_score += 15
    elif volume_acceleration >= 3: pump_score += 12
    elif volume_acceleration >= 2: pump_score += 8

    if adx_value >= 45: pump_score += 10
    elif adx_value >= 30: pump_score += 7
    elif adx_value >= 25: pump_score += 4

    if plus_di > minus_di: pump_score += 5
    if bb_width >= 8: pump_score += 5

    overextended = distance_from_ema >= 8 or price > upper
    if overextended:
        pump_score -= 15

    losing_momentum = momentum >= 3 and momentum_acceleration < 0
    if losing_momentum:
        pump_score -= 15

    breakout = fresh_breakout(close, high, low, volume)
    fresh = breakout is not None and breakout["direction"] == "LONG"
    if fresh:
        pump_score += 10

    pump_score = max(0, min(100, pump_score))

    if pump_score >= 60:
        if overextended:
            status = "🔴 PUMP VAR AMA AŞIRI UZAMIŞ"
        elif losing_momentum:
            status = "🟡 PUMP VAR AMA HIZ KESİYOR"
        elif fresh and momentum_acceleration > 0:
            status = "🟢 ERKEN PUMP GİRİŞİ"
        elif momentum_acceleration >= 1:
            status = "🟢 PUMP HIZLANIYOR"
        else:
            status = "⚡ HAREKETLENİYOR"

        return {
            "type": "PUMP", "score": pump_score, "status": status,
            "momentum": momentum, "previous_momentum": previous_momentum,
            "momentum_acceleration": momentum_acceleration,
            "volume": volume_ratio, "acceleration": volume_acceleration,
            "adx": adx_value, "stoch": stoch, "bb_width": bb_width,
            "overextended": overextended, "fresh_breakout": fresh,
            "distance_ema": distance_from_ema
        }

    # ---------------- DUMP ----------------
    dump_score = 0

    if momentum <= -5: dump_score += 20
    elif momentum <= -3: dump_score += 15
    elif momentum <= -2: dump_score += 10
    elif momentum <= -1: dump_score += 5

    if momentum_acceleration <= -3: dump_score += 20
    elif momentum_acceleration <= -2: dump_score += 15
    elif momentum_acceleration <= -1: dump_score += 10
    elif momentum_acceleration < 0: dump_score += 5

    if volume_ratio >= 5: dump_score += 20
    elif volume_ratio >= 3: dump_score += 15
    elif volume_ratio >= 2: dump_score += 10
    elif volume_ratio >= 1.5: dump_score += 5

    if volume_acceleration >= 5: dump_score += 15
    elif volume_acceleration >= 3: dump_score += 12
    elif volume_acceleration >= 2: dump_score += 8

    if adx_value >= 45: dump_score += 10
    elif adx_value >= 30: dump_score += 7
    elif adx_value >= 25: dump_score += 4

    if minus_di > plus_di: dump_score += 5

    short_overextended = distance_from_ema <= -8 or price < lower
    losing_down_momentum = momentum <= -3 and momentum_acceleration > 0

    if short_overextended:
        dump_score -= 15
    if losing_down_momentum:
        dump_score -= 15

    fresh_dump = breakout is not None and breakout["direction"] == "SHORT"
    if fresh_dump:
        dump_score += 10

    dump_score = max(0, min(100, dump_score))

    if dump_score >= 60:
        if short_overextended:
            status = "🔴 DUMP VAR AMA AŞIRI UZAMIŞ"
        elif losing_down_momentum:
            status = "🟡 DUMP VAR AMA HIZ KESİYOR"
        elif fresh_dump and momentum_acceleration < 0:
            status = "🔴 ERKEN DUMP GİRİŞİ"
        elif momentum_acceleration <= -1:
            status = "🔴 DUMP HIZLANIYOR"
        else:
            status = "⚡ DÜŞÜŞ HIZLANIYOR"

        return {
            "type": "DUMP", "score": dump_score, "status": status,
            "momentum": momentum, "previous_momentum": previous_momentum,
            "momentum_acceleration": momentum_acceleration,
            "volume": volume_ratio, "acceleration": volume_acceleration,
            "adx": adx_value, "stoch": stoch, "bb_width": bb_width,
            "overextended": short_overextended, "fresh_breakout": fresh_dump,
            "distance_ema": distance_from_ema
        }

    return None


# =========================================================
# FORMAT / HELPERS
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


# =========================================================
# ANALYSIS
# =========================================================

def analyze(symbol):
    """
    Canlı analiz: Binance'tan veri çeker, analyze_core'a devreder.
    """
    try:
        close15, high15, low15, vol15 = get_klines(symbol, "15m")
        close1h, high1h, low1h, vol1h = get_klines(symbol, "1h")
        close4h, high4h, low4h, vol4h = get_klines(symbol, "4h")

        if len(close15) < 60 or len(close1h) < 60 or len(close4h) < 60:
            return None

        return analyze_core(
            symbol, close15, high15, low15, vol15, close1h, close4h
        )

    except Exception as e:
        print(f"{symbol} analiz hatası: {e}")
        return None


def analyze_core(symbol, close15, high15, low15, vol15, close1h, close4h):
    """
    Saf hesaplama fonksiyonu — ağ çağrısı yapmaz.
    Canlı tarama (analyze) ve backtest (backtest.py) bu fonksiyonu
    ortak kullanır; sinyal mantığı tek bir yerden yönetilir.

    close1h / close4h: sadece kapanış fiyatı serisi yeterli
    (rsi/macd/ema hesapları sadece close kullanıyor).
    """
    try:
        if len(close15) < 60 or len(close1h) < 35 or len(close4h) < 55:
            return None

        # Kapanmış son mumun kapanışı = karar fiyatı (whipsaw'ı azaltır)
        price = close15[-1]

        rsi15 = rsi(close15)
        rsi1h = rsi(close1h)
        rsi4h = rsi(close4h)

        ema9 = ema(close15, 9)
        ema21 = ema(close15, 21)
        ema50 = ema(close15, 50)

        ema21_4h = ema(close4h, 21)
        ema50_4h = ema(close4h, 50)

        macd15, signal15, hist15 = macd(close15)
        macd1h, signal1h, hist1h = macd(close1h)

        stoch = stoch_rsi(close15)
        upper, middle, lower = bollinger(close15)

        obv_values = obv(close15, vol15)
        obv_positive = len(obv_values) >= 6 and obv_values[-1] > obv_values[-5]

        atr_value = atr(high15, low15, close15)
        adx_value, plus_di, minus_di = adx_di(high15, low15, close15)
        current_vwap = vwap(high15, low15, close15, vol15)
        st_bullish = supertrend_bullish(high15, low15, close15)

        avg_volume = sum(vol15[-21:-1]) / 20
        if avg_volume <= 0:
            return None

        volume_ratio = vol15[-1] / avg_volume
        previous_avg = sum(vol15[-11:-1]) / 10
        volume_acceleration = vol15[-1] / previous_avg if previous_avg > 0 else 1

        momentum_info = momentum_data(close15)
        momentum = momentum_info["momentum"]
        momentum_acceleration = momentum_info["acceleration"]

        # -------------------- LONG --------------------
        long_score = 0
        long_reasons = []

        if 50 <= rsi15 <= 68:
            long_score += 8; long_reasons.append("RSI ideal")
        if 50 <= rsi1h <= 70:
            long_score += 8; long_reasons.append("1h RSI")
        if 45 <= rsi4h <= 70:
            long_score += 7; long_reasons.append("4h RSI")
        if price > ema9 > ema21:
            long_score += 10; long_reasons.append("15m EMA uptrend")
        if price > ema50:
            long_score += 6; long_reasons.append("EMA50")
        if price > ema21_4h and ema21_4h > ema50_4h:
            long_score += 10; long_reasons.append("4h trend")
        if macd1h > signal1h:
            long_score += 8; long_reasons.append("1h MACD")
        if 20 <= stoch <= 80:
            long_score += 6; long_reasons.append("Stoch RSI")
        if middle < price < upper:
            long_score += 4; long_reasons.append("Bollinger")
        if obv_positive:
            long_score += 5; long_reasons.append("OBV")
        if price > current_vwap:
            long_score += 6; long_reasons.append("VWAP")
        if adx_value >= 25 and plus_di > minus_di:
            long_score += 8; long_reasons.append("ADX/DI")
        if st_bullish is True:
            long_score += 6; long_reasons.append("Supertrend")

        if volume_ratio >= 3: long_score += 10
        elif volume_ratio >= 2: long_score += 7
        elif volume_ratio >= 1.5: long_score += 4

        if volume_acceleration >= 3:
            long_score += 6; long_reasons.append("Volume Acceleration")
        if 0.5 <= momentum <= 5:
            long_score += 7; long_reasons.append("Momentum")
        if momentum_acceleration >= 1:
            long_score += 5; long_reasons.append("Momentum Acceleration")

        # -------------------- SHORT --------------------
        short_score = 0
        short_reasons = []

        if 32 <= rsi15 <= 50:
            short_score += 8; short_reasons.append("RSI weakness")
        if 30 <= rsi1h <= 50:
            short_score += 8; short_reasons.append("1h RSI")
        if 30 <= rsi4h <= 55:
            short_score += 7; short_reasons.append("4h RSI")
        if price < ema9 < ema21:
            short_score += 10; short_reasons.append("15m EMA downtrend")
        if price < ema50:
            short_score += 6; short_reasons.append("EMA50")
        if price < ema21_4h and ema21_4h < ema50_4h:
            short_score += 10; short_reasons.append("4h downtrend")
        if macd1h < signal1h:
            short_score += 8; short_reasons.append("1h MACD")
        if stoch < 80:
            short_score += 5; short_reasons.append("Stoch RSI")
        if lower < price < middle:
            short_score += 4; short_reasons.append("Bollinger")
        if not obv_positive:
            short_score += 5; short_reasons.append("OBV")
        if price < current_vwap:
            short_score += 6; short_reasons.append("VWAP")
        if adx_value >= 25 and minus_di > plus_di:
            short_score += 8; short_reasons.append("ADX/DI")
        if st_bullish is False:
            short_score += 6; short_reasons.append("Supertrend")

        if volume_ratio >= 3: short_score += 10
        elif volume_ratio >= 2: short_score += 7
        elif volume_ratio >= 1.5: short_score += 4

        if volume_acceleration >= 3:
            short_score += 6; short_reasons.append("Volume Acceleration")
        if -5 <= momentum <= -0.5:
            short_score += 7; short_reasons.append("Momentum")
        if momentum_acceleration <= -1:
            short_score += 5; short_reasons.append("Momentum Acceleration")

        # -------------------- FILTERS --------------------
        if volume_ratio < 1.3:
            long_score -= 15; short_score -= 15
        if adx_value < 18:
            long_score -= 8; short_score -= 8
        if stoch > 92:
            long_score -= 10
        if stoch < 8:
            short_score -= 10

        extension = overextension(close15, atr_value, ema21, upper, lower)
        if extension["long"]:
            long_score -= 20
        if extension["short"]:
            short_score -= 20

        long_score = max(0, min(100, long_score))
        short_score = max(0, min(100, short_score))

        radar = pump_dump_radar(
            close15, high15, low15, vol15,
            adx_value, plus_di, minus_di, ema21
        )

        # -------------------- SIGNALS --------------------
        long_signal = None
        short_signal = None

        if (
            long_score >= LONG_SIGNAL_THRESHOLD
            and volume_ratio >= 1.5
            and adx_value >= 20
            and plus_di > minus_di
            and price > current_vwap
            and momentum > 0
            and momentum_acceleration >= 0
            and not extension["long"]
        ):
            long_signal = "🟢 GÜÇLÜ AL"

        if (
            short_score >= SHORT_SIGNAL_THRESHOLD
            and volume_ratio >= 1.5
            and adx_value >= 20
            and minus_di > plus_di
            and price < current_vwap
            and momentum < 0
            and momentum_acceleration <= 0
            and not extension["short"]
        ):
            short_signal = "🔴 GÜÇLÜ SAT"

        if atr_value <= 0:
            return None

        risk = atr_value * 1.5

        long_sl = price - risk
        long_tp1 = price + risk
        long_tp2 = price + risk * 1.5
        long_tp3 = price + risk * 2

        short_sl = price + risk
        short_tp1 = price - risk
        short_tp2 = price - risk * 1.5
        short_tp3 = price - risk * 2

        return {
            "symbol": symbol, "price": price,
            "long_score": long_score, "short_score": short_score,
            "long_signal": long_signal, "short_signal": short_signal,
            "long_reasons": long_reasons, "short_reasons": short_reasons,
            "rsi15": rsi15, "rsi1h": rsi1h, "rsi4h": rsi4h,
            "stoch": stoch,
            "volume": volume_ratio, "volume_acceleration": volume_acceleration,
            "momentum": momentum,
            "previous_momentum": momentum_info["previous_momentum"],
            "momentum_acceleration": momentum_acceleration,
            "adx": adx_value, "plus_di": plus_di, "minus_di": minus_di,
            "vwap": current_vwap, "radar": radar, "extension": extension,
            "long_sl": long_sl, "long_tp1": long_tp1,
            "long_tp2": long_tp2, "long_tp3": long_tp3,
            "short_sl": short_sl, "short_tp1": short_tp1,
            "short_tp2": short_tp2, "short_tp3": short_tp3
        }

    except Exception as e:
        print(f"{symbol} analiz hatası: {e}")
        return None


# =========================================================
# MAIN
# =========================================================

def get_candidates():
    tickers = get(BINANCE + "/api/v3/ticker/24hr")

    candidates = []
    for ticker in tickers:
        symbol = ticker["symbol"]

        if not symbol.endswith("USDT"):
            continue
        if stablecoin_pair(symbol):
            continue
        if any(x in symbol for x in ["UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"]):
            continue

        try:
            quote_volume = float(ticker["quoteVolume"])
            if quote_volume < MIN_QUOTE_VOLUME:
                continue
            candidates.append((symbol, quote_volume))
        except Exception:
            continue

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:TOP_N_CANDIDATES]


def build_message(results):
    longs = sorted(
        [x for x in results if x["long_signal"] == "🟢 GÜÇLÜ AL"],
        key=lambda x: x["long_score"], reverse=True
    )[:TOP_LONG]

    shorts = sorted(
        [x for x in results if x["short_signal"] == "🔴 GÜÇLÜ SAT"],
        key=lambda x: x["short_score"], reverse=True
    )[:TOP_SHORT]

    pumps = sorted(
        [x for x in results if x["radar"] and x["radar"]["type"] == "PUMP"],
        key=lambda x: x["radar"]["score"], reverse=True
    )[:TOP_PUMP]

    dumps = sorted(
        [x for x in results if x["radar"] and x["radar"]["type"] == "DUMP"],
        key=lambda x: x["radar"]["score"], reverse=True
    )[:TOP_DUMP]

    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    message = (
        "🚨 GELİŞMİŞ BINANCE LONG + SHORT TARAMASI\n\n"
        f"🕐 {now}\n"
        "📊 15m + 1h + 4h (sadece kapanmış mumlar)\n"
        "🧠 RSI • Stoch RSI • MACD • EMA\n"
        "📈 BB • OBV • Supertrend\n"
        "📐 Wilder ADX • DI • VWAP\n"
        "🔥 Volume Acceleration\n"
        "🚀 Momentum Acceleration\n"
        "💥 Fresh Breakout\n"
        "🛡️ Overextension Filter\n"
        "🎯 ATR + GERÇEK R/R\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )

    message += "📈 LONG FIRSATLARI\n\n"
    if not longs:
        message += "🟡 Şu anda trade edilebilir GÜÇLÜ LONG sinyali yok.\n\n"
    else:
        for i, coin in enumerate(longs, 1):
            message += (
                f"🏆 {i}. {coin['symbol']}\n"
                f"{coin['long_signal']}\n"
                f"⭐ Sinyal: {coin['long_score']}/100\n\n"
                f"💰 Giriş: {price_format(coin['price'])}\n"
                f"RSI: {coin['rsi15']:.1f} | 1h: {coin['rsi1h']:.1f} | 4h: {coin['rsi4h']:.1f}\n"
                f"🔥 Hacim: x{coin['volume']:.1f}\n"
                f"⚡ Hacim ivmesi: x{coin['volume_acceleration']:.1f}\n"
                f"🚀 Momentum: {coin['momentum']:+.1f}%\n"
                f"⚡ Momentum ivmesi: {coin['momentum_acceleration']:+.1f} puan\n"
                f"📐 ADX: {coin['adx']:.1f}\n"
                f"📍 VWAP: {price_format(coin['vwap'])}\n"
            )
            if coin["long_reasons"]:
                message += "🧠 Teyitler: " + ", ".join(coin["long_reasons"][:10]) + "\n"
            message += (
                f"\n🛑 SL: {price_format(coin['long_sl'])}\n"
                f"🎯 TP1: {price_format(coin['long_tp1'])}\n"
                f"🎯 TP2: {price_format(coin['long_tp2'])}\n"
                f"🎯 TP3: {price_format(coin['long_tp3'])}\n"
                "📐 R/R: 1 : 2\n\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    message += "📉 SHORT FIRSATLARI\n\n"
    if not shorts:
        message += "🟡 Şu anda trade edilebilir GÜÇLÜ SHORT sinyali yok.\n\n"
    else:
        for i, coin in enumerate(shorts, 1):
            message += (
                f"🏆 {i}. {coin['symbol']}\n"
                f"{coin['short_signal']}\n"
                f"⭐ Sinyal: {coin['short_score']}/100\n\n"
                f"💰 Giriş: {price_format(coin['price'])}\n"
                f"RSI: {coin['rsi15']:.1f} | 1h: {coin['rsi1h']:.1f} | 4h: {coin['rsi4h']:.1f}\n"
                f"🔥 Hacim: x{coin['volume']:.1f}\n"
                f"⚡ Hacim ivmesi: x{coin['volume_acceleration']:.1f}\n"
                f"📉 Momentum: {coin['momentum']:+.1f}%\n"
                f"⚡ Momentum ivmesi: {coin['momentum_acceleration']:+.1f} puan\n"
                f"📐 ADX: {coin['adx']:.1f}\n"
                f"📍 VWAP: {price_format(coin['vwap'])}\n"
            )
            if coin["short_reasons"]:
                message += "🧠 Teyitler: " + ", ".join(coin["short_reasons"][:10]) + "\n"
            message += (
                f"\n🛑 SL: {price_format(coin['short_sl'])}\n"
                f"🎯 TP1: {price_format(coin['short_tp1'])}\n"
                f"🎯 TP2: {price_format(coin['short_tp2'])}\n"
                f"🎯 TP3: {price_format(coin['short_tp3'])}\n"
                "📐 R/R: 1 : 2\n\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
            )

    message += "🚀 PUMP RADAR\n\n"
    if not pumps:
        message += "🟡 Şu anda güçlü pump hareketi yok.\n\n"
    else:
        for i, coin in enumerate(pumps, 1):
            radar = coin["radar"]
            message += (
                f"🚀 {i}. {coin['symbol']}\n"
                f"{radar['status']}\n"
                f"⭐ Pump gücü: {radar['score']}/100\n\n"
                f"💰 Fiyat: {price_format(coin['price'])}\n"
                f"🔥 Hacim: x{radar['volume']:.1f}\n"
                f"⚡ Hacim ivmesi: x{radar['acceleration']:.1f}\n"
                f"🚀 Momentum: {radar['momentum']:+.1f}%\n"
                f"⚡ Momentum ivmesi: {radar['momentum_acceleration']:+.1f} puan\n"
                f"📐 ADX: {radar['adx']:.1f}\n"
                f"📊 Stoch RSI: {radar['stoch']:.1f}\n"
            )
            if radar["fresh_breakout"]:
                message += "💥 FRESH BREAKOUT: EVET\n"
            if radar["overextended"]:
                message += "🛡️ OVEREXTENSION: EVET\n"
            message += "\n"

    message += "💣 DUMP RADAR\n\n"
    if not dumps:
        message += "🟡 Şu anda güçlü dump hareketi yok.\n\n"
    else:
        for i, coin in enumerate(dumps, 1):
            radar = coin["radar"]
            message += (
                f"💣 {i}. {coin['symbol']}\n"
                f"{radar['status']}\n"
                f"⭐ Dump gücü: {radar['score']}/100\n\n"
                f"💰 Fiyat: {price_format(coin['price'])}\n"
                f"🔥 Hacim: x{radar['volume']:.1f}\n"
                f"⚡ Hacim ivmesi: x{radar['acceleration']:.1f}\n"
                f"📉 Momentum: {radar['momentum']:+.1f}%\n"
                f"⚡ Momentum ivmesi: {radar['momentum_acceleration']:+.1f} puan\n"
                f"📐 ADX: {radar['adx']:.1f}\n"
                f"📊 Stoch RSI: {radar['stoch']:.1f}\n"
            )
            if radar["fresh_breakout"]:
                message += "💥 FRESH BREAKDOWN: EVET\n"
            if radar["overextended"]:
                message += "🛡️ OVEREXTENSION: EVET\n"
            message += "\n"

    message += (
        "━━━━━━━━━━━━━━━━━━\n"
        "🧠 Momentum + momentum ivmesi + hacim + breakout + trend + risk filtresi\n"
        "⚠️ Teknik sinyal sistemidir. Yatırım tavsiyesi değildir."
    )

    return message


def scan_main():
    """Normal tarama: Binance'ı tarar, Telegram'a sinyal mesajı atar."""
    print("🚀 GELİŞMİŞ BINANCE LONG + SHORT SCANNER (v2)")

    candidates = get_candidates()
    print(f"{len(candidates)} coin analiz edilecek.")

    results = []
    for idx, (symbol, _) in enumerate(candidates, 1):
        print(f"[{idx}/{len(candidates)}] Analiz: {symbol}")
        result = analyze(symbol)
        if result:
            results.append(result)

    message = build_message(results)
    print(message)
    send_telegram(message)


# =========================================================
# BACKTEST (geçmiş veriyle sinyal sisteminin başarısını ölçer)
# =========================================================

BT_LOOKAHEAD_CANDLES = 96      # sinyal sonrası en fazla kaç 15m mum bekleyelim (96 = 24 saat)
BT_COOLDOWN_CANDLES = 8         # aynı coin için bir sinyalden sonra kaç mum boyunca yeni sinyal aranmasın
BT_TRAIL_WINDOW = 1100           # her adımda sadece son N adet 15m mumu kullan (performans için)
BT_MIN_WARMUP_15M = 960           # backtest'e başlamadan önce gereken minimum 15m mum sayısı (~10 gün)


def bt_fetch_full_klines(symbol, interval, days):
    """
    Belirtilen gün sayısı kadar geçmişe giderek TÜM kapanmış mumları
    sayfalama yaparak çeker (Binance tek istekte en fazla 1000 mum verir).
    """
    end_time = int(time.time() * 1000)
    start_time = end_time - days * 24 * 60 * 60 * 1000

    all_rows = []
    cursor = start_time

    while cursor < end_time:
        params = urllib.parse.urlencode({
            "symbol": symbol,
            "interval": interval,
            "startTime": cursor,
            "limit": 1000
        })
        url = BINANCE + "/api/v3/klines?" + params
        data = get(url)
        time.sleep(REQUEST_SLEEP)

        if not data:
            break

        all_rows.extend(data)
        last_close_time = data[-1][6]

        if last_close_time <= cursor:
            break

        cursor = last_close_time + 1

        if len(data) < 1000:
            break

    now_ms = int(time.time() * 1000)
    all_rows = [r for r in all_rows if r[6] <= now_ms]

    close = [float(x[4]) for x in all_rows]
    high = [float(x[2]) for x in all_rows]
    low = [float(x[3]) for x in all_rows]
    volume = [float(x[5]) for x in all_rows]

    return close, high, low, volume


def bt_simulate_outcome(direction, entry_price, sl, tp1, tp2, tp3,
                         future_high, future_low):
    """
    Sinyal sonrası mumlarda SL/TP seviyelerinden hangisi önce vuruldu,
    onu bulur. Aynı mumda hem SL hem TP tetiklenirse (yüksek volatilite),
    ihtiyatlı olmak için SL'nin önce vurulduğunu varsayıyoruz.
    """
    for h, l in zip(future_high, future_low):
        if direction == "LONG":
            sl_hit = l <= sl
            tp3_hit = h >= tp3
            tp2_hit = h >= tp2
            tp1_hit = h >= tp1
        else:
            sl_hit = h >= sl
            tp3_hit = l <= tp3
            tp2_hit = l <= tp2
            tp1_hit = l <= tp1

        if sl_hit:
            return "SL", -1.0
        if tp3_hit:
            return "TP3", 2.0
        if tp2_hit:
            return "TP2", 1.5
        if tp1_hit:
            return "TP1", 1.0

    return "TIMEOUT", 0.0


def bt_backtest_symbol(symbol, days):
    print(f"\n📥 {symbol}: geçmiş veri çekiliyor ({days} gün)...")

    close15, high15, low15, vol15 = bt_fetch_full_klines(symbol, "15m", days)

    if len(close15) < BT_MIN_WARMUP_15M + BT_LOOKAHEAD_CANDLES:
        print(f"⚠️ {symbol}: yeterli veri yok, atlanıyor ({len(close15)} mum).")
        return []

    print(f"✅ {symbol}: {len(close15)} adet 15m mum indirildi.")

    full_close1h = close15[3::4]
    full_close4h = close15[15::16]

    trades = []
    last_signal_index = -BT_COOLDOWN_CANDLES - 1

    total_steps = len(close15) - BT_LOOKAHEAD_CANDLES
    for i in range(BT_MIN_WARMUP_15M, total_steps):

        if i - last_signal_index < BT_COOLDOWN_CANDLES:
            continue

        window_start = max(0, i - BT_TRAIL_WINDOW + 1)

        w_close15 = close15[window_start:i + 1]
        w_high15 = high15[window_start:i + 1]
        w_low15 = low15[window_start:i + 1]
        w_vol15 = vol15[window_start:i + 1]

        n1h = (i + 1) // 4
        n4h = (i + 1) // 16

        w_close1h = full_close1h[:n1h]
        w_close4h = full_close4h[:n4h]

        result = analyze_core(
            symbol, w_close15, w_high15, w_low15, w_vol15,
            w_close1h, w_close4h
        )

        if not result:
            continue

        direction = None
        if result["long_signal"]:
            direction = "LONG"
            sl, tp1, tp2, tp3 = (
                result["long_sl"], result["long_tp1"],
                result["long_tp2"], result["long_tp3"]
            )
            score = result["long_score"]
            reasons = result["long_reasons"]
        elif result["short_signal"]:
            direction = "SHORT"
            sl, tp1, tp2, tp3 = (
                result["short_sl"], result["short_tp1"],
                result["short_tp2"], result["short_tp3"]
            )
            score = result["short_score"]
            reasons = result["short_reasons"]
        else:
            continue

        future_high = high15[i + 1: i + 1 + BT_LOOKAHEAD_CANDLES]
        future_low = low15[i + 1: i + 1 + BT_LOOKAHEAD_CANDLES]

        outcome, r_multiple = bt_simulate_outcome(
            direction, result["price"], sl, tp1, tp2, tp3,
            future_high, future_low
        )

        trades.append({
            "symbol": symbol,
            "direction": direction,
            "index": i,
            "score": score,
            "entry": result["price"],
            "outcome": outcome,
            "r": r_multiple,
            "reasons": "|".join(reasons)
        })

        last_signal_index = i

    print(f"📊 {symbol}: {len(trades)} sinyal bulundu.")
    return trades


def bt_print_summary(all_trades):
    if not all_trades:
        print("\n⚠️ Hiç sinyal üretilmedi. Eşikler çok katı olabilir "
              "(LONG_SIGNAL_THRESHOLD / SHORT_SIGNAL_THRESHOLD) ya da "
              "test edilen dönemde uygun koşul oluşmamış olabilir.")
        return

    total = len(all_trades)
    wins = [t for t in all_trades if t["r"] > 0]
    losses = [t for t in all_trades if t["r"] < 0]
    timeouts = [t for t in all_trades if t["r"] == 0]

    win_rate = len(wins) / total * 100
    avg_r = sum(t["r"] for t in all_trades) / total

    print("\n" + "=" * 50)
    print("📈 GENEL SONUÇ")
    print("=" * 50)
    print(f"Toplam sinyal      : {total}")
    print(f"Kazanan (TP)        : {len(wins)}")
    print(f"Kaybeden (SL)        : {len(losses)}")
    print(f"Zaman aşımı (TP/SL'ye ulaşmadı): {len(timeouts)}")
    print(f"Kazanma oranı        : {win_rate:.1f}%")
    print(f"Ortalama R (risk katı): {avg_r:+.2f}")

    for direction in ("LONG", "SHORT"):
        subset = [t for t in all_trades if t["direction"] == direction]
        if not subset:
            continue
        sub_wins = [t for t in subset if t["r"] > 0]
        sub_avg_r = sum(t["r"] for t in subset) / len(subset)
        print(f"\n{direction}: {len(subset)} sinyal, "
              f"kazanma oranı {len(sub_wins) / len(subset) * 100:.1f}%, "
              f"ortalama R {sub_avg_r:+.2f}")

    # ---------------------------------------------------------
    # SKORA GÖRE KIRILIM — eşik yükseltmenin işe yarayıp
    # yaramayacağını görmek için: skor arttıkça performans da
    # artıyor mu?
    # ---------------------------------------------------------
    print("\n" + "-" * 50)
    print("📊 SKOR ARALIĞINA GÖRE PERFORMANS")
    print("-" * 50)

    buckets = [(70, 79), (80, 89), (90, 100)]

    for direction in ("LONG", "SHORT"):
        print(f"\n{direction}:")
        subset = [t for t in all_trades if t["direction"] == direction]

        for lo, hi in buckets:
            bucket = [t for t in subset if lo <= t["score"] <= hi]
            if not bucket:
                print(f"  Skor {lo}-{hi}: sinyal yok")
                continue

            b_wins = [t for t in bucket if t["r"] > 0]
            b_win_rate = len(b_wins) / len(bucket) * 100
            b_avg_r = sum(t["r"] for t in bucket) / len(bucket)

            print(f"  Skor {lo}-{hi}: {len(bucket)} sinyal, "
                  f"kazanma {b_win_rate:.1f}%, ortalama R {b_avg_r:+.2f}")

    print("\nNot: Ortalama R pozitifse sistem risk/ödül açısından kâr "
          "üretmiş demektir (komisyon/slipaj hariç). Negatifse eşikleri "
          "veya skorlama ağırlıklarını gözden geçirmek gerekir.")

    bt_reason_breakdown(all_trades)


def bt_reason_breakdown(all_trades):
    """
    Her bir 'teyit' (indikatör) tek başına kazanma oranını ne yönde
    etkiliyor, onu ölçer. Bir teyit hangi sinyallerde vardıysa o
    grubun performansını, olmadığı sinyallerin performansıyla
    karşılaştırır. Böylece hangi indikatörün gerçekten işe yaradığı,
    hangisinin gürültü (hatta zararlı) olduğu görülür.
    """
    print("\n" + "-" * 50)
    print("🔍 TEYİT (İNDİKATÖR) BAZINDA ETKİ ANALİZİ")
    print("-" * 50)
    print("(pozitif fark = bu teyit varken performans daha iyi, "
          "negatif fark = bu teyit varken performans daha kötü)\n")

    for direction in ("LONG", "SHORT"):
        subset = [t for t in all_trades if t["direction"] == direction]
        if len(subset) < 10:
            continue

        all_reasons = set()
        for t in subset:
            all_reasons.update(t["reasons"].split("|"))
        all_reasons.discard("")

        overall_avg_r = sum(t["r"] for t in subset) / len(subset)

        rows = []
        for reason in sorted(all_reasons):
            with_reason = [t for t in subset if reason in t["reasons"].split("|")]
            without_reason = [t for t in subset if reason not in t["reasons"].split("|")]

            if len(with_reason) < 5:
                continue

            with_avg_r = sum(t["r"] for t in with_reason) / len(with_reason)
            with_win_rate = len([t for t in with_reason if t["r"] > 0]) / len(with_reason) * 100

            diff = with_avg_r - overall_avg_r

            rows.append((reason, len(with_reason), with_win_rate, with_avg_r, diff))

        rows.sort(key=lambda x: x[4], reverse=True)

        print(f"\n{direction} (genel ortalama R: {overall_avg_r:+.2f}, "
              f"{len(subset)} sinyal):")

        if not rows:
            print("  Yeterli veri yok (her teyit için en az 5 sinyal gerekiyor)")
            continue

        for reason, count, win_rate, avg_r, diff in rows:
            print(f"  {reason:<28} n={count:<4} kazanma={win_rate:5.1f}%  "
                  f"R={avg_r:+.2f}  (fark: {diff:+.2f})")

    print("\nNot: 'n' sayısı 15-20'nin altındaysa o teyit için sonuç "
          "istatistiksel olarak güvenilir değildir, yorumlarken dikkatli "
          "ol. Fark belirgin şekilde negatifse (örn. -0.2 ve altı), o "
          "teyidi skordan çıkarmayı düşünebiliriz.")


def bt_save_csv(all_trades, path="backtest_results.csv"):
    if not all_trades:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_trades[0].keys()))
        writer.writeheader()
        writer.writerows(all_trades)
    print(f"\n💾 Detaylı sonuçlar kaydedildi: {path}")


def backtest_main(symbols_arg, days):
    symbols = [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]
    print(f"🚀 Backtest başlıyor: {symbols} | {days} gün")

    all_trades = []
    for symbol in symbols:
        try:
            trades = bt_backtest_symbol(symbol, days)
            all_trades.extend(trades)
        except Exception as e:
            print(f"❌ {symbol} backtest hatası: {e}")

    bt_print_summary(all_trades)
    bt_save_csv(all_trades)


# =========================================================
# ENTRY POINT
# =========================================================

def main():
    parser = argparse.ArgumentParser(description="Binance Long+Short Scanner & Backtest")
    parser.add_argument("--backtest", action="store_true",
                         help="Normal tarama yerine backtest modunda çalıştır")
    parser.add_argument("--symbols", type=str, default="BTCUSDT,ETHUSDT,SOLUSDT",
                         help="Backtest için virgülle ayrılmış coin listesi")
    parser.add_argument("--days", type=int, default=60,
                         help="Backtest için kaç günlük geçmiş veri test edilsin")
    args = parser.parse_args()

    if args.backtest:
        backtest_main(args.symbols, args.days)
    else:
        scan_main()


if __name__ == "__main__":
    main()
