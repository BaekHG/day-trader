"""
Day Trader — 자동 단타 매매 시스템
매일 08:40 분석 → 텔레그램 확인 → 매수 → 모니터링 → 매도 → 리포트
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta

import pytz

import config
from ai_analyzer import AIAnalyzer
from db import Database
from kis_client import KISClient
from market_data import MarketDataCollector
from monitor import PositionMonitor
from naver_data import NaverFinanceService, NaverNewsService
from telegram_bot import TelegramBot
from trader import Trader, round_to_tick

KST = pytz.timezone("Asia/Seoul")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs(config.LOG_DIR, exist_ok=True)


def setup_logging():
    today = datetime.now(KST).strftime("%Y%m%d")
    log_file = os.path.join(config.LOG_DIR, f"day_trader_{today}.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    fmt.converter = lambda *_: datetime.now(KST).timetuple()

    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setFormatter(fmt)

    console_h = logging.StreamHandler(sys.stdout)
    console_h.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_h)
    root.addHandler(console_h)


logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def now_kst() -> datetime:
    return datetime.now(KST)


def is_weekend() -> bool:
    return now_kst().weekday() >= 5


def is_market_hours() -> bool:
    n = now_kst()
    if n.weekday() >= 5:
        return False
    return n.replace(hour=8, minute=55, second=0) <= n <= n.replace(hour=15, minute=35, second=0)


def wait_until(target_time_str: str, bot: TelegramBot, kis: KISClient, monitor: PositionMonitor):
    """target_time_str = 'HH:MM'. 대기하면서 텔레그램 명령어 처리."""
    hh, mm = map(int, target_time_str.split(":"))
    while True:
        n = now_kst()
        target = n.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if n >= target:
            break
        remaining = (target - n).total_seconds()
        logger.info("분석 시작까지 %.0f초 대기 (%s)", remaining, target_time_str)
        # 대기 중 텔레그램 명령 처리 (30초 간격)
        bot.process_updates(kis, monitor)
        sleep_dur = min(30, remaining)
        if sleep_dur > 0:
            time.sleep(sleep_dur)


def past_analysis_time() -> bool:
    hh, mm = map(int, config.ANALYSIS_TIME.split(":"))
    n = now_kst()
    return n >= n.replace(hour=hh, minute=mm, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def _recalc_stop_loss(fill_price: int, order_price: int, ai_stop: int) -> int:
    """체결가 기준으로 손절가를 재계산한다.

    AI가 지정가(order_price) 기준으로 산출한 손절가(ai_stop)의 '비율'을
    실제 체결가(fill_price)에 적용하여 최소 MIN_STOP_LOSS_PCT 이상의
    거리를 보장한다.
    """
    if order_price > 0 and ai_stop > 0:
        stop_pct = (order_price - ai_stop) / order_price  # AI 의도 손절 비율
    else:
        stop_pct = 0

    # 최소 손절 거리 보장
    min_pct = config.MIN_STOP_LOSS_PCT / 100
    stop_pct = max(stop_pct, min_pct)

    adjusted = int(fill_price * (1 - stop_pct))
    logger.info(
        "손절가 재계산: 주문가 %s → 체결가 %s | AI손절 %s → 조정 %s (%.1f%%)",
        f"{order_price:,}", f"{fill_price:,}", f"{ai_stop:,}",
        f"{adjusted:,}", stop_pct * 100,
    )
    return adjusted


def _build_score_fallback(top_stock: dict, cur_price: int, phase: str) -> dict:
    """AI 실패 시 스코어 1위 종목으로 구성한 최소 분석 결과."""
    name = top_stock.get("hts_kor_isnm", "?")
    code = top_stock.get("mksc_shrn_iscd", "")
    score = top_stock.get("score", 0)
    stop_pct = config.AFTERNOON_MIN_STOP_LOSS_PCT if phase == "afternoon" else config.MIN_STOP_LOSS_PCT

    return {
        "marketAssessment": {
            "score": 50,
            "riskFactors": "AI 분석 불가 — 스코어 기반 fallback",
            "favorableThemes": [],
            "recommendation": "매매추천" if score >= 60 else "매매비추천",
        },
        "vetoResult": {
            "approved": score >= 60,
            "reason": f"AI 불가 — 정량 스코어 {score}점 기반 자동 판단",
            "newsRisk": "분석 불가",
            "confidence": min(score, 70),
        },
        "picks": [
            {
                "rank": 1,
                "symbol": code,
                "name": name,
                "currentPrice": cur_price,
                "reason": {"news": "AI 불가", "supply": "스코어 기반", "chart": "스코어 기반"},
                "setupType": ["score_fallback"],
                "positionFromHigh": 0,
                "entryZone": {"low": int(cur_price * 0.995), "high": int(cur_price * 1.005)},
                "stopLoss": int(cur_price * (1 - stop_pct / 100)),
                "target1": int(cur_price * 1.02),
                "target2": int(cur_price * 1.03),
                "confidence": min(score, 70),
                "tags": ["score_fallback"],
                "allocation": 70,
                "sellStrategy": {
                    "breakoutHold": "트레일링 스탑",
                    "breakoutFail": "즉시 손절",
                    "volumeDrop": "거래량 급감 시 청산",
                    "sideways": "횡보 시 시간 청산",
                },
                "score": score,
            },
        ] if score >= 60 else [],
        "riskAnalysis": {
            "failureFactors": "AI 분석 불가 — 뉴스 리스크 미확인",
            "successProbability": min(score, 50),
        },
        "marketSummary": "AI 분석 불가 — 정량 스코어만으로 판단",
        "marketScore": 50,
    }


def _count_momentum_losses(monitor: PositionMonitor) -> int:
    count = 0
    for t in monitor.trades_today:
        if t.get("phase") == "momentum" and t.get("pnl_amt", 0) < 0:
            count += 1
    return count


def _is_late_session() -> bool:
    hh, mm = map(int, config.LATE_SESSION_START.split(":"))
    return now_kst() >= now_kst().replace(hour=hh, minute=mm, second=0)


def _try_momentum_entry(
    kis: KISClient, bot: TelegramBot, db: Database,
    collector: MarketDataCollector, trader: Trader,
    monitor: PositionMonitor, sold_codes: set,
    market_data: dict,
) -> str | None:
    if not config.MOMENTUM_ENABLED:
        return None

    if monitor.positions:
        return None

    kosdaq = market_data.get("kosdaq_index", {})
    kosdaq_change = float(kosdaq.get("change_rate", "0") if isinstance(kosdaq, dict) else "0")
    if kosdaq_change <= config.MARKET_INDEX_BLOCK_PCT:
        logger.info("KOSDAQ %.1f%% — 시장 폭락 진입 차단 (한도 %.1f%%)",
                    kosdaq_change, config.MARKET_INDEX_BLOCK_PCT)
        bot.send_message(
            f"🛑 KOSDAQ {kosdaq_change:+.1f}% — 시장 하락으로 모멘텀 진입 차단"
        )
        return None

    late = _is_late_session()
    if late and config.LATE_SESSION_REQUIRE_PROFIT:
        daily_pnl = _get_daily_pnl_pct(monitor)
        if daily_pnl <= 0:
            logger.info("후반 시간대 + 오전 수익 없음 (%.1f%%) — 모멘텀 스킵", daily_pnl)
            return None

    momentum_losses = _count_momentum_losses(monitor)
    if momentum_losses >= config.MOMENTUM_DAILY_MAX_LOSSES:
        logger.info("모멘텀 일일 손절한도 도달 (%d/%d) — 모멘텀 스킵",
                    momentum_losses, config.MOMENTUM_DAILY_MAX_LOSSES)
        return None

    logger.info("Phase 2M — 모멘텀 후보 소싱")
    try:
        momentum_stocks = collector.enrich_momentum_candidates(market_data.get("stock_news", {}))
    except Exception as e:
        logger.warning("모멘텀 소싱 실패: %s", e)
        return None

    if not momentum_stocks:
        return None

    top = momentum_stocks[0]
    code = top.get("mksc_shrn_iscd", "")
    name = top.get("hts_kor_isnm", "?")
    change_pct = float(str(top.get("prdy_ctrt", "0")).replace(",", "") or "0")
    m_score = top.get("momentum_score", 0)

    min_score = config.LATE_SESSION_MIN_SCORE if late else config.MOMENTUM_MIN_SCORE
    if m_score < min_score:
        logger.info("모멘텀 1위 스코어 부족: %s (%.1f, 최소 %d) — 스킵",
                    name, m_score, min_score)
        return None

    logger.info("모멘텀 1위: %s (%.1f%%, 스코어 %.1f) — 풀백 진입 확인", name, change_pct, m_score)
    bot.send_message(
        f"🚀 <b>모멘텀 후보 발견</b>\n\n"
        f"{name} ({code})\n"
        f"등락률: {change_pct:+.1f}%\n"
        f"모멘텀 스코어: {m_score:.1f}\n"
        f"풀백 진입 확인 중..."
    )

    if not collector.check_momentum_entry(code):
        logger.info("모멘텀 풀백 미확인 — 다음 사이클 재시도")
        bot.send_message(f"⏳ {name} 풀백 진입 조건 미충족 — 다음 사이클 재시도")
        return None

    try:
        price_data = kis.get_current_price(code)
        cur_price = price_data["price"]
        now = now_kst()
        today_open = price_data.get("open", 0) if (now.hour == 9 and now.minute < 30) else 0
        today_high = price_data.get("high", 0)
    except Exception as e:
        logger.warning("모멘텀 현재가 조회 실패: %s", e)
        return None

    if cur_price <= 0:
        return None

    try:
        available_cash = kis.get_available_cash()
    except Exception:
        available_cash = config.TOTAL_CAPITAL

    pos_pct = config.LATE_SESSION_POSITION_PCT if late else config.MAX_POSITION_PCT
    position_cash = int(available_cash * pos_pct / 100)
    quantity = position_cash // cur_price
    if quantity <= 0:
        logger.info("모멘텀 주문 가능 수량 0주 — 스킵")
        return None

    if late:
        stop_pct = config.LATE_SESSION_STOP_LOSS_PCT
    else:
        stop_pct = config.MOMENTUM_STOP_LOSS_PCT
        for score_threshold, pct in config.MOMENTUM_STOP_LOSS_BY_SCORE:
            if m_score >= score_threshold:
                stop_pct = pct
                break
    stop_loss = int(cur_price * (1 - stop_pct / 100))

    # 모멘텀: 상한 지정가 (현재가 + 1% 버퍼) — 빠른 체결 + 슬리피지 제한
    order_price = round_to_tick(int(cur_price * 1.01))
    quantity = position_cash // order_price  # 상한가 기준 수량 재계산
    if quantity <= 0:
        logger.info("모멘텀 주문 가능 수량 0주 (버퍼 적용 후) — 스킵")
        return None

    order = {
        "stock_code": code,
        "name": name,
        "price": order_price,
        "quantity": quantity,
        "amount": quantity * order_price,
        "reason": f"모멘텀 진입 ({change_pct:+.1f}%, 스코어 {m_score:.1f})",
        "target1": int(cur_price * 1.05),
        "target2": int(cur_price * 1.10),
        "stop_loss": stop_loss,
        "score": int(m_score),
        "sell_strategy": {"breakoutHold": "모멘텀 트레일링", "breakoutFail": "갭실패 즉시청산"},
        "is_momentum": True,
    }

    bot.send_message(
        f"🚀 <b>모멘텀 매수 진행</b>\n\n"
        f"{name} {quantity}주 × {order_price:,}원 (상한지정가)\n"
        f"현재가: {cur_price:,}원 / 버퍼: +1%\n"
        f"투입금: {quantity * order_price:,}원 (자본 {pos_pct}%)\n"
        f"손절선: {stop_loss:,}원 (-{stop_pct}%)"
    )

    results = trader.execute_buy_orders([order])
    success = [r for r in results if r["success"]]
    if not success:
        bot.send_message(f"⚠️ {name} 모멘텀 매수 실패")
        return None

    fills = []
    for attempt in range(4):
        time.sleep(15)
        result = trader.check_fills(success)
        if result is None:
            continue
        fills = result
        if fills:
            break

    if fills:
        f = fills[0]
        fill_price = f["price"]
        buy_slippage = (fill_price - cur_price) / cur_price * 100 if cur_price > 0 else 0
        adjusted_stop = int(fill_price * (1 - stop_pct / 100))

        bot.send_fill_confirmation(fills)
        monitor.add_position(
            stock_code=f["stock_code"],
            name=f["name"],
            quantity=f["quantity"],
            entry_price=fill_price,
            target1=order["target1"],
            target2=order["target2"],
            stop_loss=adjusted_stop,
            sell_strategy=order["sell_strategy"],
            buy_slippage_pct=buy_slippage,
            score=order["score"],
            phase="momentum",
            is_momentum=True,
            today_open=today_open,
        )

        if not config.DRY_RUN and db:
            db.save_trade(
                stock_code=f["stock_code"], stock_name=f["name"],
                action="buy", quantity=f["quantity"], price=fill_price,
                reason=order["reason"],
            )

        return "momentum_entered"

    if not config.DRY_RUN:
        try:
            pending = kis.get_pending_orders()
            momentum_pending = [p for p in pending if p["stock_code"] == code]
            if momentum_pending:
                trader.cancel_unfilled_orders(momentum_pending)
                bot.send_message(f"⏳ {name} 모멘텀 미체결 취소")
        except Exception as e:
            logger.warning("모멘텀 미체결 취소 실패: %s", e)

    return None


def _past_entry_cutoff() -> bool:
    hh, mm = map(int, config.NO_NEW_ENTRY_AFTER.split(":"))
    n = now_kst()
    return n.hour > hh or (n.hour == hh and n.minute >= mm)


def _past_afternoon_cutoff() -> bool:
    hh, mm = map(int, config.AFTERNOON_PHASE_END.split(":"))
    n = now_kst()
    return n.hour > hh or (n.hour == hh and n.minute >= mm)


def _afternoon_started() -> bool:
    hh, mm = map(int, config.AFTERNOON_PHASE_START.split(":"))
    n = now_kst()
    return n.hour > hh or (n.hour == hh and n.minute >= mm)


def _should_run_afternoon(monitor: PositionMonitor) -> bool:
    if not config.AFTERNOON_ENABLED:
        return False
    if monitor.should_stop:
        return False
    if _past_afternoon_cutoff():
        return False
    daily_pnl = _get_daily_pnl_pct(monitor)
    if daily_pnl <= config.DAILY_LOSS_LIMIT_PCT:
        logger.info("오후 전략 스킵 — 일일 손실한도 도달 (%.1f%%)", daily_pnl)
        return False
    return True


def _try_reinvest(
    kis: KISClient, bot: TelegramBot, collector: MarketDataCollector,
    analyzer: AIAnalyzer, trader: Trader, monitor: PositionMonitor,
    sold_codes: set, phase: str = "morning",
) -> None:
    cutoff_fn = _past_afternoon_cutoff if phase == "afternoon" else _past_entry_cutoff
    if cutoff_fn():
        return
    try:
        remaining_cash = kis.get_available_cash()
    except Exception as e:
        logger.warning("잔여 현금 조회 실패: %s", e)
        return
    if remaining_cash < config.MIN_REINVEST_CASH:
        return

    skip_codes = set(monitor.positions.keys()) | sold_codes
    logger.info("잔여 현금 재투자 — %s원 추가 종목 탐색", f"{remaining_cash:,}")
    bot.send_message(f"💰 잔여 현금 {remaining_cash:,}원 — 추가 종목 분석")

    try:
        mdata = collector.fetch_market_data(phase=phase)
        enr = collector.enrich_stocks(
            mdata["volume_ranking"], mdata["stock_news"], mdata["is_market_open"],
            phase=phase,
        )
        if not enr:
            bot.send_message("📊 하드 필터 통과 종목 없음 — 재투자 건너뜀")
            return
        reinvest_pos = [
            {"name": p["name"], "code": c, "remaining_qty": p["remaining_qty"]}
            for c, p in monitor.positions.items()
        ]
        anal = analyzer.analyze(
            enriched_stocks=enr, up_ranking=mdata["up_ranking"],
            down_ranking=mdata["down_ranking"], kospi_index=mdata["kospi_index"],
            kosdaq_index=mdata["kosdaq_index"], exchange_rate=mdata["exchange_rate"],
            is_market_open=mdata["is_market_open"],
            current_positions=reinvest_pos or None,
        )
        anal["_kospi"] = mdata["kospi_index"]
        anal["_kosdaq"] = mdata["kosdaq_index"]
        anal["_exchange_rate"] = mdata["exchange_rate"]
        bot.send_analysis_result(anal, remaining_cash)

        rec = anal.get("marketAssessment", {}).get("recommendation", "")
        if rec == "매매비추천":
            return

        new_picks = [p for p in anal.get("picks", []) if p["symbol"] not in skip_codes]
        if not new_picks:
            bot.send_message("추가 매수 대상 없음")
            return

        new_orders = trader.calculate_orders(new_picks, remaining_cash, skip_codes)
        if not new_orders:
            return

        bot.send_buy_orders(new_orders)
        new_results = trader.execute_buy_orders(new_orders)
        new_success = [r for r in new_results if r["success"]]
        if not new_success:
            return

        new_map = {o["stock_code"]: o for o in new_success}
        new_fills = []
        for attempt in range(4):
            time.sleep(15)
            result = trader.check_fills(new_success)
            if result is None:
                continue
            new_fills = result
            if len(new_fills) >= len(new_success):
                break
        if new_fills:
            bot.send_fill_confirmation(new_fills)
            for nf in new_fills:
                mo = new_map.get(nf["stock_code"])
                if mo:
                    adjusted_stop = _recalc_stop_loss(
                        nf["price"], mo["price"], mo["stop_loss"],
                    )
                    monitor.add_position(
                        stock_code=nf["stock_code"], name=nf["name"],
                        quantity=nf["quantity"], entry_price=nf["price"],
                        target1=mo["target1"], target2=mo["target2"],
                        stop_loss=adjusted_stop,
                        sell_strategy=mo.get("sell_strategy"),
                    )

        filled_codes = {nf["stock_code"] for nf in new_fills}
        unfilled = [o for o in new_success if o["stock_code"] not in filled_codes]
        if unfilled:
            try:
                pending = kis.get_pending_orders()
                unfilled_codes = {o["stock_code"] for o in unfilled}
                to_cancel = [p for p in pending if p["stock_code"] in unfilled_codes]
                if to_cancel:
                    trader.cancel_unfilled_orders(to_cancel)
                    names = ", ".join(p["name"] for p in to_cancel)
                    bot.send_message(f"⏳ 미체결 자동 취소: {names}")
            except Exception as e:
                logger.error("미체결 취소 실패: %s", e)
    except Exception as e:
        logger.error("잔여 현금 재투자 실패: %s", e)


def _get_daily_pnl_pct(monitor: PositionMonitor) -> float:
    """일일 손익률 (실현 + 미실현)."""
    realized = sum(t.get("pnl_amt", 0) for t in monitor.trades_today)
    unrealized = 0
    for code, pos in monitor.positions.items():
        try:
            pd = monitor.kis.get_current_price(code)
            cur = pd["price"]
            if cur > 0:
                unrealized += (cur - pos["entry_price"]) * pos["remaining_qty"]
        except Exception:
            pass
    total_pnl = realized + unrealized
    if config.TOTAL_CAPITAL <= 0:
        return 0.0
    return total_pnl / config.TOTAL_CAPITAL * 100


def run_daily_cycle():
    setup_logging()
    logger.info("=" * 50)
    logger.info("Day Trader 시작 — %s", now_kst().strftime("%Y.%m.%d %H:%M"))
    logger.info("=" * 50)

    kis = KISClient()
    bot = TelegramBot()
    db = Database()
    naver_fin = NaverFinanceService()
    naver_news = NaverNewsService()
    collector = MarketDataCollector(kis, naver_fin, naver_news)
    ai_key = config.ANTHROPIC_API_KEY if config.AI_PROVIDER == "anthropic" else config.OPENAI_API_KEY
    analyzer = AIAnalyzer(ai_key, provider=config.AI_PROVIDER)
    trader = Trader(kis, bot, db)
    monitor = PositionMonitor(kis, bot, db)

    if not config.DRY_RUN:
        logger.info("KIS 잔고 ↔ positions.json 동기화")
        sync_result = monitor.sync_with_balance()
        if sync_result["added"] or sync_result["removed"]:
            lines = ["🔄 <b>포지션 동기화 완료</b>"]
            for h in sync_result["added"]:
                lines.append(f"  ➕ {h['name']} {h['quantity']}주 @ {h['avg_price']:,}원")
            for name in sync_result["removed"]:
                lines.append(f"  ➖ {name} (청산됨)")
            bot.send_message("\n".join(lines))

    bot.start_polling(kis, monitor)

    if is_weekend() and not config.DRY_RUN:
        bot.send_message("주말입니다. 월요일에 다시 시작합니다.")
        logger.info("주말 — 종료")
        return bot

    mode_label = " [모의투자]" if config.DRY_RUN else ""
    bot.send_message(f"🔔 Day Trader 시작{mode_label} ({now_kst().strftime('%Y.%m.%d %H:%M')})")

    sold_codes: set[str] = set()
    for t in monitor.trades_today:
        if "code" in t and t.get("pnl_amt", 0) < 0:
            sold_codes.add(t["code"])

    if monitor.positions and past_analysis_time():
        logger.info("기존 포지션 %d개 감지 — 모니터링 재개", len(monitor.positions))
        bot.send_message(
            f"기존 포지션 {len(monitor.positions)}개 감지 — 모니터링 재개\n"
            + "\n".join(f"  {p['name']} {p['remaining_qty']}주" for p in monitor.positions.values())
        )
        exit_reason = _run_monitoring_loop(
            monitor, bot, kis, collector, analyzer, trader, sold_codes,
        )
        if exit_reason == "positions_cleared" and not _past_entry_cutoff():
            logger.info("포지션 청산 — 추가 사이클 가능, 멀티사이클 진입")
        else:
            _send_daily_report(monitor, bot, db)
            return bot

    if not past_analysis_time() and not config.DRY_RUN:
        wait_until(config.ANALYSIS_TIME, bot, kis, monitor)

    cycle = 0
    consecutive_losses = 0
    while not _past_entry_cutoff() and cycle < config.MAX_CYCLES:
        cycle += 1
        logger.info("━━━ 사이클 %d/%d 시작 ━━━", cycle, config.MAX_CYCLES)

        daily_pnl = _get_daily_pnl_pct(monitor)
        if daily_pnl <= config.DAILY_LOSS_LIMIT_PCT:
            logger.info("일일 손실한도 도달 (%.1f%%) — 사이클 중단", daily_pnl)
            bot.send_message(f"🛑 일일 손실한도 도달 ({daily_pnl:.1f}%) — 매매 중단")
            break
        if daily_pnl >= config.DAILY_PROFIT_TARGET_PCT:
            logger.info("일일 수익목표 달성 (%.1f%%) — 사이클 중단", daily_pnl)
            bot.send_message(f"🎯 일일 수익목표 달성 ({daily_pnl:.1f}%) — 매매 중단")
            break
        if consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            logger.info("%d연패 — 당일 매매 중단", consecutive_losses)
            bot.send_message(f"🛑 {consecutive_losses}연패 — 당일 매매 중단 (리스크 관리)")
            break

        trades_before = len(monitor.trades_today)
        exit_reason = _run_one_cycle(
            cycle, kis, bot, db, collector, analyzer, trader, monitor, sold_codes,
            consecutive_losses=consecutive_losses,
        )
        for t in monitor.trades_today[trades_before:]:
            if "code" in t and t.get("pnl_amt", 0) < 0:
                sold_codes.add(t["code"])

        new_trades = monitor.trades_today[trades_before:]
        if new_trades:
            last_pnl = new_trades[-1].get("pnl_amt", 0)
            if last_pnl < 0:
                consecutive_losses += 1
            else:
                consecutive_losses = 0

        # 재시도 가능한 결과: 쿨다운 후 다음 사이클
        retryable = ("no_picks", "opening_filtered", "low_confidence", "positions_cleared")
        if exit_reason not in retryable:
            logger.info("사이클 종료 (사유: %s) — 재시도 불가", exit_reason)
            break

        if monitor.should_stop:
            break

        if not _past_entry_cutoff() and cycle < config.MAX_CYCLES:
            cooldown = config.CYCLE_COOLDOWN
            # 매매비추천/필터탈락은 쿨다운 짧게 (시장 변화 빠르게 재확인)
            if exit_reason in ("no_picks", "opening_filtered", "low_confidence"):
                cooldown = min(cooldown, 600)  # 최대 10분
                bot.send_message(
                    f"⏸ 사이클 {cycle} — 진입 조건 미충족 ({exit_reason})\n"
                    f"{cooldown // 60}분 후 시장 재분석합니다."
                )
            else:
                bot.send_message(f"⏸ 사이클 {cycle} 완료 — {cooldown // 60}분 쿨다운")
            logger.info("쿨다운 %d초 시작 (사유: %s)", cooldown, exit_reason)
            cooldown_end = time.time() + cooldown
            while time.time() < cooldown_end:
                try:
                    bot.process_updates(kis, monitor)
                except Exception:
                    pass
                if monitor.should_stop or _past_entry_cutoff():
                    break
                time.sleep(min(30, cooldown_end - time.time()))

    if monitor.positions and not monitor.should_stop:
        logger.info("오전 잔여 포지션 %d개 — 모니터링 계속", len(monitor.positions))
        loop_exit = _run_monitoring_loop(
            monitor, bot, kis, collector, analyzer, trader, sold_codes,
        )
        if loop_exit in ("market_close", "user_stop"):
            _send_daily_report(monitor, bot, db)
            return bot

    if _should_run_afternoon(monitor):
        if not _afternoon_started():
            start_str = config.AFTERNOON_PHASE_START
            bot.send_message(
                f"☀️ 오전 전략 종료 — {start_str} 오후 전략 시작 대기\n"
                f"(포지션↓ 사이즈↓ 보수적 운영)"
            )
            wait_until(config.AFTERNOON_PHASE_START, bot, kis, monitor)

        if not monitor.should_stop and not _past_afternoon_cutoff():
            _run_afternoon_phase(
                kis, bot, db, collector, analyzer, trader, monitor,
                sold_codes, consecutive_losses,
            )

    _send_daily_report(monitor, bot, db)
    return bot


def _run_afternoon_phase(
    kis: KISClient, bot: TelegramBot, db: Database,
    collector: MarketDataCollector, analyzer: AIAnalyzer,
    trader: Trader, monitor: PositionMonitor,
    sold_codes: set, consecutive_losses: int,
):
    logger.info("━━━ 오후 전략 시작 (%s ~ %s) ━━━",
                config.AFTERNOON_PHASE_START, config.AFTERNOON_PHASE_END)
    bot.send_message(
        f"🌙 <b>오후 전략 시작</b>\n"
        f"시간: {config.AFTERNOON_PHASE_START} ~ {config.AFTERNOON_PHASE_END}\n"
        f"포지션: {config.AFTERNOON_MAX_POSITION_PCT}% | "
        f"보유: {config.AFTERNOON_MAX_HOLD_MINUTES}분 | "
        f"사이클: 최대 {config.AFTERNOON_MAX_CYCLES}회"
    )

    cycle = 0
    while not _past_afternoon_cutoff() and cycle < config.AFTERNOON_MAX_CYCLES:
        cycle += 1
        logger.info("━━━ 오후 사이클 %d/%d 시작 ━━━", cycle, config.AFTERNOON_MAX_CYCLES)

        daily_pnl = _get_daily_pnl_pct(monitor)
        if daily_pnl <= config.DAILY_LOSS_LIMIT_PCT:
            logger.info("일일 손실한도 도달 (%.1f%%) — 오후 사이클 중단", daily_pnl)
            bot.send_message(f"🛑 일일 손실한도 도달 ({daily_pnl:.1f}%) — 오후 매매 중단")
            break
        if daily_pnl >= config.DAILY_PROFIT_TARGET_PCT:
            logger.info("일일 수익목표 달성 (%.1f%%) — 오후 사이클 중단", daily_pnl)
            bot.send_message(f"🎯 일일 수익목표 달성 ({daily_pnl:.1f}%) — 오후 매매 중단")
            break
        if consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            logger.info("%d연패 — 오후 매매 중단", consecutive_losses)
            bot.send_message(f"🛑 {consecutive_losses}연패 — 오후 매매 중단")
            break

        trades_before = len(monitor.trades_today)
        exit_reason = _run_one_cycle(
            cycle, kis, bot, db, collector, analyzer, trader, monitor, sold_codes,
            consecutive_losses=consecutive_losses,
            phase="afternoon",
        )
        for t in monitor.trades_today[trades_before:]:
            if "code" in t and t.get("pnl_amt", 0) < 0:
                sold_codes.add(t["code"])

        new_trades = monitor.trades_today[trades_before:]
        if new_trades:
            last_pnl = new_trades[-1].get("pnl_amt", 0)
            if last_pnl < 0:
                consecutive_losses += 1
            else:
                consecutive_losses = 0

        retryable = ("no_picks", "opening_filtered", "low_confidence", "positions_cleared")
        if exit_reason not in retryable:
            logger.info("오후 사이클 종료 (사유: %s) — 재시도 불가", exit_reason)
            break

        if monitor.should_stop:
            break

        if not _past_afternoon_cutoff() and cycle < config.AFTERNOON_MAX_CYCLES:
            cooldown = config.AFTERNOON_CYCLE_COOLDOWN
            if exit_reason in ("no_picks", "opening_filtered", "low_confidence"):
                cooldown = min(cooldown, 600)
                bot.send_message(
                    f"⏸ 오후 사이클 {cycle} — 진입 조건 미충족 ({exit_reason})\n"
                    f"{cooldown // 60}분 후 시장 재분석합니다."
                )
            else:
                bot.send_message(f"⏸ 오후 사이클 {cycle} 완료 — {cooldown // 60}분 쿨다운")
            logger.info("오후 쿨다운 %d초 (사유: %s)", cooldown, exit_reason)
            cooldown_end = time.time() + cooldown
            while time.time() < cooldown_end:
                try:
                    bot.process_updates(kis, monitor)
                except Exception:
                    pass
                if monitor.should_stop or _past_afternoon_cutoff():
                    break
                time.sleep(min(30, cooldown_end - time.time()))

    logger.info("━━━ 오후 전략 종료 ━━━")


def _run_one_cycle(
    cycle: int,
    kis: KISClient, bot: TelegramBot, db: Database,
    collector: MarketDataCollector, analyzer: AIAnalyzer,
    trader: Trader, monitor: PositionMonitor,
    sold_codes: set,
    consecutive_losses: int = 0,
    phase: str = "morning",
) -> str:
    logger.info("Phase 1 — 시장 데이터 수집")
    try:
        market_data = collector.fetch_market_data(phase=phase)
    except Exception as e:
        logger.error("시장 데이터 수집 실패: %s", e)
        bot.send_message(f"시장 데이터 수집 실패: {e}")
        return "error"

    phase_label = "오후" if phase == "afternoon" else "오전"
    logger.info("Phase 2 — 종목 심층 데이터 수집 (%s)", phase_label)
    try:
        enriched = collector.enrich_stocks(
            market_data["volume_ranking"],
            market_data["stock_news"],
            market_data["is_market_open"],
            phase=phase,
        )
    except Exception as e:
        logger.error("종목 데이터 enrichment 실패: %s", e)
        bot.send_message(f"종목 데이터 보강 실패: {e}")
        return "error"

    logger.info("enriched %d 종목", len(enriched))

    if not monitor.positions:
        momentum_result = _try_momentum_entry(
            kis, bot, db, collector, trader, monitor, sold_codes, market_data,
        )
        if momentum_result == "momentum_entered":
            logger.info("모멘텀 진입 성공 — 모니터링 전환")
            return _run_monitoring_loop(
                monitor, bot, kis, collector, analyzer, trader, sold_codes, phase="momentum",
            )
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
        logger.info("모멘텀 후보 없음 — 다음 사이클 대기")
        return "no_picks"

    if not enriched:
        logger.info("하드 필터 통과 종목 0개 — 이번 사이클 매매 비추천")
        bot.send_message("📊 하드 필터 통과 종목 없음 — 시장 조건 재확인 후 재시도합니다.")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
        return "no_picks"

    logger.info("Phase 3 — AI 분석 중")
    ai_used = True
    try:
        positions_info = [
            {"name": p["name"], "code": c, "remaining_qty": p["remaining_qty"]}
            for c, p in monitor.positions.items()
        ]
        analysis = analyzer.analyze(
            enriched_stocks=enriched,
            up_ranking=market_data["up_ranking"],
            down_ranking=market_data["down_ranking"],
            kospi_index=market_data["kospi_index"],
            kosdaq_index=market_data["kosdaq_index"],
            exchange_rate=market_data["exchange_rate"],
            is_market_open=market_data["is_market_open"],
            current_positions=positions_info or None,
        )
    except Exception as e:
        logger.error("AI 분석 실패 — 스코어 기반 fallback 진행: %s", e)
        bot.send_message(f"⚠️ AI 분석 실패 ({e}) — 스코어 기반 fallback 진행")
        ai_used = False
        top = enriched[0]
        cur_price = int(top.get("stck_prpr", 0))
        analysis = _build_score_fallback(top, cur_price, phase)

    logger.info("분석 완료 (AI=%s) — 추천: %s",
                ai_used, analysis.get("marketAssessment", {}).get("recommendation", "?"))
    if not config.DRY_RUN and not db.save_analysis(analysis):
        logger.warning("분석 DB 저장 실패")
        bot.send_message("⚠️ 분석 결과 DB 저장 실패")

    try:
        available_cash = kis.get_available_cash()
        logger.info("주문 가능 현금: %s원", f"{available_cash:,}")
    except Exception as e:
        logger.warning("현금 조회 실패, 설정값 사용: %s", e)
        available_cash = config.TOTAL_CAPITAL

    logger.info("Phase 4 — 텔레그램 분석 결과 전송")
    analysis["_kospi"] = market_data["kospi_index"]
    analysis["_kosdaq"] = market_data["kosdaq_index"]
    analysis["_exchange_rate"] = market_data["exchange_rate"]
    analysis["_ai_used"] = ai_used
    bot.send_analysis_result(analysis, available_cash)

    recommendation = analysis.get("marketAssessment", {}).get("recommendation", "")
    veto = analysis.get("vetoResult", {})
    picks = analysis.get("picks", [])

    enriched_score_map = {s.get("mksc_shrn_iscd", ""): s.get("score", 0) for s in enriched}
    for pick in picks:
        if "score" not in pick:
            pick["score"] = enriched_score_map.get(pick.get("symbol", ""), 0)

    if ai_used and veto and not veto.get("approved", True):
        veto_reason = veto.get("reason", "사유 없음")
        logger.info("AI veto 거부: %s", veto_reason)
        bot.send_message(f"🚫 AI Veto 거부: {veto_reason}")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
        return "no_picks"

    if recommendation == "매매비추천" or not picks:
        logger.info("매매 비추천 — 매수 없이 대기")
        bot.send_message("📊 매매 비추천 — 시장 조건 재확인 후 재시도합니다.")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
        return "no_picks"

    # 손절 후 다음 사이클: AI 신뢰도 기준 강화
    if consecutive_losses > 0:
        min_conf = config.MIN_CONFIDENCE_AFTER_LOSS
        low_conf = [p for p in picks if p.get("confidence", 0) < min_conf]
        if low_conf:
            names = ", ".join(p["name"] for p in low_conf)
            logger.info("손절 후 신뢰도 미달: %s (기준 %d%%)", names, min_conf)
            bot.send_message(
                f"⚠️ {consecutive_losses}연패 후 안전 모드 — "
                f"신뢰도 {min_conf}% 미만 종목 제외: {names}"
            )
            picks = [p for p in picks if p.get("confidence", 0) >= min_conf]
            if not picks:
                bot.send_message("신뢰도 기준 미달 — 이번 사이클 매수 스킵")
                if monitor.positions:
                    return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
                return "low_confidence"

    # ── Phase 5 — 오프닝 검증 (실시간 안전 필터) ──
    logger.info("Phase 5 — 오프닝 검증 (실시간 데이터 확인)")
    validated_picks = []
    for pick in picks:
        symbol = pick["symbol"]
        name = pick["name"]
        try:
            price_data = kis.get_current_price(symbol)
            cur_price = price_data["price"]
            change_pct = price_data["change_pct"]
            volume = price_data["volume"]
            logger.info(
                "%s 오프닝: %s원 (%+.1f%%), 거래량 %s",
                name, f"{cur_price:,}", change_pct, f"{volume:,}",
            )
        except Exception as e:
            logger.warning("%s 현재가 조회 실패 — 검증 스킵: %s", name, e)
            bot.send_message(f"⚠️ {name} 현재가 조회 실패 — 매수 스킵")
            continue

        # 갭다운 필터: 전일 대비 급락 시 스킵
        if change_pct < config.OPENING_MAX_GAP_DOWN_PCT:
            msg = (
                f"❌ {name} 오프닝 탈락 — "
                f"갭다운 {change_pct:+.1f}% (한도 {config.OPENING_MAX_GAP_DOWN_PCT}%)"
            )
            logger.info(msg)
            bot.send_message(msg)
            continue

        # 갭업 필터: 이미 너무 올라간 경우 추격매수 방지
        if change_pct > config.OPENING_MAX_GAP_UP_PCT:
            msg = (
                f"❌ {name} 오프닝 탈락 — "
                f"갭업 {change_pct:+.1f}% (한도 +{config.OPENING_MAX_GAP_UP_PCT}%) 추격매수 방지"
            )
            logger.info(msg)
            bot.send_message(msg)
            continue

        # 거래량 필터: 유동성 부족 시 스킵
        if volume < config.OPENING_MIN_VOLUME:
            msg = (
                f"❌ {name} 오프닝 탈락 — "
                f"거래량 {volume:,} < 최소 {config.OPENING_MIN_VOLUME:,}"
            )
            logger.info(msg)
            bot.send_message(msg)
            continue

        # 검증 통과
        logger.info("%s 오프닝 검증 통과 ✓", name)
        validated_picks.append(pick)

    if not validated_picks:
        bot.send_message("📊 오프닝 검증 결과: 모든 후보 탈락 — 매수 없이 모니터링")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
        return "opening_filtered"

    passed_names = ", ".join(p["name"] for p in validated_picks)
    bot.send_message(
        f"✅ 오프닝 검증 통과: {passed_names}\n"
        f"({len(validated_picks)}/{len(picks)}개 통과) — 매수 진행"
    )

    # ── Phase 7 — 매수 주문 실행 ──
    logger.info("Phase 7 — 매수 주문 실행")
    orders = trader.calculate_orders(validated_picks, available_cash, sold_codes, phase=phase)
    if not orders:
        bot.send_message("주문 가능한 종목이 없습니다.")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
        return "no_orders"
    bot.send_buy_orders(orders)
    results = trader.execute_buy_orders(orders)
    success_orders = [r for r in results if r["success"]]
    fail_orders = [r for r in results if not r["success"]]
    if fail_orders:
        fail_msg = "\n".join(f"  {o['name']}: {o['message']}" for o in fail_orders)
        bot.send_message(f"⚠️ 매수 실패:\n{fail_msg}")
    if not success_orders:
        bot.send_message("모든 매수 주문 실패.")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)
        return "all_failed"
    order_map = {o["stock_code"]: o for o in success_orders}

    max_attempts = max(config.BUY_CONFIRM_TIMEOUT // 15, 4)
    logger.info("Phase 8 — 체결 대기 (15초 간격, 최대 %d회)", max_attempts)
    fills = []
    for attempt in range(max_attempts):
        time.sleep(15)
        result = trader.check_fills(success_orders)
        if result is None:
            logger.warning("체결 조회 API 오류 — 재시도 (시도 %d/%d)", attempt + 1, max_attempts)
            continue
        fills = result
        filled_names = [f["name"] for f in fills]
        logger.info("체결 %d/%d — %s (시도 %d/%d)",
                     len(fills), len(success_orders),
                     ", ".join(filled_names) or "없음", attempt + 1, max_attempts)
        if len(fills) >= len(success_orders):
            break

    if fills:
        bot.send_fill_confirmation(fills)
        for f in fills:
            matching_order = order_map.get(f["stock_code"])
            if matching_order:
                fill_price = f["price"]
                order_price = matching_order["price"]
                buy_slippage_pct = 0.0
                if fill_price > 0 and order_price > 0:
                    buy_slippage_pct = (fill_price - order_price) / order_price * 100
                    fill_dev = abs(buy_slippage_pct)
                    if fill_dev > config.MAX_ENTRY_DEVIATION_PCT:
                        sign = "↑" if fill_price > order_price else "↓"
                        msg = (
                            f"⚠️ {f['name']} 체결가 괴리 경고\n"
                            f"주문가: {order_price:,}원 → 체결가: {fill_price:,}원 ({fill_dev:.1f}%{sign})\n"
                            f"시장 급변동 — 모니터링 주의"
                        )
                        bot.send_message(msg)
                        logger.warning("%s 체결가 괴리 %.1f%% (주문 %s → 체결 %s)",
                                       f["name"], fill_dev, f"{order_price:,}", f"{fill_price:,}")
                    logger.info("%s 슬리피지: %+.3f%% (주문 %s → 체결 %s)",
                                f["name"], buy_slippage_pct, f"{order_price:,}", f"{fill_price:,}")
                try:
                    fresh = kis.get_current_price(f["stock_code"])
                    fresh_price = fresh["price"]
                    if fresh_price > 0 and fill_price > 0:
                        cur_vs_fill = (fresh_price - fill_price) / fill_price * 100
                        if cur_vs_fill < -config.MIN_STOP_LOSS_PCT:
                            msg = (
                                f"🚨 {f['name']} 체결 직후 급락 감지\n"
                                f"체결가: {fill_price:,}원 → 현재가: {fresh_price:,}원 ({cur_vs_fill:.1f}%)\n"
                                f"손절선 이미 하회 — 즉시 매도 예정"
                            )
                            bot.send_message(msg)
                            logger.warning("%s 체결 직후 현재가 이미 손절선 하회 (%.1f%%)", f["name"], cur_vs_fill)
                except Exception as e:
                    logger.warning("%s 체결 후 현재가 확인 실패: %s", f["name"], e)

                adjusted_stop = _recalc_stop_loss(
                    fill_price, order_price, matching_order["stop_loss"],
                )
                monitor.add_position(
                    stock_code=f["stock_code"],
                    name=f["name"],
                    quantity=f["quantity"],
                    entry_price=fill_price,
                    target1=matching_order["target1"],
                    target2=matching_order["target2"],
                    stop_loss=adjusted_stop,
                    sell_strategy=matching_order.get("sell_strategy"),
                    buy_slippage_pct=buy_slippage_pct,
                    score=matching_order.get("score", 0),
                    phase=phase,
                )

    pending = []
    if not config.DRY_RUN:
        for pq_attempt in range(3):
            try:
                pending = kis.get_pending_orders()
                break
            except Exception as e:
                logger.error("미체결 조회 실패 (시도 %d/3): %s", pq_attempt + 1, e)
                if pq_attempt < 2:
                    time.sleep(2)
                else:
                    bot.send_message("⚠️ 미체결 조회 3회 실패 — /balance 로 수동 확인 필요")

    if pending:
        logger.info("Phase 8.5 — 미체결 %d건 재분석", len(pending))
        bot.send_message(
            f"⏳ 미체결 {len(pending)}건 — 재분석 진행\n"
            + "\n".join(f"  {p['name']} 잔여 {p['remaining_qty']}주 × {p['order_price']:,}원" for p in pending)
        )

        for p in pending:
            orig = order_map.get(p["stock_code"], {})
            p["reason"] = orig.get("reason", "AI 추천 매수")
            p["target1"] = orig.get("target1", 0)
            p["target2"] = orig.get("target2", 0)
            p["stop_loss"] = orig.get("stop_loss", 0)
            p["sell_strategy"] = orig.get("sell_strategy")

        cancelled = trader.cancel_unfilled_orders(pending)

        if cancelled:
            time.sleep(2)
            retry_results = trader.retry_with_reanalysis(cancelled, analyzer)

            for r in retry_results:
                if r.get("retried") and r.get("success"):
                    time.sleep(10)
                    retry_fills = trader.check_fills([r])
                    for rf in retry_fills:
                        adjusted_stop = _recalc_stop_loss(
                            rf["price"],
                            r.get("retry_price", rf["price"]),
                            r.get("stop_loss", 0),
                        )
                        monitor.add_position(
                            stock_code=rf["stock_code"],
                            name=rf["name"],
                            quantity=rf["quantity"],
                            entry_price=rf["price"],
                            target1=r.get("target1", 0),
                            target2=r.get("target2", 0),
                            stop_loss=adjusted_stop,
                            sell_strategy=r.get("sell_strategy"),
                        )
    elif not fills:
        bot.send_message("⚠️ 체결 확인 불가 — /balance 명령어로 수동 확인해주세요.")

    _try_reinvest(kis, bot, collector, analyzer, trader, monitor, sold_codes, phase=phase)

    logger.info("Phase 9 — 모니터링 시작")
    return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes, phase=phase)


def _run_monitoring_loop(
    monitor: PositionMonitor, bot: TelegramBot, kis: KISClient,
    collector=None, analyzer=None, trader=None, sold_codes=None,
    phase: str = "morning",
) -> str:
    logger.info("모니터링 루프 시작 — 포지션 %d개", len(monitor.positions))
    bot.send_message(f"🔍 모니터링 시작 — {len(monitor.positions)}개 포지션")
    last_reinvest = 0

    while True:
        n = now_kst()

        if n.hour >= 15 and n.minute >= 35:
            logger.info("장 마감 — 모니터링 종료")
            return "market_close"

        if monitor.should_stop:
            logger.info("사용자 /stop 명령 — 모니터링 종료")
            return "user_stop"

        if not monitor.positions:
            logger.info("모든 포지션 청산 — 모니터링 종료")
            bot.send_message("모든 포지션 청산 완료 — 모니터링 종료")
            return "positions_cleared"

        if is_market_hours():
            trades_before = len(monitor.trades_today)
            try:
                monitor.check_positions()
            except Exception as e:
                logger.error("포지션 체크 오류: %s", e)
            if len(monitor.trades_today) > trades_before:
                for t in monitor.trades_today[trades_before:]:
                    if t.get("code") and sold_codes is not None and t.get("pnl_amt", 0) < 0:
                        sold_codes.add(t["code"])
                last_reinvest = 0

        try:
            bot.process_updates(kis, monitor)
        except Exception as e:
            logger.error("텔레그램 업데이트 처리 오류: %s", e)

        if collector and analyzer and trader and is_market_hours():
            manual = bot._reinvest_requested
            if manual:
                bot._reinvest_requested = False
            cutoff_fn = _past_afternoon_cutoff if phase == "afternoon" else _past_entry_cutoff
            if manual or (time.time() - last_reinvest >= config.REINVEST_CHECK_INTERVAL
                          and not cutoff_fn()):
                last_reinvest = time.time()
                _try_reinvest(kis, bot, collector, analyzer, trader, monitor, sold_codes or set(), phase=phase)

        time.sleep(config.CHECK_INTERVAL)


def _send_daily_report(monitor: PositionMonitor, bot: TelegramBot, db: Database | None = None):
    """일일 리포트 전송 + DB 저장."""
    logger.info("일일 리포트 생성")
    summary = monitor.get_daily_summary()
    bot.send_daily_report(summary)

    if db:
        remaining = [
            {"code": code, "name": pos["name"], "qty": pos["remaining_qty"], "entry": pos["entry_price"]}
            for code, pos in monitor.positions.items()
        ]
        if not db.save_daily_report(monitor.trades_today, remaining):
            logger.warning("일일 리포트 DB 저장 실패")
            bot.send_message("⚠️ 일일 리포트 DB 저장 실패")

    logger.info("일일 리포트 전송 완료")
    logger.info("Day Trader 종료 — %s", now_kst().strftime("%H:%M"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _sleep_until_midnight():
    n = now_kst()
    tomorrow = (n + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    seconds = (tomorrow - n).total_seconds()
    logger.info("다음 사이클까지 %.0f초 대기 (00:00 KST)", seconds)
    time.sleep(max(seconds, 60))


if __name__ == "__main__":
    import argparse
    _parser = argparse.ArgumentParser(description="Day Trader")
    _parser.add_argument("--dry-run", action="store_true", help="모의투자 모드")
    _args = _parser.parse_args()
    if _args.dry_run:
        config.DRY_RUN = True

    while True:
        _bot = None
        try:
            _bot = run_daily_cycle()
        except KeyboardInterrupt:
            logger.info("사용자 중단 (Ctrl+C)")
            break
        except Exception as e:
            logger.exception("예상치 못한 오류: %s", e)
            try:
                TelegramBot().send_message(f"❌ Day Trader 오류 발생: {e}")
            except Exception:
                pass
        if config.DRY_RUN:
            logger.info("모의투자 1회 완료 — 종료")
            break
        _sleep_until_midnight()
        if _bot:
            _bot.stop_polling()
