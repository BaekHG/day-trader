"""
Day Trader — 자동 단타 매매 시스템
매일 08:40 분석 → 텔레그램 확인 → 매수 → 모니터링 → 매도 → 리포트
"""

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
from trader import Trader

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


def _past_entry_cutoff() -> bool:
    hh, mm = map(int, config.NO_NEW_ENTRY_AFTER.split(":"))
    n = now_kst()
    return n.hour > hh or (n.hour == hh and n.minute >= mm)


def _try_reinvest(
    kis: KISClient, bot: TelegramBot, collector: MarketDataCollector,
    analyzer: AIAnalyzer, trader: Trader, monitor: PositionMonitor,
    sold_codes: set,
) -> None:
    if _past_entry_cutoff():
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
        mdata = collector.fetch_market_data()
        enr = collector.enrich_stocks(
            mdata["volume_ranking"], mdata["stock_news"], mdata["is_market_open"],
        )
        anal = analyzer.analyze(
            enriched_stocks=enr, up_ranking=mdata["up_ranking"],
            down_ranking=mdata["down_ranking"], kospi_index=mdata["kospi_index"],
            kosdaq_index=mdata["kosdaq_index"], exchange_rate=mdata["exchange_rate"],
            is_market_open=mdata["is_market_open"],
        )
        rec = anal.get("marketAssessment", {}).get("recommendation", "")
        if rec == "매매비추천":
            bot.send_message("재투자 분석: 매매비추천 — 패스")
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
            new_fills = trader.check_fills(new_success)
            if len(new_fills) >= len(new_success):
                break
        if new_fills:
            bot.send_fill_confirmation(new_fills)
            for nf in new_fills:
                mo = new_map.get(nf["stock_code"])
                if mo:
                    monitor.add_position(
                        stock_code=nf["stock_code"], name=nf["name"],
                        quantity=nf["quantity"], entry_price=nf["price"],
                        target1=mo["target1"], target2=mo["target2"],
                        stop_loss=mo["stop_loss"],
                        sell_strategy=mo.get("sell_strategy"),
                    )
                    sold_codes.add(nf["stock_code"])
    except Exception as e:
        logger.error("잔여 현금 재투자 실패: %s", e)


def _get_daily_pnl_pct(monitor: PositionMonitor) -> float:
    total_pnl = sum(t.get("pnl_amt", 0) for t in monitor.trades_today)
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

    if is_weekend():
        bot.send_message("주말입니다. 월요일에 다시 시작합니다.")
        logger.info("주말 — 종료")
        return bot

    bot.send_message(f"🔔 Day Trader 시작 ({now_kst().strftime('%Y.%m.%d %H:%M')})")

    sold_codes: set[str] = set()
    sold_codes.update(t["code"] for t in monitor.trades_today if "code" in t)

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

    if not past_analysis_time():
        wait_until(config.ANALYSIS_TIME, bot, kis, monitor)

    for cycle in range(config.MAX_CYCLES):
        logger.info("━━━ 사이클 %d/%d 시작 ━━━", cycle + 1, config.MAX_CYCLES)

        if _past_entry_cutoff():
            logger.info("신규 진입 마감 (%s) — 사이클 중단", config.NO_NEW_ENTRY_AFTER)
            break

        daily_pnl = _get_daily_pnl_pct(monitor)
        if daily_pnl <= config.DAILY_LOSS_LIMIT_PCT:
            logger.info("일일 손실한도 도달 (%.1f%%) — 사이클 중단", daily_pnl)
            bot.send_message(f"🛑 일일 손실한도 도달 ({daily_pnl:.1f}%) — 매매 중단")
            break
        if daily_pnl >= config.DAILY_PROFIT_TARGET_PCT:
            logger.info("일일 수익목표 달성 (%.1f%%) — 사이클 중단", daily_pnl)
            bot.send_message(f"🎯 일일 수익목표 달성 ({daily_pnl:.1f}%) — 매매 중단")
            break

        exit_reason = _run_one_cycle(
            cycle, kis, bot, db, collector, analyzer, trader, monitor, sold_codes,
        )
        sold_codes.update(t["code"] for t in monitor.trades_today if "code" in t)

        if exit_reason != "positions_cleared":
            break

        if cycle < config.MAX_CYCLES - 1:
            if _past_entry_cutoff():
                logger.info("다음 사이클 진입 마감 — 종료")
                break
            logger.info("쿨다운 %d초 시작", config.CYCLE_COOLDOWN)
            bot.send_message(f"⏸ 사이클 {cycle + 1} 완료 — {config.CYCLE_COOLDOWN // 60}분 쿨다운")
            cooldown_end = time.time() + config.CYCLE_COOLDOWN
            while time.time() < cooldown_end:
                try:
                    bot.process_updates(kis, monitor)
                except Exception:
                    pass
                if monitor.should_stop:
                    break
                time.sleep(min(30, cooldown_end - time.time()))
            if monitor.should_stop:
                break

    _send_daily_report(monitor, bot, db)
    return bot


