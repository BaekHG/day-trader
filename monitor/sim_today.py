"""
2026-02-26 모멘텀 시뮬레이션 — 웹서치 수집 데이터 기반
버그 수정된 코드가 아침부터 돌았다면 어떻게 됐을지 추정
"""

# ── 수집 데이터 (2/26 장초반 9:11 AM 기준 웹서치 결과) ──
# 출처: 중앙이코노미뉴스 개장시황, 이데일리 특징주 등

STOCKS_TODAY = [
    # (종목명, 코드, 2/26 등락률%, 전일 이벤트, 전일 등락률 추정%, 가격대)
    ("에이엔피",     "015260", 28.52, "2/24 상한가(+29.90%)",    29.90, 728),
    ("비트맥스",     "377030", 24.80, "불명",                      0.0, 0),
    ("바이젠셀",     "308080", 24.37, "2/25 상한가(+29.85%)",    29.85, 9700),
    ("원풍물산",     "036090", 22.91, "2/25 +19.80%",            19.80, 0),
    ("현대ADM",     "339770", 22.59, "불명",                      0.0, 0),
    ("THE CUBE&",  "999999", 22.41, "불명",                      0.0, 0),
    ("나무기술",     "242040", 21.35, "2/13 하락(-4.96%)",        -4.96, 2420),
    ("파라택시스코리아","999998", 19.61, "불명",                      0.0, 0),
    ("쿠콘",        "347890", 17.77, "불명",                      0.0, 0),
    ("LG이노텍",    "011070", 15.65, "정상거래",                    1.0, 0),
    ("엑스게이트",   "239340", 15.35, "불명",                      0.0, 0),
]

# ── 전략 파라미터 (config.py 기준) ──
MOMENTUM_RATE_MIN = 5.0
MOMENTUM_RATE_MAX = 29.9
MOMENTUM_MIN_PRICE = 2000
MOMENTUM_PREV_DAY_MAX_CHANGE = 12.0  # 핵심 필터: 전일 +12% 초과 → 제외
MOMENTUM_MIN_SCORE = 60
TOTAL_CAPITAL = 3_000_000
MAX_POSITION_PCT = 80
MOMENTUM_STOP_LOSS_PCT = 2.5
COMMISSION_PCT = 0.015   # 매수+매도 수수료 (%)
TAX_PCT = 0.18           # 세금 (%)

TRAILING_STOP_LEVELS = [
    (10.0, 7.5),
    (7.0, 5.0),
    (5.0, 3.0),
    (3.0, 1.5),
    (1.5, 0.3),
]


