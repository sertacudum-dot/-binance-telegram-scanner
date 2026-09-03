"""
BACKTEST SCRIPT
================

Bu script, Bot.py içindeki analyze_core() fonksiyonunun ürettiği
LONG/SHORT sinyallerini geçmiş Binance verisiyle test eder ve
her sinyalin gerçekte kâr mı zarar mı ettirdiğini ölçer.

KULLANIM:
    python backtest.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --days 60

NASIL ÇALIŞIR:
    1. Belirtilen coin(ler) için geçmiş 15 dakikalık mumları çeker.
    2. 1h ve 4h mumlarını 15m mumlardan yeniden oluşturur (ekstra
       API isteği yapmadan, zaman damgalarına göre gruplayarak).
    3. Zaman içinde ilerler (walk-forward): her adımda SADECE o ana
       kadar bilinen veriyle Bot.py'deki aynı sinyal mantığını çalıştırır.
    4. Bir sinyal üretildiğinde, SL/TP seviyelerinden hangisinin önce
       vurulduğunu sonraki mumlarda kontrol eder.
    5. Sonunda kazanma oranı, ortalama R (risk katı) ve sinyal sayısı
       gibi özet istatistikleri yazdırır.

NOT: Bu script'in ürettiği sonuçlar sadece GEÇMİŞ veri üzerinde bir
fikir verir; gelecekte aynı performansı garanti etmez. Piyasa
koşulları değişebilir (rejim değişikliği), bu yüzden düzenli aralıklarla
tekrar çalıştırıp sonuçları izlemek gerekir.
"""

import argparse
import csv
import time
import urllib.parse
from datetime import datetime, timezone

# Repo'daki dosya Bot.py adıyla duruyor; bu yüzden Bot.py'yi import
# ediyoruz. Eğer sende dosya adı farklıysa (örn. scanner.py), aşağıdaki
# satırı "import scanner as sc" olarak değiştir.
import Bot as sc


LOOKAHEAD_CANDLES = 96      # sinyal sonrası en fazla kaç 15m mum bekleyelim (96 = 24 saat)
COOLDOWN_CANDLES = 8        # aynı coin için bir sinyalden sonra kaç mum boyunca yeni sinyal aranmasın (8 = 2 saat)
TRAIL_WINDOW = 1100         # her adımda sadece son N adet 15m mumu kullan (performans için)
MIN_WARMUP_15M = 960        # backtest'e başlamadan önce gereken minimum 15m mum sayısı (~10 gün)


# =========================================================
# GEÇMİŞ VERİ ÇEKME (sayfalama ile)
# =========================================================

def fetch_full_klines(symbol, interval, days):
    """
    Belirtilen gün sayısı kadar geçmişe giderek TÜM kapanmış
    15m/1h/4h mumları sayfalama yaparak çeker (Binance tek istekte
    en fazla 1000 mum veriyor).
    """
    interval_ms = {
        "15m": 15 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
    }[interval]

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
        url = sc.BINANCE + "/api/v3/klines?" + params
        data = sc.get(url)
        time.sleep(sc.REQUEST_SLEEP)

        if not data:
            break

        all_rows.extend(data)
        last_close_time = data[-1][6]

        if last_close_time <= cursor:
            break

        cursor = last_close_time + 1

        if len(data) < 1000:
            break

    # Sadece kapanmış mumları al (son mum hâlâ oluşuyor olabilir)
    now_ms = int(time.time() * 1000)
    all_rows = [r for r in all_rows if r[6] <= now_ms]

    close = [float(x[4]) for x in all_rows]
    high = [float(x[2]) for x in all_rows]
    low = [float(x[3]) for x in all_rows]
    volume = [float(x[5]) for x in all_rows]

    return close, high, low, volume


# =========================================================
# WALK-FORWARD BACKTEST (tek coin)
# =========================================================

