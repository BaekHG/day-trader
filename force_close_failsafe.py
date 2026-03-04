"""
Force-close failsafe — 메인 봇과 독립적으로 15:25에 실행.
positions.json에 포지션이 남아있으면 시장가 매도.
단, manual 포지션과 오버나이트 홀딩 조건 충족 종목은 스킵.

봇이 크래시/hang 되어도 불필요한 오버나이트 방지.

Usage:
    python3 force_close_failsafe.py          # 포지션 있으면 청산
    python3 force_close_failsafe.py --dry     # 드라이런 (매도 없이 확인만)
"""

import json
import logging
import os
import sys
import time
from datetime import datetime

import pytz

import config
from kis_client import KISClient
from telegram_bot import TelegramBot

KST = pytz.timezone("Asia/Seoul")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(config.LOG_DIR, "failsafe.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("failsafe")


def load_positions() -> dict:
    """positions.json에서 포지션 로드."""
    try:
        with open(config.POSITIONS_FILE, "r") as f:
            positions = json.load(f)
        return positions if isinstance(positions, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.info("positions.json 로드 실패 (정상 — 포지션 없음): %s", e)
        return {}


def save_positions(positions: dict):
    """positions.json 저장 (홀딩 종목만 남김)."""
    try:
        tmp = config.POSITIONS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)
        os.rename(tmp, config.POSITIONS_FILE)
        logger.info("positions.json 업데이트 완료 (%d개 남음)", len(positions))
    except Exception as e:
        logger.error("positions.json 저장 실패: %s", e)


def check_overnight_eligible(pos: dict, current_price: int) -> bool:
    """오버나이트 홀딩 조건 체크."""
    if not config.OVERNIGHT_ENABLED:
        return False

    entry_price = pos.get("entry_price", 0)
    high_since_entry = pos.get("high_since_entry", 0)

    if entry_price <= 0 or high_since_entry <= 0:
        return False

    profit_pct = (current_price - entry_price) / entry_price * 100
    high_ratio = current_price / high_since_entry if high_since_entry > 0 else 0

    eligible = (
        profit_pct >= config.OVERNIGHT_MIN_PROFIT_PCT
        and high_ratio >= config.OVERNIGHT_MIN_HIGH_RATIO
    )

    logger.info(
        "  오버나이트 체크: 수익 %.1f%% (기준 %.1f%%), 고점비 %.1f%% (기준 %.0f%%) → %s",
        profit_pct, config.OVERNIGHT_MIN_PROFIT_PCT,
        high_ratio * 100, config.OVERNIGHT_MIN_HIGH_RATIO * 100,
        "홀딩 ✓" if eligible else "청산 대상",
    )
    return eligible


def force_close_all(dry_run: bool = False):
    """포지션 강제 청산. manual/오버나이트 조건 충족 종목은 스킵."""
    now = datetime.now(KST)
    logger.info("=" * 40)
    logger.info("강제청산 failsafe 시작 — %s", now.strftime("%Y.%m.%d %H:%M:%S"))

    positions = load_positions()
    if not positions:
        logger.info("포지션 없음 — 정상 종료")
        return

    logger.info("잔여 포지션 %d개 발견!", len(positions))
    for code, pos in positions.items():
        manual_tag = " [수동]" if pos.get("manual") else ""
        logger.info("  %s (%s) %d주 @ %s원%s",
                     pos.get("name", "?"), code,
                     pos.get("remaining_qty", 0),
                     f"{pos.get('entry_price', 0):,}",
                     manual_tag)

    if dry_run:
        logger.info("[DRY RUN] 매도 주문 건너뜀")
        return

    kis = KISClient()
    bot = TelegramBot()

    try:
        holdings = kis.get_balance()
        real_holdings = {h["stock_code"]: h for h in holdings if h["quantity"] > 0}
    except Exception as e:
        logger.error("잔고 조회 실패: %s — positions.json 기준으로 진행", e)
        real_holdings = None

    success_count = 0
    fail_count = 0
    skip_count = 0
    kept_positions = {}  # 홀딩/수동으로 남길 포지션

    for code, pos in positions.items():
        name = pos.get("name", code)

        # ── 수동 종목 스킵 ──
        if pos.get("manual"):
            logger.info("%s — 수동 매수 종목, 스킵 ✓", name)
            kept_positions[code] = pos
            skip_count += 1
            continue

        # ── 오버나이트 홀딩 조건 체크 ──
        try:
            price_data = kis.get_current_price(code)
            current_price = price_data.get("price", 0) if isinstance(price_data, dict) else 0
        except Exception as e:
            logger.warning("%s 현재가 조회 실패: %s — 청산 진행", name, e)
            current_price = 0

        if current_price > 0 and check_overnight_eligible(pos, current_price):
            logger.info("%s — 오버나이트 홀딩 조건 충족, 스킵 ✓", name)
            kept_positions[code] = pos
            skip_count += 1
            continue

        # ── 청산 대상 ──
        if real_holdings is not None:
            if code not in real_holdings:
                logger.info("%s — 실잔고에 없음 (이미 청산됨), 스킵", name)
                continue
            qty = real_holdings[code]["quantity"]
        else:
            qty = pos.get("remaining_qty", 0)

        if qty <= 0:
            logger.info("%s — 수량 0, 스킵", name)
            continue

        logger.info("%s 시장가 매도 시도 — %d주", name, qty)

        for attempt in range(3):
            try:
                result = kis.place_sell_order(code, qty)
                if result.get("rt_cd") == "0":
                    logger.info("%s 매도 주문 성공 ✓", name)
                    success_count += 1
                    break
                else:
                    err = result.get("msg1", "알 수 없음")
                    logger.error("%s 매도 실패 (시도 %d/3): %s", name, attempt + 1, err)
                    if attempt < 2:
                        time.sleep(2 ** attempt)
            except Exception as e:
                logger.error("%s 매도 주문 오류 (시도 %d/3): %s", name, attempt + 1, e)
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            fail_count += 1
            logger.error("%s 매도 3회 실패!", name)

    # ── 텔레그램 알림 ──
    msg_lines = [f"🚨 <b>Failsafe 강제청산 실행</b> ({now.strftime('%H:%M')})"]
    if success_count:
        msg_lines.append(f"✅ 청산 성공: {success_count}건")
    if skip_count:
        msg_lines.append(f"⏭️ 스킵: {skip_count}건 (수동/오버나이트)")
    if fail_count:
        msg_lines.append(f"❌ 청산 실패: {fail_count}건 — 수동 확인 필요!")
    if not success_count and not fail_count and not skip_count:
        msg_lines.append("ℹ️ 실잔고 확인 결과 청산 대상 없음")

    try:
        bot.send_message("\n".join(msg_lines))
    except Exception as e:
        logger.error("텔레그램 전송 실패: %s", e)

    # ── positions.json 정리: 홀딩/수동 종목만 남기기 ──
    if fail_count == 0:
        if kept_positions:
            save_positions(kept_positions)
        else:
            save_positions({})
    else:
        logger.warning("일부 실패 — positions.json 유지 (수동 확인 필요)")

    logger.info(
        "강제청산 failsafe 완료 — 성공 %d / 스킵 %d / 실패 %d",
        success_count, skip_count, fail_count,
    )


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    if dry:
        logger.info("[DRY RUN MODE]")
    force_close_all(dry_run=dry)