def _run_one_cycle(
    cycle: int,
    kis: KISClient, bot: TelegramBot, db: Database,
    collector: MarketDataCollector, analyzer: AIAnalyzer,
    trader: Trader, monitor: PositionMonitor,
    sold_codes: set,
) -> str:
    logger.info("Phase 1 — 시장 데이터 수집")
    try:
        market_data = collector.fetch_market_data()
    except Exception as e:
        logger.error("시장 데이터 수집 실패: %s", e)
        bot.send_message(f"시장 데이터 수집 실패: {e}")
        return "error"

    logger.info("Phase 2 — 종목 심층 데이터 수집")
    try:
        enriched = collector.enrich_stocks(
            market_data["volume_ranking"],
            market_data["stock_news"],
            market_data["is_market_open"],
        )
    except Exception as e:
        logger.error("종목 데이터 enrichment 실패: %s", e)
        bot.send_message(f"종목 데이터 보강 실패: {e}")
        return "error"

    logger.info("enriched %d 종목", len(enriched))

    logger.info("Phase 3 — AI 분석 중")
    try:
        analysis = analyzer.analyze(
            enriched_stocks=enriched,
            up_ranking=market_data["up_ranking"],
            down_ranking=market_data["down_ranking"],
            kospi_index=market_data["kospi_index"],
            kosdaq_index=market_data["kosdaq_index"],
            exchange_rate=market_data["exchange_rate"],
            is_market_open=market_data["is_market_open"],
        )
    except Exception as e:
        logger.error("AI 분석 실패: %s", e)
        bot.send_message(f"AI 분석 실패: {e}")
        return "error"

    logger.info("AI 분석 완료 — 추천: %s", analysis.get("marketAssessment", {}).get("recommendation", "?"))
    db.save_analysis(analysis)

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
    bot.send_analysis_result(analysis, available_cash)

    recommendation = analysis.get("marketAssessment", {}).get("recommendation", "")
    picks = analysis.get("picks", [])

    if recommendation == "매매비추천" or not picks:
        logger.info("매매 비추천 — 매수 없이 모니터링 모드")
        bot.send_message("매매 비추천 — 기존 포지션만 모니터링합니다.")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes)
        return "no_picks"

    bot.send_message(f"🔄 사이클 {cycle + 1} — 자동 매수 진행")

    logger.info("Phase 7 — 매수 주문 실행")
    orders = trader.calculate_orders(picks, available_cash, sold_codes)
    if not orders:
        bot.send_message("주문 가능한 종목이 없습니다.")
        if monitor.positions:
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes)
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
            return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes)
        return "all_failed"

    logger.info("Phase 8 — 체결 대기 (15초 간격, 최대 3분)")
    order_map = {o["stock_code"]: o for o in success_orders}
    fills = []
    for attempt in range(12):
        time.sleep(15)
        fills = trader.check_fills(success_orders)
        filled_names = [f["name"] for f in fills]
        logger.info("체결 %d/%d — %s (시도 %d/12)",
                     len(fills), len(success_orders),
                     ", ".join(filled_names) or "없음", attempt + 1)
        if len(fills) >= len(success_orders):
            break

    if fills:
        bot.send_fill_confirmation(fills)
        for f in fills:
            matching_order = order_map.get(f["stock_code"])
            if matching_order:
                monitor.add_position(
                    stock_code=f["stock_code"],
                    name=f["name"],
                    quantity=f["quantity"],
                    entry_price=f["price"],
                    target1=matching_order["target1"],
                    target2=matching_order["target2"],
                    stop_loss=matching_order["stop_loss"],
                    sell_strategy=matching_order.get("sell_strategy"),
                )

    try:
        pending = kis.get_pending_orders()
    except Exception as e:
        logger.error("미체결 조회 실패: %s", e)
        pending = []

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
                        monitor.add_position(
                            stock_code=rf["stock_code"],
                            name=rf["name"],
                            quantity=rf["quantity"],
                            entry_price=rf["price"],
                            target1=r.get("target1", 0),
                            target2=r.get("target2", 0),
                            stop_loss=r.get("stop_loss", 0),
                            sell_strategy=r.get("sell_strategy"),
                        )
    elif not fills:
        bot.send_message("⚠️ 체결 확인 불가 — /balance 명령어로 수동 확인해주세요.")

    _try_reinvest(kis, bot, collector, analyzer, trader, monitor, sold_codes)

    logger.info("Phase 9 — 모니터링 시작")
    return _run_monitoring_loop(monitor, bot, kis, collector, analyzer, trader, sold_codes)


def _run_monitoring_loop(
    monitor: PositionMonitor, bot: TelegramBot, kis: KISClient,
    collector=None, analyzer=None, trader=None, sold_codes=None,
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
                    if t.get("code") and t["code"] not in monitor.positions and sold_codes is not None:
                        sold_codes.add(t["code"])
                last_reinvest = 0

        try:
            bot.process_updates(kis, monitor)
        except Exception as e:
            logger.error("텔레그램 업데이트 처리 오류: %s", e)

        if (collector and analyzer and trader
                and time.time() - last_reinvest >= config.REINVEST_CHECK_INTERVAL
                and not _past_entry_cutoff()
                and is_market_hours()):
            last_reinvest = time.time()
            _try_reinvest(kis, bot, collector, analyzer, trader, monitor, sold_codes or set())

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
        db.save_daily_report(monitor.trades_today, remaining)

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
        _sleep_until_midnight()
        if _bot:
            _bot.stop_polling()
