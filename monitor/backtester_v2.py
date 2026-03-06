"""
OLD vs NEW 전략 비교 백테스터.

OLD: 프로그레시브 트레일링 스톱 + 고정 손절 1.2% + 시간 청산
NEW: 비대칭 R:R (타이트 손절 + 시간정지 + 티어드 분할매도 + 잔여분 트레일링)

Usage:
    python3 backtester_v2.py --codes 005930,000660,035420 --days 20
    python3 backtester_v2.py --codes 005930 --days 60 --entry-quality premium --show-trades
    python3 backtester_v2.py --codes 005930,000660 --days 30 --entry-quality mixed
"""

import argparse
import logging
import os
import random
import sys
from datetime import datetime

import pytz
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from kis_client import KISClient

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

# ── 비용 상수 ──
BUY_FEE = 0.015       # 매수 수수료 %
SELL_FEE = 0.015       # 매도 수수료 %
SELL_TAX = 0.18        # 매도세 %
SLIPPAGE = 0.06        # 슬리피지 % per side
ROUND_COST = BUY_FEE + SELL_FEE + SELL_TAX + SLIPPAGE * 2  # ~0.33%

BARS = 78              # 6.5시간 / 5분 = 78개 5분봉
MINUTES_PER_BAR = 5


# ═══════════════════════════════════════════════════════════════
# 인트라데이 시뮬레이션 (일봉 OHLC → 78개 5분봉)
# ═══════════════════════════════════════════════════════════════

def generate_intraday(d_open, d_high, d_low, d_close, seed=0):
    """일봉 OHLC에서 78개 5분봉 생성 (구간별 선형보간 + 노이즈)."""
    rng = random.Random(seed)
    n = BARS
    r = max(d_high - d_low, 1)

    up = d_close >= d_open
    if up:
        # 상승일: 시가 → 소폭딥 → 상승 → 고가 → 소폭조정 → 종가
        keys = [
            (0, d_open),
            (5, max(d_low, int(d_open - r * 0.12))),
            (int(n * 0.25), int(d_open + (d_high - d_open) * 0.4)),
            (int(n * 0.50), d_high),
            (int(n * 0.65), int(d_high - r * 0.15)),
            (n - 1, d_close),
        ]
    else:
        # 하락일: 시가 → 소폭상승 → 고가 → 하락 → 저가 → 소폭반등 → 종가
        keys = [
            (0, d_open),
            (int(n * 0.10), d_high),
            (int(n * 0.35), int(d_high - (d_high - d_low) * 0.6)),
            (int(n * 0.55), d_low),
            (int(n * 0.75), int(d_low + r * 0.12)),
            (n - 1, d_close),
        ]

    # 구간별 선형보간
    prices = []
    for i in range(n):
        lo_k, hi_k = keys[0], keys[-1]
        for k in range(len(keys) - 1):
            if keys[k][0] <= i <= keys[k + 1][0]:
                lo_k, hi_k = keys[k], keys[k + 1]
                break
        span = hi_k[0] - lo_k[0]
        if span == 0:
            p = lo_k[1]
        else:
            p = lo_k[1] + (i - lo_k[0]) / span * (hi_k[1] - lo_k[1])

        # ±0.1% 노이즈
        p += rng.uniform(-0.001, 0.001) * p
        prices.append(max(d_low, min(d_high, int(p))))

    prices[0] = d_open
    prices[-1] = d_close

    # 5분봉 candle 배열
    candles = []
    for i in range(len(prices) - 1):
        co, cc = prices[i], prices[i + 1]
        ch = min(d_high, max(co, cc, int(max(co, cc) * 1.0005)))
        cl = max(d_low, min(co, cc, int(min(co, cc) * 0.9995)))
        candles.append({"open": co, "high": ch, "low": cl, "close": cc})

    return candles


# ═══════════════════════════════════════════════════════════════
# OLD 전략: 프로그레시브 트레일링 스톱
# ═══════════════════════════════════════════════════════════════

