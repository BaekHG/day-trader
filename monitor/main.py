"""
Day Trader — 자동 단타 매매 시스템
매일 08:40 분석 → 텔레그램 확인 → 매수 → 모니터링 → 매도 → 리포트
"""
from __future__ import annotations

import logging
import os
import json
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

def _is_early_morning() -> bool:
    """장 초반 모드 (09:00 ~ 09:00+EARLY_MORNING_MINUTES)."""
    now = now_kst()
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    return now <= market_open + timedelta(minutes=config.EARLY_MORNING_MINUTES)


# 모멘텀 스캔 요약 (사이클 메시지에서 참조)
_last_momentum_scan_summary = ""
_morning_top_movers: list[dict] = []  # 오전 급등주 추적
_MOVERS_FILE = os.path.join(os.path.dirname(__file__) or '.', '.morning_top_movers.json')


def _save_morning_top_movers():
    """오전 급등주 데이터를 파일에 저장 (재시작 복구용)."""
    try:
        with open(_MOVERS_FILE, 'w') as f:
            json.dump({'date': now_kst().strftime('%Y-%m-%d'), 'movers': _morning_top_movers}, f, ensure_ascii=False)
    except Exception as e:
        logger.warning('급등주 저장 실패: %s', e)


def _load_morning_top_movers():
    """파일에서 오전 급등주 데이터 복구. 당일 데이터만 로드."""
    global _morning_top_movers
    try:
        with open(_MOVERS_FILE, 'r') as f:
            data = json.load(f)
        if data.get('date') == now_kst().strftime('%Y-%m-%d'):
            _morning_top_movers = data.get('movers', [])
            logger.info('오전 급등주 복구: %d종목', len(_morning_top_movers))
        else:
            logger.info('급등주 데이터 날짜 불일치 — 무시')
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning('급등주 복구 실패: %s', e)

# --- 불장 모드 (Market Boost) 상태 ---
_boost_state = {
    "active": False,
    "sentiment": "neutral",
    "boost_themes": [],
    "hurt_themes": [],
    "confidence": 0,
    "reason": "",
}


def _run_sentiment_check(naver_news, analyzer, bot):
    """08:55 뉴스 센티먼트 분석 (장 시작 전 사전 판단)."""
    global _boost_state
    headlines = naver_news.get_market_news()
    if not headlines:
        bot.send_message("📰 시장 뉴스 수집 실패 — 센티먼트 분석 스킵")
        return
    result = analyzer.analyze_market_sentiment(headlines)
    _boost_state["sentiment"] = result.get("sentiment", "neutral")
    _boost_state["boost_themes"] = result.get("boost_themes", [])
    _boost_state["hurt_themes"] = result.get("hurt_themes", [])
    _boost_state["confidence"] = result.get("confidence", 0)
    # confidence 70 미만이면 neutral 강제 — 저신뢰 판단으로 부스트 방지
    if _boost_state["confidence"] < 70 and _boost_state["sentiment"] != "neutral":
        logger.info("센티먼트 신뢰도 부족 (%d < 70) — %s → neutral 강제",
                    _boost_state["confidence"], _boost_state["sentiment"])
        _boost_state["sentiment"] = "neutral"
    summary = result.get("summary", "")

    sentiment = _boost_state["sentiment"]
    conf = _boost_state["confidence"]
    themes = ", ".join(_boost_state["boost_themes"][:5]) or "없음"
    hurt = ", ".join(_boost_state["hurt_themes"][:5]) or "없음"
    emoji = "🔥" if sentiment == "bullish" else "❄️" if sentiment == "bearish" else "➖"
    bot.send_message(
        f"{emoji} <b>시장 센티먼트 분석</b>\n\n"
        f"판단: {sentiment} (신뢰도 {conf}%)\n"
        f"수혜테마: {themes}\n"
        f"피해테마: {hurt}\n"
        f"요약: {summary}"
    )
    logger.info("센티먼트: %s (conf=%d) themes=%s hurt=%s",
                sentiment, conf, themes, hurt)