def simulate_outcome(direction, entry_price, sl, tp1, tp2, tp3,
                      future_high, future_low):
    """
    Sinyal sonrası mumlarda SL/TP seviyelerinden hangisi önce
    vuruldu, onu bulur. Aynı mumda hem SL hem TP tetiklenirse
    (yüksek volatilite), ihtiyatlı olmak için SL'nin önce
    vurulduğunu varsayıyoruz.
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


def backtest_symbol(symbol, days):
    print(f"\n📥 {symbol}: geçmiş veri çekiliyor ({days} gün)...")

    close15, high15, low15, vol15 = fetch_full_klines(symbol, "15m", days)

    if len(close15) < MIN_WARMUP_15M + LOOKAHEAD_CANDLES:
        print(f"⚠️ {symbol}: yeterli veri yok, atlanıyor "
              f"({len(close15)} mum).")
        return []

    print(f"✅ {symbol}: {len(close15)} adet 15m mum indirildi.")

    # 1h ve 4h kapanış serilerini 15m mumlardan türet
    # (Binance mum zamanları epoch'a hizalı olduğu için 4'lü ve
    # 16'lı gruplamak doğru 1h/4h mumlarını verir)
    full_close1h = close15[3::4]
    full_close4h = close15[15::16]

    trades = []
    last_signal_index = -COOLDOWN_CANDLES - 1

    total_steps = len(close15) - LOOKAHEAD_CANDLES
    for i in range(MIN_WARMUP_15M, total_steps):

        if i - last_signal_index < COOLDOWN_CANDLES:
            continue

        window_start = max(0, i - TRAIL_WINDOW + 1)

        w_close15 = close15[window_start:i + 1]
        w_high15 = high15[window_start:i + 1]
        w_low15 = low15[window_start:i + 1]
        w_vol15 = vol15[window_start:i + 1]

        n1h = (i + 1) // 4
        n4h = (i + 1) // 16

        w_close1h = full_close1h[:n1h]
        w_close4h = full_close4h[:n4h]

        result = sc.analyze_core(
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
        elif result["short_signal"]:
            direction = "SHORT"
            sl, tp1, tp2, tp3 = (
                result["short_sl"], result["short_tp1"],
                result["short_tp2"], result["short_tp3"]
            )
            score = result["short_score"]

        if not direction:
            continue

        future_high = high15[i + 1: i + 1 + LOOKAHEAD_CANDLES]
        future_low = low15[i + 1: i + 1 + LOOKAHEAD_CANDLES]

        outcome, r_multiple = simulate_outcome(
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
            "r": r_multiple
        })

        last_signal_index = i

    print(f"📊 {symbol}: {len(trades)} sinyal bulundu.")
    return trades


# =========================================================
# ÖZET RAPOR
# =========================================================

def print_summary(all_trades):
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

    print("\nNot: Ortalama R pozitifse sistem risk/ödül açısından "
          "kâr üretmiş demektir (komisyon/slipaj hariç). Negatifse "
          "eşikleri veya skorlama ağırlıklarını gözden geçirmek gerekir.")


def save_csv(all_trades, path="backtest_results.csv"):
    if not all_trades:
        return

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_trades[0].keys()))
        writer.writeheader()
        writer.writerows(all_trades)

    print(f"\n💾 Detaylı sonuçlar kaydedildi: {path}")


# =========================================================
# MAIN
# =========================================================

def main():
    parser = argparse.ArgumentParser(description="Binance sinyal botu backtest'i")
    parser.add_argument(
        "--symbols", type=str, default="BTCUSDT,ETHUSDT,SOLUSDT",
        help="Virgülle ayrılmış coin listesi (örn. BTCUSDT,ETHUSDT)"
    )
    parser.add_argument(
        "--days", type=int, default=60,
        help="Kaç günlük geçmiş veri test edilsin (varsayılan: 60)"
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print(f"🚀 Backtest başlıyor: {symbols} | {args.days} gün")

    all_trades = []
    for symbol in symbols:
        try:
            trades = backtest_symbol(symbol, args.days)
            all_trades.extend(trades)
        except Exception as e:
            print(f"❌ {symbol} backtest hatası: {e}")

    print_summary(all_trades)
    save_csv(all_trades)


if __name__ == "__main__":
    main()