def sim_old(candles, entry):
    """OLD: [(5.0,4.0),(3.0,2.2),(2.0,1.5),(1.5,1.0)] 트레일링 + 1.2% 고정손절 + 5bar 시간청산."""
    stop_pct = 1.2
    levels = [(5.0, 4.0), (3.0, 2.2), (2.0, 1.5), (1.5, 1.0)]

    high = entry
    stop = int(entry * (1 - stop_pct / 100))

    for i, c in enumerate(candles):
        if c["high"] > high:
            high = c["high"]

        # 프로그레시브 트레일링 업데이트
        hwm = (high - entry) / entry * 100
        for lv, prot in levels:
            if hwm >= lv:
                stop = max(stop, int(entry * (1 + prot / 100)))
                break

        # 스톱 히트
        if c["low"] <= stop:
            pnl = (stop - entry) / entry * 100 - ROUND_COST
            reason = "trailing" if stop > int(entry * (1 - stop_pct / 100)) else "stop_loss"
            return {"net_pnl": round(pnl, 3), "reason": reason, "bars": i + 1}

        # 시간 청산: 5bar(25분) 동안 ±0.5% 이내 횡보
        if i >= 5 and abs((c["close"] - entry) / entry * 100) < 0.5:
            pnl = (c["close"] - entry) / entry * 100 - ROUND_COST
            return {"net_pnl": round(pnl, 3), "reason": "time_flat", "bars": i + 1}

    # 장마감
    pnl = (candles[-1]["close"] - entry) / entry * 100 - ROUND_COST
    return {"net_pnl": round(pnl, 3), "reason": "eod", "bars": len(candles)}


# ═══════════════════════════════════════════════════════════════
# NEW 전략: 비대칭 R:R (타이트 손절 + 시간정지 + 티어드 + 트레일링)
# ═══════════════════════════════════════════════════════════════