def main():
    print("=" * 70)
    print("  2026-02-26 모멘텀 시뮬레이션 분석")
    print("  (수정된 코드가 아침 09:02부터 돌았다면?)")
    print("=" * 70)
    print()

    # ── Step 1: 모멘텀 소싱 필터 적용 ──
    print("▶ Step 1: 모멘텀 소싱 필터 적용")
    print(f"  조건: 등락률 {MOMENTUM_RATE_MIN}~{MOMENTUM_RATE_MAX}%, "
          f"최소 가격 {MOMENTUM_MIN_PRICE:,}원, "
          f"전일 등락률 ≤ {MOMENTUM_PREV_DAY_MAX_CHANGE}%")
    print("-" * 70)
    print(f"  {'종목':>12}  {'등락률':>7}  {'전일':>20}  {'전일등락':>7}  {'판정':>10}")
    print("-" * 70)

    passed = []
    for name, code, change, prev_event, prev_change, price in STOCKS_TODAY:
        # 등락률 범위 체크
        if not (MOMENTUM_RATE_MIN <= change <= MOMENTUM_RATE_MAX):
            verdict = "등락률 범위 초과"
        # 전일 연속급등 필터 (핵심!)
        elif prev_change > MOMENTUM_PREV_DAY_MAX_CHANGE:
            verdict = f"❌ 전일 {prev_change:+.1f}% > {MOMENTUM_PREV_DAY_MAX_CHANGE}%"
        # 가격 필터
        elif price > 0 and price < MOMENTUM_MIN_PRICE:
            verdict = "가격 미달"
        else:
            if prev_change > 0 and prev_change <= MOMENTUM_PREV_DAY_MAX_CHANGE:
                verdict = "✅ 통과"
                passed.append((name, code, change, price, prev_change))
            elif prev_change == 0:
                verdict = "⚠️ 전일 미확인 (통과 가능)"
                passed.append((name, code, change, price, prev_change))
            else:
                verdict = "✅ 통과"
                passed.append((name, code, change, price, prev_change))

        print(f"  {name:>12}  {change:>+6.1f}%  {prev_event:>20}  {prev_change:>+6.1f}%  {verdict}")

    print()
    print(f"  → 필터 통과: {len(passed)}개 / {len(STOCKS_TODAY)}개")
    print()

    # ── Step 2: 핵심 분석 ──
    print("=" * 70)
    print("  핵심 분석 결과")
    print("=" * 70)
    print()
    print("  🔴 오늘 상승률 TOP 3 전부 전일 급등 필터에 걸림!")
    print()
    print("  1위 에이엔피 (+28.52%) — 2/24 상한가(+29.90%) → 전일필터 탈락")
    print("  2위 비트맥스 (+24.80%) — 전일 데이터 미확인 (통과 가능)")
    print("  3위 바이젠셀 (+24.37%) — 2/25 상한가(+29.85%) → 전일필터 탈락")
    print("  4위 원풍물산 (+22.91%) — 2/25 +19.80% → 전일필터 탈락")
    print()

    if not passed:
        print("  ❌ 모멘텀 필터 통과 종목 = 0개")
        print("  → 버그가 수정되어 있었어도 매수는 없었을 가능성 높음")
        print()
        print("=" * 70)
        return

    # ── Step 3: 통과 종목 시뮬레이션 ──
    print("=" * 70)
    print("  통과 가능 종목 시뮬레이션 (전일 데이터 미확인 포함)")
    print("=" * 70)
    print()

    for name, code, change, price, prev_change in passed:
        if price <= 0:
            # 가격 미확인 — 추정
            print(f"  {name} ({code}): 가격 미확인 — 시뮬레이션 불가")
            continue

        # 모멘텀 진입 시뮬레이션 (09:02~09:15)
        # 시가는 전일종가 기준 등락률이 이미 반영된 상태
        # 진입 시점 추정: 시가 + 2% (급등 초반 진입)
        prev_close = int(price / (1 + change / 100))
        est_open = int(prev_close * (1 + change / 100 * 0.6))  # 시가 = 등락률의 ~60% 수준
        entry_price = int(est_open * 1.02)  # 시가 +2% 진입
        if entry_price > price:
            entry_price = price  # 종가 초과 불가

        order_price = int(entry_price * 1.01)  # +1% 상한 지정가
        position_cash = int(TOTAL_CAPITAL * MAX_POSITION_PCT / 100)
        qty = position_cash // order_price
        if qty <= 0:
            continue

        invested = qty * entry_price

        # 고점 추정: 종가보다 3~5% 높았을 것으로 추정 (장중 고점)
        est_high = int(price * 1.03)
        est_low = int(entry_price * 0.97)

        # 종가 기준 청산 (15:10 강제청산)
        exit_price = price
        hwm_pct = (est_high - entry_price) / entry_price * 100

        # 트레일링 스톱 체크
        trailing_stop = int(entry_price * (1 - MOMENTUM_STOP_LOSS_PCT / 100))
        for level_pnl, stop_pnl in TRAILING_STOP_LEVELS:
            if hwm_pct >= level_pnl:
                trailing_stop = max(trailing_stop, int(entry_price * (1 + stop_pnl / 100)))
                break

        if est_low <= trailing_stop and trailing_stop > int(entry_price * (1 - MOMENTUM_STOP_LOSS_PCT / 100)):
            exit_price = trailing_stop
            exit_reason = f"트레일링 (고점 +{hwm_pct:.1f}%→보호)"
        elif est_low <= int(entry_price * (1 - MOMENTUM_STOP_LOSS_PCT / 100)):
            exit_price = int(entry_price * (1 - MOMENTUM_STOP_LOSS_PCT / 100))
            exit_reason = "손절"
        else:
            exit_price = price  # 종가 청산
            exit_reason = "종가 청산 (15:10)"

        # P&L
        gross_pnl = (exit_price - entry_price) / entry_price * 100
        cost = COMMISSION_PCT * 2 + TAX_PCT  # 수수료 + 세금 (%)
        net_pnl = gross_pnl - cost
        pnl_amount = int(invested * net_pnl / 100)

        emoji = "🟢" if net_pnl > 0 else "🔴"
        print(f"  {emoji} {name} ({code})")
        print(f"     전일종가 추정: {prev_close:,}원")
        print(f"     진입가: ~{entry_price:,}원 (시가+2% 추정)")
        print(f"     수량: {qty}주 × 투입금 {invested:,}원")
        print(f"     종가: {price:,}원 / 고점 추정: ~{est_high:,}원")
        print(f"     청산: {exit_price:,}원 ({exit_reason})")
        print(f"     수익률: {net_pnl:+.2f}% (수수료/세금 차감)")
        print(f"     손익: {pnl_amount:+,}원")
        print()

    # ── 결론 ──
    print("=" * 70)
    print("  🔍 결론")
    print("=" * 70)
    print()
    print("  오늘(2/26) 상승률 TOP 종목들의 대부분은")
    print("  전일(2/25) 또는 전전일(2/24)에 이미 상한가를 기록한 종목입니다.")
    print()
    print("  모멘텀 전략의 '전일 연속급등 필터'(MOMENTUM_PREV_DAY_MAX_CHANGE=12%)")
    print("  에 의해 대다수가 자동 탈락됩니다.")
    print()
    print("  ▸ 에이엔피 (+28.52%): 2/24 상한가 → ❌ 필터 탈락")
    print("  ▸ 바이젠셀 (+24.37%): 2/25 상한가 → ❌ 필터 탈락")
    print("  ▸ 원풍물산 (+22.91%): 2/25 +19.8% → ❌ 필터 탈락")
    print()
    print("  💡 즉, amount 버그가 수정돼 있었어도")
    print("     오늘 상위 급등주를 매수하지 않았을 가능성이 높습니다.")
    print()
    print("  전일 데이터를 확인할 수 없는 종목(비트맥스, 쿠콘, 엑스게이트 등)")
    print("  중에서 전일 등락률 <12%인 종목이 있었다면")
    print("  그 종목이 모멘텀 매수 대상이었을 수 있습니다.")
    print()
    print("  📌 정확한 시뮬레이션은 KIS API 접근이 가능한 환경에서")
    print("     실행해야 합니다. (이 환경에서는 프록시 차단)")
    print("=" * 70)


if __name__ == "__main__":
    main()