def _confirm_boost_from_index(market_data: dict, bot):
    """KOSPI/KOSDAQ 지표로 부스트 최종 확정.

    뉴스 bullish + 지표 강세 → 확정
    뉴스 bullish + 지표 약세 → 평시
    뉴스 neutral + 지표 강세 → 확정 (돈은 안 거짓말)
    """
    global _boost_state
    kospi = market_data.get("kospi_index", {})
    kosdaq = market_data.get("kosdaq_index", {})
    kospi_chg = float(kospi.get("change_rate", "0") if isinstance(kospi, dict) else "0")
    kosdaq_chg = float(kosdaq.get("change_rate", "0") if isinstance(kosdaq, dict) else "0")

    index_strong = (
        kospi_chg >= config.BOOST_KOSPI_THRESHOLD
        or kosdaq_chg >= config.BOOST_KOSDAQ_THRESHOLD
    )
    sentiment = _boost_state["sentiment"]

    if sentiment == "bullish" and index_strong:
        _boost_state["active"] = True
        _boost_state["reason"] = f"뉴스 bullish + 지표 강세 (KOSPI {kospi_chg:+.1f}%, KOSDAQ {kosdaq_chg:+.1f}%)"
    elif sentiment == "neutral" and index_strong:
        _boost_state["active"] = True
        _boost_state["reason"] = f"지표 강세 감지 (KOSPI {kospi_chg:+.1f}%, KOSDAQ {kosdaq_chg:+.1f}%) — 돈은 안 거짓말"
    else:
        _boost_state["active"] = False
        _boost_state["reason"] = f"평시 유지 (sentiment={sentiment}, KOSPI {kospi_chg:+.1f}%, KOSDAQ {kosdaq_chg:+.1f}%)"

    if _boost_state["active"]:
        bot.send_message(
            f"🚀 <b>불장 모드 확정!</b>\n\n"
            f"사유: {_boost_state['reason']}\n"
            f"MAX_POSITION: {config.BOOST_MAX_POSITION_PCT}% | "
            f"MIN_SCORE: {config.BOOST_MOMENTUM_MIN_SCORE} | "
            f"STOP_LOSS: -{config.BOOST_STOP_LOSS_PCT}%\n"
            f"NO_NEW_ENTRY: {config.BOOST_NO_NEW_ENTRY_AFTER} | "
            f"COOLDOWN: {config.BOOST_CYCLE_COOLDOWN}s"
        )
    else:
        bot.send_message(f"⚖️ 평시 모드 — {_boost_state['reason']}")
    logger.info("부스트 가부: %s — %s", _boost_state['active'], _boost_state['reason'])


