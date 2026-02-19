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


def run_daily_cycle():
    setup_logging()
    logger.info("=" * 50)
    logger.info("Day Trader 시작 — %s", now_kst().strftime("%Y.%m.%d %H:%M"))
    logger.info("=" * 50)

    # --- Init ---
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

    # --- Weekend check ---
    if is_weekend():
        bot.send_message("주말입니다. 월요일에 다시 시작합니다.")
        logger.info("주말 — 종료")
        return

    bot.send_message(f"🔔 Day Trader 시작 ({now_kst().strftime('%Y.%m.%d %H:%M')})")

    # --- Resume: 이미 포지션이 있으면 모니터링으로 직행 ---
    if monitor.positions and past_analysis_time():
        logger.info("기존 포지션 %d개 감지 — 모니터링 재개", len(monitor.positions))
        bot.send_message(
            f"기존 포지션 {len(monitor.positions)}개 감지 — 모니터링 재개\n"
            + "\n".join(f"  {p['name']} {p['remaining_qty']}주" for p in monitor.positions.values())
        )
        _run_monitoring_loop(monitor, bot, kis)
        _send_daily_report(monitor, bot, db)
        return

    # --- Phase 0: Wait until analysis time ---
    if not past_analysis_time():
        wait_until(config.ANALYSIS_TIME, bot, kis, monitor)

    # --- Phase 1: Fetch market data ---
    logger.info("Phase 1 — 시장 데이터 수집")
    try:
        market_data = collector.fetch_market_data()
    except Exception as e:
        logger.error("시장 데이터 수집 실패: %s", e)
        bot.send_message(f"시장 데이터 수집 실패: {e}")
        return

    # --- Phase 2: Enrich top stocks ---
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
        return

    logger.info("enriched %d 종목", len(enriched))

    # --- Phase 3: AI analysis ---
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
        return

    logger.info("AI 분석 완료 — 추천: %s", analysis.get("marketAssessment", {}).get("recommendation", "?"))
    db.save_analysis(analysis)

    # --- Phase 4: Send analysis to Telegram ---
    logger.info("Phase 4 — 텔레그램 분석 결과 전송")
    analysis["_kospi"] = market_data["kospi_index"]
    analysis["_kosdaq"] = market_data["kosdaq_index"]
    analysis["_exchange_rate"] = market_data["exchange_rate"]
    bot.send_analysis_result(analysis, config.TOTAL_CAPITAL)

    # --- Phase 5: Check recommendation ---
    recommendation = analysis.get("marketAssessment", {}).get("recommendation", "")
    picks = analysis.get("picks", [])

    if recommendation == "매매비추천" or not picks:
        logger.info("매매 비추천 — 매수 없이 모니터링 모드")
        bot.send_message("오늘은 매매 비추천입니다. 기존 포지션만 모니터링합니다.")
        if monitor.positions:
            _run_monitoring_loop(monitor, bot, kis)
        _send_daily_report(monitor, bot, db)
        return

    # --- Phase 6: Wait for buy confirmation ---
    logger.info("Phase 6 — 매수 확인 대기 (최대 %d초)", config.BUY_CONFIRM_TIMEOUT)
    confirmed = bot.wait_for_buy_confirmation(config.BUY_CONFIRM_TIMEOUT)
    if not confirmed:
        logger.info("매수 취소/시간초과")
        if monitor.positions:
            _run_monitoring_loop(monitor, bot, kis)
        _send_daily_report(monitor, bot, db)
        return

    # --- Phase 7: Calculate & execute buy orders ---
    logger.info("Phase 7 — 매수 주문 실행")
    orders = trader.calculate_orders(picks, config.TOTAL_CAPITAL)
    if not orders:
        bot.send_message("주문 가능한 종목이 없습니다.")
        _send_daily_report(monitor, bot, db)
        return

    bot.send_buy_orders(orders)
    results = trader.execute_buy_orders(orders)

    success_orders = [r for r in results if r["success"]]
    fail_orders = [r for r in results if not r["success"]]

    if fail_orders:
        fail_msg = "\n".join(f"  {o['name']}: {o['message']}" for o in fail_orders)
        bot.send_message(f"⚠️ 매수 실패:\n{fail_msg}")

    if not success_orders:
        bot.send_message("모든 매수 주문 실패. 모니터링 모드로 전환합니다.")
        if monitor.positions:
            _run_monitoring_loop(monitor, bot, kis)
        _send_daily_report(monitor, bot, db)
        return

    # --- Phase 8: Wait for fills & add to monitor ---
    logger.info("Phase 8 — 체결 대기")
    time.sleep(5)  # 체결 대기

    # 최대 3번 체결 확인 시도 (5초 간격)
    fills = []
    for attempt in range(3):
        fills = trader.check_fills(orders)
        if fills:
            break
        logger.info("체결 대기 중... (시도 %d/3)", attempt + 1)
        time.sleep(5)

    if fills:
        bot.send_fill_confirmation(fills)
        for f in fills:
            # 매칭되는 주문에서 target/stop 정보 가져오기
            matching_order = next(
                (o for o in orders if o["stock_code"] == f["stock_code"]), None
            )
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
    else:
        bot.send_message("⚠️ 체결 확인 불가 — 수동으로 확인해주세요. /balance 명령어로 확인 가능합니다.")
        # 주문은 넣었으니 모니터링은 계속 (체결 확인 실패해도 포지션 수동 추가 가능)

    # --- Phase 9: Monitoring loop ---
    logger.info("Phase 9 — 모니터링 시작")
    _run_monitoring_loop(monitor, bot, kis)

    # --- Phase 10: Daily report ---
    _send_daily_report(monitor, bot, db)


def _run_monitoring_loop(monitor: PositionMonitor, bot: TelegramBot, kis: KISClient):
    """장 마감까지 포지션 모니터링 + 텔레그램 명령 처리."""
    logger.info("모니터링 루프 시작 — 포지션 %d개", len(monitor.positions))
    bot.send_message(f"🔍 모니터링 시작 — {len(monitor.positions)}개 포지션")

    while True:
        n = now_kst()

        # 장 마감 체크 (15:35 이후 종료)
        if n.hour >= 15 and n.minute >= 35:
            logger.info("장 마감 — 모니터링 종료")
            break

        # /stop 명령 체크
        if monitor.should_stop:
            logger.info("사용자 /stop 명령 — 모니터링 종료")
            break

        # 포지션 없으면 종료
        if not monitor.positions:
            logger.info("모든 포지션 청산 — 모니터링 종료")
            bot.send_message("모든 포지션 청산 완료 — 모니터링 종료")
            break

        # 장중인 경우에만 포지션 체크
        if is_market_hours():
            try:
                monitor.check_positions()
            except Exception as e:
                logger.error("포지션 체크 오류: %s", e)

        # 텔레그램 명령 처리
        try:
            bot.process_updates(kis, monitor)
        except Exception as e:
            logger.error("텔레그램 업데이트 처리 오류: %s", e)

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
        try:
            run_daily_cycle()
        except KeyboardInterrupt:
            logger.info("사용자 중단 (Ctrl+C)")
            break
        except Exception as e:
            logger.exception("예상치 못한 오류: %s", e)
            try:
                bot = TelegramBot()
                bot.send_message(f"❌ Day Trader 오류 발생: {e}")
            except Exception:
                pass
        _sleep_until_midnight()