def sim_new(candles, entry, quality="standard"):
    """NEW: 진입품질 기반 타이트 손절 + 시간정지 + 분할매도 + 잔여분 트레일링."""
    stop_map = {"premium": 1.5, "standard": 1.2, "weak": 0.8}
    stop_pct = stop_map[quality]

    tiers = [(1.5, 40), (3.0, 50)]
    trail_pct = 1.5
    flat_bars = max(1, 20 // MINUTES_PER_BAR)
    lose_bars = max(1, 20 // MINUTES_PER_BAR)
    flat_thresh = 0.3

    remaining = 1.0       # 보유 비율 (1.0 = 100%)
    realized = 0.0        # 실현된 가중 PnL
    tiers_done = [False] * len(tiers)
    peak = entry

    for i, c in enumerate(candles):
        if c["high"] > peak:
            peak = c["high"]

        cur_pnl = (c["close"] - entry) / entry * 100
        low_pnl = (c["low"] - entry) / entry * 100
        high_pnl = (c["high"] - entry) / entry * 100

        # 1. 타이트 손절
        if low_pnl <= -stop_pct:
            pnl = -stop_pct - ROUND_COST
            realized += remaining * pnl
            return {"net_pnl": round(realized, 3), "reason": "tight_stop", "bars": i + 1}

        # 2. 시간정지 — 횡보 (15분)
        if i >= flat_bars and abs(cur_pnl) < flat_thresh:
            pnl = cur_pnl - ROUND_COST
            realized += remaining * pnl
            return {"net_pnl": round(realized, 3), "reason": "time_flat", "bars": i + 1}

        # 3. 시간정지 — 마이너스: 백테스트에서 해로움 판명 → 제거

        # 4. 티어드 분할매도
        for t_idx, (t_pct, t_sell_pct) in enumerate(tiers):
            if not tiers_done[t_idx] and high_pnl >= t_pct:
                sell_frac = (t_sell_pct / 100) * remaining  # remaining의 %
                pnl_tier = t_pct - ROUND_COST
                realized += sell_frac * pnl_tier
                remaining -= sell_frac
                tiers_done[t_idx] = True
                if remaining <= 0.01:
                    return {"net_pnl": round(realized, 3), "reason": "all_tiers", "bars": i + 1}
                break  # 한 bar에 한 티어만

        # 5. 잔여분 트레일링 (모든 티어 완료 후)
        if all(tiers_done) and remaining > 0.01:
            trail_stop = peak * (1 - trail_pct / 100)
            if c["low"] <= trail_stop:
                pnl_r = (int(trail_stop) - entry) / entry * 100 - ROUND_COST
                realized += remaining * pnl_r
                return {"net_pnl": round(realized, 3), "reason": "trail_rem", "bars": i + 1}

    # 장마감
    pnl_r = (candles[-1]["close"] - entry) / entry * 100 - ROUND_COST
    realized += remaining * pnl_r
    return {"net_pnl": round(realized, 3), "reason": "eod", "bars": len(candles)}


# ═══════════════════════════════════════════════════════════════
# 실행
# ═══════════════════════════════════════════════════════════════

def assign_quality(seed):
    """mixed 모드: 20% premium, 50% standard, 30% weak."""
    rng = random.Random(seed)
    r = rng.random()
    if r < 0.20:
        return "premium"
    elif r < 0.70:
        return "standard"
    else:
        return "weak"


def run(kis, codes, days, eq):
    old_all, new_all = [], []

    for code in codes:
        daily = kis.get_daily_candles(code)
        if not daily:
            print(f"  ⚠ {code}: 일봉 데이터 없음")
            continue

        target = daily[:days]
        target.reverse()  # oldest first

        for day in target:
            d_o = int(str(day.get("stck_oprc", 0)).replace(",", "") or 0)
            d_h = int(str(day.get("stck_hgpr", 0)).replace(",", "") or 0)
            d_l = int(str(day.get("stck_lwpr", 0)).replace(",", "") or 0)
            d_c = int(str(day.get("stck_clpr", 0)).replace(",", "") or 0)
            date = day.get("stck_bsop_date", "?")

            if d_o <= 0 or d_h <= d_l:
                continue

            range_pct = (d_h - d_l) / d_o * 100
            if range_pct < 0.5:
                continue
            upside_pct = (d_h - d_o) / d_o * 100
            if upside_pct < 1.5:
                continue

            # 진입가: 시가 + 0.3% (확인 후 매수 시뮬레이션)
            entry = int(d_o * 1.003)
            entry = min(entry, d_h)

            seed = hash(f"{code}_{date}") & 0xFFFFFFFF
            candles = generate_intraday(d_o, d_h, d_l, d_c, seed)

            # 진입 품질 결정
            quality = eq if eq != "mixed" else assign_quality(seed)

            ot = sim_old(candles, entry)
            nt = sim_new(candles, entry, quality)
            ot["date"] = nt["date"] = date
            ot["code"] = nt["code"] = code
            nt["quality"] = quality
            old_all.append(ot)
            new_all.append(nt)

    return old_all, new_all


def print_summary(label, trades):
    if not trades:
        print(f"\n{label}: 거래 없음")
        return

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    total = sum(t["net_pnl"] for t in trades)
    avg = total / len(trades)
    avg_w = sum(t["net_pnl"] for t in wins) / len(wins) if wins else 0
    avg_l = sum(t["net_pnl"] for t in losses) / len(losses) if losses else 0
    gw = sum(t["net_pnl"] for t in wins)
    gl = abs(sum(t["net_pnl"] for t in losses))
    pf = gw / gl if gl > 0 else float("inf")

    # 최대 낙폭 (MDD)
    equity = 0.0
    peak_equity = 0.0
    mdd = 0.0
    for t in trades:
        equity += t["net_pnl"]
        if equity > peak_equity:
            peak_equity = equity
        dd = peak_equity - equity
        if dd > mdd:
            mdd = dd

    # 종료 사유 분포
    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1

    print(f"\n{'=' * 58}")
    print(f"  {label}")
    print(f"{'=' * 58}")
    print(f"  총 거래:       {len(trades)}건")
    print(f"  승/패:         {len(wins)} / {len(losses)}  (승률 {len(wins)/len(trades)*100:.1f}%)")
    print(f"  총 수익률:     {total:+.2f}%")
    print(f"  평균 수익률:   {avg:+.3f}%")
    print(f"  평균 승:       {avg_w:+.3f}%")
    print(f"  평균 패:       {avg_l:+.3f}%")
    if avg_l != 0:
        print(f"  R:R 비율:      {abs(avg_w / avg_l):.2f}x")
    print(f"  Profit Factor: {pf:.2f}")
    print(f"  최대 낙폭:     {mdd:.2f}%")
    print(f"  종료 사유:")
    for r, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {r:18s} {cnt:4d}건 ({cnt / len(trades) * 100:.1f}%)")
    print(f"{'=' * 58}")


def print_comparison(old_trades, new_trades):
    print(f"\n{'═' * 62}")
    print("  📊 OLD vs NEW 직접 비교 (동일 진입 → 다른 청산)")
    print(f"{'═' * 62}")

    nb, ob, eq = 0, 0, 0
    diff_sum = 0.0

    for o, n in zip(old_trades, new_trades):
        d = n["net_pnl"] - o["net_pnl"]
        diff_sum += d
        if d > 0.01:
            nb += 1
        elif d < -0.01:
            ob += 1
        else:
            eq += 1

    t = len(old_trades)
    print(f"  NEW 우세: {nb}건 ({nb / t * 100:.1f}%)")
    print(f"  OLD 우세: {ob}건 ({ob / t * 100:.1f}%)")
    print(f"  동률:     {eq}건 ({eq / t * 100:.1f}%)")
    print(f"  NEW 트레이드당 우위: {diff_sum / t:+.3f}%")
    print(f"  NEW 총 우위:         {diff_sum:+.2f}%")

    # 상황별 분석
    print(f"\n  {'─' * 56}")
    print("  상황별 분석:")

    # 상승일 (close > open)
    up_old = [o for o, n in zip(old_trades, new_trades)
              if o.get("_up", True)]  # fallback
    # Recalc based on actual trade data
    up_diffs = []
    down_diffs = []
    for o, n in zip(old_trades, new_trades):
        d = n["net_pnl"] - o["net_pnl"]
        # We don't have day data here, so classify by old result
        if o["net_pnl"] > 0:
            up_diffs.append(d)
        else:
            down_diffs.append(d)

    if up_diffs:
        print(f"  승 트레이드(OLD기준): NEW 평균 차이 {sum(up_diffs)/len(up_diffs):+.3f}% ({len(up_diffs)}건)")
    if down_diffs:
        print(f"  패 트레이드(OLD기준): NEW 평균 차이 {sum(down_diffs)/len(down_diffs):+.3f}% ({len(down_diffs)}건)")
    print(f"{'═' * 62}")


def main():
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="OLD vs NEW 전략 비교 백테스터")
    parser.add_argument("--codes", required=True,
                        help="종목코드 (콤마구분, 예: 005930,000660,035420)")
    parser.add_argument("--days", type=int, default=20,
                        help="백테스트 일수 (기본 20)")
    parser.add_argument("--entry-quality", default="standard",
                        choices=["premium", "standard", "weak", "mixed"],
                        help="NEW 전략 진입 품질 (기본 standard, mixed=랜덤분포)")
    parser.add_argument("--show-trades", action="store_true",
                        help="개별 거래 상세 출력")
    args = parser.parse_args()

    codes = [c.strip() for c in args.codes.split(",")]

    print(f"\n📊 백테스트 시작")
    print(f"   종목: {', '.join(codes)}")
    print(f"   기간: 최근 {args.days}거래일")
    print(f"   진입품질: {args.entry_quality}")
    print(f"   왕복비용: {ROUND_COST:.3f}% (수수료 {BUY_FEE + SELL_FEE:.3f}% + 세금 {SELL_TAX:.3f}% + 슬리피지 {SLIPPAGE * 2:.3f}%)")
    print(f"   시뮬레이션: {BARS}개 5분봉/일")

    kis = KISClient()
    old_t, new_t = run(kis, codes, args.days, args.entry_quality)

    if not old_t:
        print("\n❌ 유효한 거래 데이터 없음")
        return

    print_summary("📉 OLD 전략 (프로그레시브 트레일링)", old_t)
    print_summary("📈 NEW 전략 (비대칭 R:R)", new_t)
    print_comparison(old_t, new_t)

    if args.show_trades:
        print(f"\n📋 개별 거래 상세:")
        q_col = "품질" if args.entry_quality == "mixed" else ""
        print(f"  {'날짜':>10} {'종목':>8} {'OLD':>8} {'사유':>12} {'NEW':>8} {'사유':>14} {'차이':>8} {q_col}")
        print(f"  {'-' * 78}")
        for o, n in zip(old_t, new_t):
            d = n["net_pnl"] - o["net_pnl"]
            m = "✅" if d > 0.01 else "❌" if d < -0.01 else "➖"
            q = n.get("quality", "")[0].upper() if args.entry_quality == "mixed" else ""
            print(
                f"  {o['date']:>10} {o['code']:>8} {o['net_pnl']:>+7.2f}% {o['reason']:>12} "
                f"{n['net_pnl']:>+7.2f}% {n['reason']:>14} {d:>+7.2f}% {m} {q}"
            )


if __name__ == "__main__":
    main()