def _try_momentum_entry(
    kis: KISClient, bot: TelegramBot, db: Database,
    collector: MarketDataCollector, trader: Trader,
    monitor: PositionMonitor, sold_codes: set,
    market_data: dict,
    consecutive_losses: int = 0,
) -> str | None:
    global _last_momentum_scan_summary
    _last_momentum_scan_summary = ""

    if not config.MOMENTUM_ENABLED:
        return None

    if len(monitor.positions) >= config.MAX_PICKS:
        return None

    kosdaq = market_data.get("kosdaq_index", {})
    kosdaq_change = float(kosdaq.get("change_rate", "0") if isinstance(kosdaq, dict) else "0")
    _kosdaq_blocked = kosdaq_change <= config.MARKET_INDEX_BLOCK_PCT
    if _kosdaq_blocked:
        logger.info("KOSDAQ %.1f%% — 시장 하락 감지 (한도 %.1f%%, 고스코어 오버라이드 가능)",
                    kosdaq_change, config.MARKET_INDEX_BLOCK_PCT)

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

    # 오전 급등주 추적 (오후 눌림목 대상)
    global _morning_top_movers
    for s in momentum_stocks[:5]:
        s_code = s.get("mksc_shrn_iscd", "")
        s_change = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")
        s_high = int(str(s.get("stck_hgpr", 0)).replace(",", "") or 0)
        s_cur = int(str(s.get("stck_prpr", 0)).replace(",", "") or 0)
        s_prev_close = int(s_cur / (1 + s_change / 100)) if s_change > 0 and s_cur > 0 else 0
        if s_change >= config.PULLBACK_MIN_MORNING_CHANGE:
            existing = next((m for m in _morning_top_movers if m["code"] == s_code), None)
            if existing:
                if s_high > existing["morning_high"]:
                    existing["morning_high"] = s_high
                    existing["morning_high_pct"] = s_change
            else:
                _morning_top_movers.append({
                    "code": s_code,
                    "name": s.get("hts_kor_isnm", "?"),
                    "morning_high": s_high,
                    "morning_high_pct": s_change,
                    "prev_close": s_prev_close,
                })

    if _morning_top_movers:
        _save_morning_top_movers()
    if not momentum_stocks:
        _last_momentum_scan_summary = getattr(collector, 'last_scan_summary', '후보 없음')
        return None

    top = momentum_stocks[0]
    code = top.get("mksc_shrn_iscd", "")
    name = top.get("hts_kor_isnm", "?")
    change_pct = float(str(top.get("prdy_ctrt", "0")).replace(",", "") or "0")
    m_score = top.get("momentum_score", 0)

    early = _is_early_morning()
    boosted = _boost_state["active"]
    if late:
        min_score = config.LATE_SESSION_MIN_SCORE
    elif boosted:
        min_score = config.BOOST_MOMENTUM_MIN_SCORE
    elif early:
        min_score = config.EARLY_MOMENTUM_MIN_SCORE
    else:
        min_score = config.MOMENTUM_MIN_SCORE
    # 손절 후 다음 진입: 최소 스코어 강화
    if consecutive_losses > 0:
        min_score = max(min_score, config.AFTER_LOSS_MIN_SCORE)
        logger.info("손절 후 안전 모드: 최소 스코어 %d 적용 (%d연패)", min_score, consecutive_losses)
    if m_score < min_score:
        logger.info("모멘텀 1위 스코어 부족: %s (%.1f, 최소 %d) — 스킵",
                    name, m_score, min_score)
        scan_info = getattr(collector, 'last_scan_summary', '')
        score_msg = f"1위 {name} 스코어 {m_score:.1f} < 최소 {min_score}"
        _last_momentum_scan_summary = f"{score_msg}\n{scan_info}" if scan_info else score_msg
        return None

    # KOSDAQ 하락 차단: 스코어가 오버라이드 기준 이상이면 진입 허용
    if _kosdaq_blocked:
        if m_score >= config.MARKET_INDEX_OVERRIDE_SCORE:
            logger.info("KOSDAQ %.1f%% 하락이지만 스코어 %.1f ≥ %d — 차단 오버라이드",
                        kosdaq_change, m_score, config.MARKET_INDEX_OVERRIDE_SCORE)
            bot.send_message(
                f"⚡ KOSDAQ {kosdaq_change:+.1f}% 하락이지만\n"
                f"{name} 스코어 {m_score:.1f} ≥ {config.MARKET_INDEX_OVERRIDE_SCORE} — 진입 허용"
            )
        else:
            logger.info("KOSDAQ %.1f%% + 스코어 %.1f < %d — 모멘텀 차단",
                        kosdaq_change, m_score, config.MARKET_INDEX_OVERRIDE_SCORE)
            bot.send_message(
                f"🛑 KOSDAQ {kosdaq_change:+.1f}% 하락 + "
                f"{name} 스코어 {m_score:.1f} ≤ {config.MARKET_INDEX_OVERRIDE_SCORE} — 진입 차단"
            )
            return None

    # --- 고스코어 즉시 진입: 풀백 패턴 없이도 진입 허용 ---
    skip_pullback = False
    # 1) 스코어가 충분히 높으면 시간대 무관하게 풀백 생략 (네오티스 75.8 사례)
    if m_score >= config.MOMENTUM_SKIP_PULLBACK_SCORE:
        skip_pullback = True
        logger.info("고스코어 즉시 진입: %s (스코어 %.1f ≥ %d) — 풀백 스킵",
                    name, m_score, config.MOMENTUM_SKIP_PULLBACK_SCORE)
    # 2) 초반 모드: 낮은 스코어도 고점 근처면 풀백 생략
    elif early and m_score >= config.EARLY_SKIP_PULLBACK_SCORE:
        high_ratio = top.get("_high_ratio", 0)
        if high_ratio == 0:
            today_high = int(str(top.get("stck_hgpr", 0)).replace(",", "") or 0)
            cur = int(str(top.get("stck_prpr", 0)).replace(",", "") or 0)
            high_ratio = cur / today_high if today_high > 0 else 0
        if high_ratio >= config.EARLY_SKIP_PULLBACK_HIGH_RATIO:
            skip_pullback = True
            logger.info("초반 모드 즉시 진입: %s (스코어 %.1f, 고점비 %.1f%%) — 풀백 스킵",
                        name, m_score, high_ratio * 100)

    logger.info("모멘텀 1위: %s (%.1f%%, 스코어 %.1f) — %s",
                name, change_pct, m_score,
                "즉시 진입" if skip_pullback else "풀백 진입 확인")
    bot.send_message(
        f"🚀 <b>모멘텀 후보 발견</b>\n\n"
        f"{name} ({code})\n"
        f"등락률: {change_pct:+.1f}%\n"
        f"모멘텀 스코어: {m_score:.1f}\n"
        f"{'⚡ 초반 즉시 진입' if skip_pullback else '풀백 진입 확인 중...'}"
    )

    if not skip_pullback:
        entry_ok, entry_reason = collector.check_momentum_entry(code)
        if not entry_ok:
            logger.info("모멘텀 풀백 미확인 — %s — 다음 사이클 재시도", entry_reason)
            bot.send_message(f"⏳ {name} 풀백 진입 미충족\n사유: {entry_reason}")
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
        logger.warning("예수금 조회 실패 — 모멘텀 진입 스킵")
        return None

    if boosted:
        pos_pct = config.BOOST_MAX_POSITION_PCT
    elif late:
        pos_pct = config.LATE_SESSION_POSITION_PCT
    else:
        pos_pct = config.MAX_POSITION_PCT
    position_cash = int(available_cash * pos_pct / 100)
    quantity = position_cash // cur_price
    if quantity <= 0:
        logger.info("모멘텀 주문 가능 수량 0주 — 스킵")
        return None

    if late:
        stop_pct = config.LATE_SESSION_STOP_LOSS_PCT
    elif boosted:
        stop_pct = config.BOOST_STOP_LOSS_PCT
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

    # 매수 이유 구체화 — 숫자를 해석해서 사람이 납득할 수 있게
    high_ratio = top.get('_high_ratio', 0)
    if high_ratio == 0:
        th = int(str(top.get('stck_hgpr', 0)).replace(',', '') or 0)
        high_ratio = cur_price / th if th > 0 else 0
    vol_ratio = top.get('_vol_ratio', 0)
    theme_label = top.get('_theme_label', '')

    # 거래량 해석
    if vol_ratio >= 10:
        vol_reason = f'거래량 {vol_ratio:.0f}배 폭증 — 세력/기관 유입 의심'
    elif vol_ratio >= 5:
        vol_reason = f'거래량 {vol_ratio:.1f}배 폭증 — 강한 매수세 유입'
    elif vol_ratio >= 3:
        vol_reason = f'거래량 {vol_ratio:.1f}배 급증 — 시장 관심 집중'
    elif vol_ratio >= 2:
        vol_reason = f'거래량 {vol_ratio:.1f}배 증가 — 평소 대비 활발'
    else:
        vol_reason = f'거래량 {vol_ratio:.1f}배 — 보통 수준'

    # 고점비 해석
    hr_pct = high_ratio * 100
    if hr_pct >= 98:
        hr_reason = f'고점 대비 {hr_pct:.1f}% — 매도 압력 약함 (강세)'
    elif hr_pct >= 95:
        hr_reason = f'고점 대비 {hr_pct:.1f}% — 상승 모멘텀 유지'
    elif hr_pct >= 90:
        hr_reason = f'고점 대비 {hr_pct:.1f}% — 소폭 조정 중'
    else:
        hr_reason = f'고점 대비 {hr_pct:.1f}% — 조정 진행 중'

    # 스코어 해석
    if m_score >= 60:
        score_reason = f'스코어 {m_score:.0f}점 (1위) — 매우 강한 모멘텀'
    elif m_score >= 40:
        score_reason = f'스코어 {m_score:.0f}점 (1위) — 강한 모멘텀'
    else:
        score_reason = f'스코어 {m_score:.0f}점 (1위) — 진입 기준 충족'

    # 진입 모드 해석
    if early and skip_pullback:
        mode_reason = '장 초반 고점유지 — 풀백 없이 즉시 진입'
    elif skip_pullback and m_score >= config.MOMENTUM_SKIP_PULLBACK_SCORE:
        mode_reason = f'고스코어({m_score:.0f}) 즉시 진입 — 풀백 불필요'
    elif boosted:
        mode_reason = '불장 모드 — 테마 수혜 공격적 진입'
    elif late:
        mode_reason = '후반 세션 — 보수적 배팅'
    else:
        mode_reason = '풀백 확인 후 진입'

    reasons = [
        f'\U0001f680 <b>모멘텀 매수 진행</b>\n',
        f'{name} ({code}) {change_pct:+.1f}%',
        f'',
        f'\U0001f4ca <b>매수 이유</b>',
        f'• {vol_reason}',
        f'• {hr_reason}',
        f'• {score_reason}',
        f'• {mode_reason}',
    ]
    if theme_label:
        reasons.append(f'• 테마: {theme_label}')
    reasons += [
        f'',
        f'\U0001f4b0 <b>주문</b>',
        f'{quantity}주 × {order_price:,}원 (상한지정가)',
        f'투입: {quantity * order_price:,}원 (자본 {pos_pct}%)',
        f'손절: {stop_loss:,}원 (-{stop_pct}%)',
    ]
    bot.send_message('\n'.join(reasons))

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

        bot.send_fill_confirmation(fills, strategy='momentum')
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

def _try_pullback_entry(
    kis: KISClient, bot: TelegramBot, db: Database,
    trader: Trader, monitor: PositionMonitor,
    sold_codes: set,
) -> str | None:
    """오후 눌림목 반등 진입."""
    global _morning_top_movers

    if not _morning_top_movers:
        logger.info("눌림목 — 오전 급등주 기록 없음")
        return None

    if len(monitor.positions) >= config.MAX_PICKS:
        return None

    logger.info("눌림목 스캔 — 오전 급등주 %d종목 확인", len(_morning_top_movers))

    for mover in _morning_top_movers:
        code = mover["code"]
        name = mover["name"]
        morning_high = mover["morning_high"]
        prev_close = mover["prev_close"]

        if code in sold_codes:
            logger.info("눌림목 제외 [오늘 손절 종목]: %s", name)
            continue

        try:
            price_data = kis.get_current_price(code)
            current = price_data["price"]
            today_low = price_data.get("low", 0)
        except Exception as e:
            logger.warning("눌림목 가격 조회 실패 %s: %s", name, e)
            continue

        if current <= 0 or morning_high <= 0 or prev_close <= 0:
            continue

        # 되돌림 비율: (고점-현재) / (고점-전일종가)
        rise = morning_high - prev_close
        if rise <= 0:
            continue
        retracement = (morning_high - current) / rise

        if retracement < config.PULLBACK_RETRACEMENT_MIN:
            logger.info("눌림목 제외 [되돌림 부족 %.0f%%]: %s", retracement * 100, name)
            continue
        if retracement > config.PULLBACK_RETRACEMENT_MAX:
            logger.info("눌림목 제외 [과다 하락 %.0f%%]: %s", retracement * 100, name)
            continue

        # 전일 대비 아직 플러스인지
        change_pct = (current - prev_close) / prev_close * 100
        if change_pct <= 0:
            logger.info("눌림목 제외 [전일 대비 마이너스]: %s (%.1f%%)", name, change_pct)
            continue

        # 반등 확인
        if today_low > 0:
            bounce = (current - today_low) / today_low * 100
            if bounce < config.PULLBACK_BOUNCE_CONFIRM_PCT:
                logger.info("눌림목 제외 [반등 미확인 %.1f%%]: %s", bounce, name)
                continue

        logger.info("눌림목 진입 대상: %s (되돌림 %.0f%%, 현재 %s)",
                    name, retracement * 100, f"{current:,}")

        try:
            available_cash = kis.get_available_cash()
        except Exception:
            logger.warning("예수금 조회 실패 — 눌림목 진입 스킵")
            continue

        position_cash = int(available_cash * config.AFTERNOON_MAX_POSITION_PCT / 100)
        order_price = round_to_tick(int(current * 1.005))
        quantity = position_cash // order_price
        if quantity <= 0:
            continue

        stop_loss = int(current * (1 - config.PULLBACK_STOP_LOSS_PCT / 100))
        target = int(current * (1 + config.PULLBACK_TARGET_PCT / 100))

        # 매수 이유 구체화 — 숫자를 해석해서 사람이 납득할 수 있게
        candidate_count = len(_morning_top_movers)
        bounce_pct = (current - today_low) / today_low * 100 if today_low > 0 else 0

        # 되돌림 해석
        ret_pct = retracement * 100
        if ret_pct >= 55:
            ret_reason = f'되돌림 {ret_pct:.0f}% — 충분히 눈림, 바닥 근처'
        elif ret_pct >= 40:
            ret_reason = f'되돌림 {ret_pct:.0f}% — 적정 조정 구간'
        else:
            ret_reason = f'되돌림 {ret_pct:.0f}% — 초기 조정 구간'

        # 반등 해석
        if bounce_pct >= 2.0:
            bounce_reason = f'저점 대비 +{bounce_pct:.1f}% 반등 — 강한 바닥 신호'
        elif bounce_pct >= 1.0:
            bounce_reason = f'저점 대비 +{bounce_pct:.1f}% 반등 — 바닥 다진 신호'
        else:
            bounce_reason = f'저점 대비 +{bounce_pct:.1f}% 반등 — 초기 반등'

        reasons = [
            f'\U0001f4c9 <b>눌림목 반등 매수</b>\n',
            f'{name} ({code}) 현재 {change_pct:+.1f}%',
            f'',
            f'\U0001f4ca <b>매수 이유</b>',
            f'• 오전 +{mover["morning_high_pct"]:.1f}% 급등 후 조정 — 매수 기회',
            f'• {ret_reason}',
            f'• {bounce_reason}',
            f'• 전일대비 +{change_pct:.1f}% 유지 — 상승 추세 유효',
            f'• {candidate_count}개 급등주 중 최적 진입점',
            f'',
            f'\U0001f4b0 <b>주문</b>',
            f'{quantity}주 × {order_price:,}원',
            f'목표: {target:,}원 (+{config.PULLBACK_TARGET_PCT}%)',
            f'손절: {stop_loss:,}원 (-{config.PULLBACK_STOP_LOSS_PCT}%)',
        ]
        bot.send_message('\n'.join(reasons))

        order = {
            "stock_code": code, "name": name,
            "price": order_price, "quantity": quantity,
            "amount": quantity * order_price,
            "reason": f"눌림목 반등 (되돌림 {retracement * 100:.0f}%)",
            "target1": target,
            "target2": int(current * 1.05),
            "stop_loss": stop_loss,
            "score": 0,
            "sell_strategy": {"type": "pullback", "target_pct": config.PULLBACK_TARGET_PCT},
            "is_momentum": False,
        }

        results = trader.execute_buy_orders([order])
        success = [r for r in results if r["success"]]
        if not success:
            bot.send_message(f"⚠️ {name} 눌림목 매수 실패")
            continue

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
            slippage = (fill_price - current) / current * 100 if current > 0 else 0
            monitor.add_position(
                stock_code=f["stock_code"], name=f["name"],
                quantity=f["quantity"], entry_price=fill_price,
                target1=int(fill_price * (1 + config.PULLBACK_TARGET_PCT / 100)),
                target2=int(fill_price * 1.05),
                stop_loss=int(fill_price * (1 - config.PULLBACK_STOP_LOSS_PCT / 100)),
                sell_strategy={"type": "pullback", "target_pct": config.PULLBACK_TARGET_PCT},
                buy_slippage_pct=slippage, score=0, phase="pullback", is_momentum=False,
            )
            bot.send_fill_confirmation(fills, strategy='pullback')
            if not config.DRY_RUN and db:
                db.save_trade(stock_code=f["stock_code"], stock_name=f["name"],
                    action="buy", quantity=f["quantity"], price=fill_price,
                    reason=order["reason"])
            return "pullback_entered"

        if not config.DRY_RUN:
            try:
                pending = kis.get_pending_orders()
                pb = [p for p in pending if p["stock_code"] == code]
                if pb:
                    trader.cancel_unfilled_orders(pb)
            except Exception:
                pass

    return None

def _past_entry_cutoff() -> bool:
    cutoff = config.BOOST_NO_NEW_ENTRY_AFTER if _boost_state["active"] else config.NO_NEW_ENTRY_AFTER
    hh, mm = map(int, cutoff.split(":"))
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
    """일일 손익률 (실현 + 미실현). 실제 예수금+보유자산 기준."""
    realized = sum(t.get("pnl_amt", 0) for t in monitor.trades_today)
    unrealized = 0
    position_value = 0
    for code, pos in monitor.positions.items():
        try:
            pd = monitor.kis.get_current_price(code)
            cur = pd["price"]
            if cur > 0:
                unrealized += (cur - pos["entry_price"]) * pos["remaining_qty"]
                position_value += cur * pos["remaining_qty"]
        except Exception:
            pass
    total_pnl = realized + unrealized
    # 실제 총자산 = 예수금 + 보유종목 평가액
    try:
        cash = monitor.kis.get_available_cash()
    except Exception:
        cash = 0
    total_assets = cash + position_value
    if total_assets <= 0:
        return 0.0
    return total_pnl / total_assets * 100


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

    # 오전 급등주 데이터 복구 (장중 재시작 대비)
    _load_morning_top_movers()

    if not config.DRY_RUN:
        logger.info("KIS 잔고 ↔ positions.json 동기화")
        sync_result = monitor.sync_with_balance()
        if sync_result["added"] or sync_result["removed"] or sync_result.get("updated"):
            lines = ["🔄 <b>포지션 동기화 완료</b>"]
            for h in sync_result["added"]:
                lines.append(f"  ➕ {h['name']} {h['quantity']}주 @ {h['avg_price']:,}원")
            for name in sync_result["removed"]:
                lines.append(f"  ➖ {name} (청산됨)")
            for u in sync_result.get("updated", []):
                lines.append(f"  🔄 {u['name']} {u['old']}주→{u['new']}주 (KIS 기준)")
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

    # --- 오버나이트 포지션 갭 체크 (09:05) ---
    overnight_positions = {c: p for c, p in monitor.positions.items() if p.get("overnight")}
    if overnight_positions and not config.DRY_RUN:
        logger.info("오버나이트 포지션 %d개 감지 — %s 갭 체크 대기",
                    len(overnight_positions), config.OVERNIGHT_MORNING_CHECK)
        bot.send_message(
            f"🌙 오버나이트 포지션 {len(overnight_positions)}개 — "
            f"{config.OVERNIGHT_MORNING_CHECK} 갭 체크 예정\n"
            + "\n".join(f"  {p['name']} {p['remaining_qty']}주" for p in overnight_positions.values())
        )
        wait_until(config.OVERNIGHT_MORNING_CHECK, bot, kis, monitor)
        for code, pos in list(overnight_positions.items()):
            try:
                price_data = kis.get_current_price(code)
                current = price_data["price"]
                overnight_close = pos.get("overnight_close_price", pos["entry_price"])
                gap_pct = (current - overnight_close) / overnight_close * 100 if overnight_close > 0 else 0
                entry = pos["entry_price"]
                total_pnl_pct = (current - entry) / entry * 100 if entry > 0 else 0

                if gap_pct <= config.OVERNIGHT_GAP_DOWN_SELL_PCT:
                    # 갭다운 → 즉시 매도
                    logger.info("%s 갭다운 %.1f%% — 즉시 매도", pos["name"], gap_pct)
                    bot.send_message(
                        f"🚨 <b>{pos['name']} 갭다운 — 즉시 매도</b>\n\n"
                        f"전일 종가: {overnight_close:,}원 → 현재: {current:,}원 ({gap_pct:+.1f}%)\n"
                        f"전체 수익: {total_pnl_pct:+.1f}%"
                    )
                    remaining = pos["remaining_qty"]
                    try:
                        sell_result = kis.place_sell_order(code, remaining)
                        if sell_result.get("rt_cd") == "0":
                            monitor.trades_today.append({
                                "code": code, "name": pos["name"],
                                "action": "sell", "quantity": remaining,
                                "entry_price": entry, "exit_price": current,
                                "pnl_pct": total_pnl_pct,
                                "pnl_amt": int((current - entry) * remaining),
                                "reason": f"오버나이트 갭다운 {gap_pct:+.1f}%",
                                "phase": "overnight",
                            })
                            monitor.remove_position(code)
                            if db:
                                db.save_trade(code, pos["name"], "sell", remaining, current,
                                              reason=f"오버나이트 갭다운 {gap_pct:+.1f}%")
                        else:
                            bot.send_message(f"⚠️ {pos['name']} 매도 실패: {sell_result.get('msg1', '')}")
                    except Exception as e:
                        logger.error("오버나이트 매도 실패 %s: %s", pos["name"], e)
                        bot.send_message(f"⚠️ {pos['name']} 오버나이트 매도 오류: {e}")
                else:
                    # 갭업/보합 → 트레일링 유지
                    pos["overnight"] = False  # 플래그 해제 — 일반 모니터링으로 전환
                    monitor._save_positions()
                    logger.info("%s 갭 %+.1f%% — 트레일링 유지 (전체 %+.1f%%)",
                                pos["name"], gap_pct, total_pnl_pct)
                    bot.send_message(
                        f"✅ <b>{pos['name']} 오버나이트 유지</b>\n\n"
                        f"전일 종가: {overnight_close:,}원 → 현재: {current:,}원 ({gap_pct:+.1f}%)\n"
                        f"전체 수익: {total_pnl_pct:+.1f}% — 트레일링 스탑으로 모니터링"
                    )
            except Exception as e:
                logger.error("오버나이트 체크 실패 %s: %s", pos.get("name", code), e)


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
        elif exit_reason == "positions_cleared" and _should_run_afternoon(monitor):
            logger.info("활성 포지션 청산 — 오후 전략으로 전환")
        else:
            _send_daily_report(monitor, bot, db)
            return bot

    # --- 불장 모드: 08:55 센티먼트 분석 ---
    if config.BOOST_ENABLED and not past_analysis_time() and not config.DRY_RUN:
        wait_until(config.SENTIMENT_TIME, bot, kis, monitor)
        _run_sentiment_check(naver_news, analyzer, bot)

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
        profit_target = config.BOOST_DAILY_PROFIT_TARGET_PCT if _boost_state["active"] else config.DAILY_PROFIT_TARGET_PCT
        if daily_pnl >= profit_target:
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
            last_trade = new_trades[-1]
            last_pnl = last_trade.get("pnl_amt", 0)
            last_pnl_pct = last_trade.get("pnl_pct", 0)
            if last_pnl < 0:
                consecutive_losses += 1
            else:
                consecutive_losses = 0
                # 단일 거래 수익 +N% 이상 → 당일 종료 (돈 지킨다)
                profit_stop = config.BOOST_FIRST_PROFIT_STOP_PCT if _boost_state["active"] else config.FIRST_PROFIT_STOP_PCT
                if last_pnl_pct >= profit_stop:
                    logger.info("수익 확보 +%.1f%% → 당일 매매 종료", last_pnl_pct)
                    bot.send_message(
                        f"🎯 <b>수익 확보 — 당일 매매 종료</b>\n\n"
                        f"수익률: {last_pnl_pct:+.1f}% ({last_pnl:+,}원)\n"
                        f"돈 지킵니다. 내일 또 보곜요. 💪"
                    )
                    break

        # 재시도 가능한 결과: 쿨다운 후 다음 사이클
        retryable = ("no_picks", "opening_filtered", "low_confidence", "positions_cleared")
        if exit_reason not in retryable:
            logger.info("사이클 종료 (사유: %s) — 재시도 불가", exit_reason)
            break

        if monitor.should_stop:
            break

        if not _past_entry_cutoff() and cycle < config.MAX_CYCLES:
            early = _is_early_morning()
            if _boost_state["active"]:
                cooldown = config.BOOST_CYCLE_COOLDOWN
            elif early:
                cooldown = config.EARLY_CYCLE_COOLDOWN
            else:
                cooldown = config.CYCLE_COOLDOWN
            # 매매비추천/필터탈락은 쿨다운 짧게 (시장 변화 빠르게 재확인)
            if exit_reason in ("no_picks", "opening_filtered", "low_confidence"):
                cooldown = min(cooldown, 600)  # 최대 10분
                scan_detail = _last_momentum_scan_summary
                msg = (
                    f"⏸ 사이클 {cycle} — 진입 조건 미충족 ({exit_reason})\n"
                    f"{cooldown // 60}분 후 시장 재분석합니다."
                )
                if scan_detail:
                    msg += f"\n\n🔍 <b>모멘텀 스캔 요약</b>\n{scan_detail}"
                bot.send_message(msg)
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
                f"☀️ 오전 전략 종료 — {start_str} 눌림목 전략 시작 대기\n"
                f"(오전 급등주 되돌림 매수)"
            )
            wait_until(config.AFTERNOON_PHASE_START, bot, kis, monitor)

        # 오전 연패 기록 리셋 — 오후는 별도 세션으로 취급
        consecutive_losses = 0

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
    """오후 전략: 모멘텀 + 눌림목 병행."""
    # 급등주 데이터 없으면 현재 시장에서 직접 스캔
    global _morning_top_movers
    if not _morning_top_movers:
        logger.info("오전 급등주 데이터 없음 — 현재 시장 스캔으로 대체")
        try:
            raw = collector.kis.get_fluctuation_ranking_filtered(
                rate_min=config.PULLBACK_MIN_MORNING_CHANGE,
                rate_max=30.0, price_min=config.MOMENTUM_MIN_PRICE,
                vol_min=config.MOMENTUM_MIN_VOLUME,
            )
            for s in (raw or [])[:10]:
                s_code = s.get("mksc_shrn_iscd") or s.get("stck_shrn_iscd", "")
                s_change = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")
                s_high = int(str(s.get("stck_hgpr", 0)).replace(",", "") or 0)
                s_cur = int(str(s.get("stck_prpr", 0)).replace(",", "") or 0)
                s_prev = int(s_cur / (1 + s_change / 100)) if s_change > 0 and s_cur > 0 else 0
                if s_code and s_change >= config.PULLBACK_MIN_MORNING_CHANGE:
                    _morning_top_movers.append({
                        "code": s_code,
                        "name": s.get("hts_kor_isnm", "?"),
                        "morning_high": s_high,
                        "morning_high_pct": s_change,
                        "prev_close": s_prev,
                    })
            if _morning_top_movers:
                _save_morning_top_movers()
                logger.info("시장 스캔으로 급등주 %d종목 확보", len(_morning_top_movers))
        except Exception as e:
            logger.warning("시장 스캔 실패: %s", e)

    logger.info("━━━ 오후 전략 시작 (%s ~ %s) — 모멘텀 + 눌림목 ━━━",
                config.AFTERNOON_PHASE_START, config.AFTERNOON_PHASE_END)
    pullback_names = ", ".join(m["name"] for m in _morning_top_movers[:5]) if _morning_top_movers else "없음"
    bot.send_message(
        f"📈 <b>오후 전략 시작</b> (모멘텀 + 눌림목)\n"
        f"눌림목 대상: {pullback_names}\n"
        f"포지션: {config.AFTERNOON_MAX_POSITION_PCT}% | "
        f"목표: +{config.PULLBACK_TARGET_PCT}% | "
        f"손절: -{config.PULLBACK_STOP_LOSS_PCT}%"
    )

    afternoon_entries = 0
    cycle = 0
    while not _past_afternoon_cutoff() and cycle < config.AFTERNOON_MAX_CYCLES:
        cycle += 1

        daily_pnl = _get_daily_pnl_pct(monitor)
        if daily_pnl <= config.DAILY_LOSS_LIMIT_PCT:
            bot.send_message(f"🛑 일일 손실한도 ({daily_pnl:.1f}%) — 오후 중단")
            break

        if not monitor.positions:
            entered = False

            # 1) 눌림목 먼저 시도
            if _morning_top_movers:
                result = _try_pullback_entry(kis, bot, db, trader, monitor, sold_codes)
                if result == "pullback_entered":
                    entered = True
                    afternoon_entries += 1

            # 2) 눌림목 없으면 모멘텀 시도
            if not entered and not monitor.positions:
                try:
                    market_data = collector.fetch_market_data(phase="afternoon")
                except Exception as e:
                    logger.warning("오후 시장데이터 수집 실패: %s", e)
                    market_data = None
                if market_data:
                    momentum_result = _try_momentum_entry(
                        kis, bot, db, collector, trader, monitor, sold_codes, market_data,
                        consecutive_losses=consecutive_losses,
                    )
                    if momentum_result == "momentum_entered":
                        entered = True
                        afternoon_entries += 1

            # 진입 성공 → 모니터링
            if entered:
                _run_monitoring_loop(
                    monitor, bot, kis, collector, analyzer, trader, sold_codes,
                    phase="afternoon",
                )
                for t in monitor.trades_today:
                    if t.get("pnl_amt", 0) < 0 and "code" in t:
                        sold_codes.add(t["code"])
                continue

        if not _past_afternoon_cutoff():
            cooldown = config.AFTERNOON_CYCLE_COOLDOWN
            bot.send_message(f"⏸ 오후 대기 — {cooldown // 60}분 후 재스캔")
            cooldown_end = time.time() + cooldown
            while time.time() < cooldown_end:
                try:
                    bot.process_updates(kis, monitor)
                except Exception:
                    pass
                if monitor.should_stop or _past_afternoon_cutoff():
                    break
                time.sleep(min(30, cooldown_end - time.time()))

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

    # 첫 사이클: KOSPI/KOSDAQ 지표로 부스트 최종 확정
    if cycle == 1 and config.BOOST_ENABLED and _boost_state["sentiment"] != "":
        _confirm_boost_from_index(market_data, bot)

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
            consecutive_losses=consecutive_losses,
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
        logger.warning("현금 조회 실패: %s — 매매 건너뛰", e)
        bot.send_message("⚠️ 예수금 조회 실패 — 오늘 매매 스킵")
        return

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
    # 모니터링 진입 전 KIS 잔고 동기화
    if not config.DRY_RUN:
        monitor.sync_with_balance()
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

        active = {k: v for k, v in monitor.positions.items() if not v.get('manual')}
        if not active:
            logger.info("활성 포지션 청산 — 모니터링 종료 (수동 %d개 유지)", len(monitor.positions))
            bot.send_message("모든 활성 포지션 청산 완료 — 모니터링 종료")
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
