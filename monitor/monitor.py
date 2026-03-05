from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime

import pytz

import config
from db import Database
from kis_client import KISClient
from telegram_bot import TelegramBot

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")


class PositionMonitor:
    def __init__(self, kis: KISClient, bot: TelegramBot, db: Database | None = None):
        self.kis = kis
        self.bot = bot
        self.db = db
        self.positions: dict[str, dict] = {}
        self.trades_today: list[dict] = []
        self.should_stop = False
        self._lock = threading.Lock()
        self._load_positions()
        self._load_trades_today()

    def add_position(
        self, stock_code: str, name: str, quantity: int, entry_price: int,
        target1: int, target2: int, stop_loss: int, sell_strategy: dict | None = None,
        buy_slippage_pct: float = 0.0, score: int = 0, phase: str = "morning",
        is_momentum: bool = False, today_open: int = 0,
    ):
        existing = self.positions.get(stock_code)
        if existing and existing.get("remaining_qty", 0) > 0:
            # 같은 종목 추가매수 — 수량 합산 + 평균단가 재계산
            old_qty = existing["remaining_qty"]
            total_cost = existing["entry_price"] * old_qty + entry_price * quantity
            new_qty = old_qty + quantity
            avg_price = total_cost // new_qty if new_qty > 0 else entry_price
            existing["quantity"] = new_qty
            existing["remaining_qty"] = new_qty
            existing["entry_price"] = avg_price
            existing["stop_loss"] = stop_loss
            existing["high_since_entry"] = max(existing.get("high_since_entry", avg_price), avg_price)
            if sell_strategy:
                existing["sell_strategy"] = sell_strategy
            self._save_positions()
            tag = "[모멘텀]" if is_momentum else ""
            logger.info("%s포지션 추가매수: %s +%d주 (총 %d주, 평단 %s원)", tag, name, quantity, new_qty, f"{avg_price:,}")
            return
        self.positions[stock_code] = {
            "name": name, "quantity": quantity, "remaining_qty": quantity,
            "entry_price": entry_price, "target1": target1, "target2": target2,
            "stop_loss": stop_loss, "high_since_entry": entry_price,
            "target1_hit": False, "sell_strategy": sell_strategy or {},
            "entry_time": datetime.now(KST).isoformat(),
            "buy_slippage_pct": round(buy_slippage_pct, 3),
            "score": score,
            "phase": phase,
            "is_momentum": is_momentum,
            "today_open": today_open,
        }
        self._save_positions()
        tag = "[모멘텀]" if is_momentum else ""
        logger.info("%s포지션 추가: %s %d주 @ %s원", tag, name, quantity, f"{entry_price:,}")

    def remove_position(self, stock_code: str):
        if stock_code in self.positions:
            del self.positions[stock_code]
            self._save_positions()

    def check_positions(self):
        with self._lock:
            self._check_positions_locked()

    def _check_positions_locked(self):
        now = datetime.now(KST)
        force_hh, force_mm = map(int, config.FORCE_CLOSE_TIME.split(":"))  # 15:10 — 손실 종목 청산

        for code, pos in list(self.positions.items()):
            # 수동 매수 포지션은 모니터링 완전 스킵 (유저가 직접 관리)
            if pos.get("manual"):
                continue
            try:
                price_data = self.kis.get_current_price(code)
            except Exception as e:
                logger.error("%s 가격 조회 실패: %s", pos["name"], e)
                continue

            current = price_data["price"]
            if current <= 0:
                continue

            if current > pos["high_since_entry"]:
                pos["high_since_entry"] = current
                self._save_positions()

            entry = pos["entry_price"]
            remaining = pos["remaining_qty"]
            pnl_pct = (current - entry) / entry * 100 if entry else 0

            # --- 장 마감 2단계 청산 ---
            final_hh, final_mm = map(int, config.FINAL_CLOSE_TIME.split(":"))  # 15:20
            is_final = now.hour > final_hh or (now.hour == final_hh and now.minute >= final_mm)
            is_force = now.hour > force_hh or (now.hour == force_hh and now.minute >= force_mm)

            if is_final:
                # 15:20 — 오버나이트 조건 충족 시 홀딩, 아니면 전량 청산
                if config.OVERNIGHT_ENABLED and pnl_pct >= config.OVERNIGHT_MIN_PROFIT_PCT:
                    high_ratio = current / pos["high_since_entry"] if pos.get("high_since_entry", 0) > 0 else 0
                    if high_ratio >= config.OVERNIGHT_MIN_HIGH_RATIO:
                        pos["overnight"] = True
                        pos["overnight_close_price"] = current
                        self._save_positions()
                        logger.info("%s 오버나이트 홀딩 — 수익 %.1f%%, 고점비 %.1f%%", pos["name"], pnl_pct, high_ratio * 100)
                        self.bot.send_message(
                            f"🌙 <b>{pos['name']} 오버나이트 홀딩</b>\n\n"
                            f"수익: {pnl_pct:+.1f}% ({current:,}원)\n"
                            f"고점비: {high_ratio * 100:.1f}%\n"
                            f"내일 {config.OVERNIGHT_MORNING_CHECK} 갭 체크 예정"
                        )
                        continue
                self._execute_sell(code, pos, remaining, current, f"{config.FINAL_CLOSE_TIME} 전량 강제 청산", pnl_pct)
                continue
            elif is_force and pnl_pct <= 0:
                # 15:10 — 손실 종목만 청산 (수익 종목은 트레일링 유지)
                self._execute_sell(code, pos, remaining, current, f"{config.FORCE_CLOSE_TIME} 손실 청산 (수익종목 트레일링 유지)", pnl_pct)
                continue

            is_momentum = pos.get("is_momentum", False)

            if is_momentum:
                today_open = pos.get("today_open", 0)
                if today_open > 0 and current < today_open:
                    self._execute_sell(
                        code, pos, remaining, current,
                        "모멘텀 시가 하회 — 갭 실패 즉시 청산", pnl_pct,
                    )
                    continue


            # 눌림목 포지션: 손절만 빠르게, 매도는 트레일링으로 (고정 목표 제거)
            is_pullback = pos.get("phase") == "pullback"
            if is_pullback:
                pullback_stop = int(entry * (1 - config.PULLBACK_STOP_LOSS_PCT / 100))
                if current <= pullback_stop:
                    self._execute_sell(code, pos, remaining, current, "눌림목 손절", pnl_pct)
                    continue

                pb_entry_time = pos.get("entry_time", "")
                if pb_entry_time:
                    pb_dt = datetime.fromisoformat(pb_entry_time)
                    pb_hold = (now - pb_dt).total_seconds() / 60
                    if pb_hold >= config.AFTERNOON_MAX_HOLD_MINUTES and pnl_pct < 1.0:
                        self._execute_sell(code, pos, remaining, current,
                            f"눌림목 {config.AFTERNOON_MAX_HOLD_MINUTES}분 횡보", pnl_pct)
                        continue
                # 트레일링 스탑은 아래 공통 로직에서 처리 (fall through)

            # 불장 모드 확인 (순환 import 회피)
            _boosted = False
            try:
                import main as _main_mod
                _boosted = getattr(_main_mod, "_boost_state", {}).get("active", False)
            except Exception:
                pass

            if is_momentum and _boosted:
                trailing_levels = config.BOOST_MOMENTUM_TRAILING_STOP_LEVELS
            elif is_momentum:
                trailing_levels = config.MOMENTUM_TRAILING_STOP_LEVELS
            else:
                trailing_levels = config.TRAILING_STOP_LEVELS

            effective_stop = pos["stop_loss"]
            high_pnl = (pos["high_since_entry"] - entry) / entry * 100 if entry else 0
            for level_pnl, stop_pnl in trailing_levels:
                if high_pnl >= level_pnl:
                    trailing_stop = int(entry * (1 + stop_pnl / 100))
                    effective_stop = max(effective_stop, trailing_stop)
                    break
            if current <= effective_stop:
                if effective_stop > pos["stop_loss"]:
                    tag = "모멘텀 " if is_momentum else ""
                    reason = f"{tag}트레일링 스탑 (고점 +{high_pnl:.1f}% → 손절선 +{((effective_stop - entry) / entry * 100):.1f}%)"
                else:
                    reason = "모멘텀 손절" if is_momentum else "손절"
                self._execute_sell(code, pos, remaining, current, reason, pnl_pct)
                continue

            pos_phase = pos.get("phase", "morning")
            if is_momentum and _boosted:
                max_hold = config.BOOST_TIME_STOP_MINUTES
                min_profit_for_hold = config.BOOST_TIME_STOP_MIN_PROFIT
            elif is_momentum:
                max_hold = config.MOMENTUM_TIME_STOP_MINUTES
                min_profit_for_hold = config.MOMENTUM_TIME_STOP_MIN_PROFIT
            elif pos_phase == "afternoon":
                max_hold = config.AFTERNOON_MAX_HOLD_MINUTES
                min_profit_for_hold = 1.0
            else:
                max_hold = config.MAX_HOLD_MINUTES
                min_profit_for_hold = 1.0

            entry_time_str = pos.get("entry_time", "")
            if entry_time_str:
                entry_dt = datetime.fromisoformat(entry_time_str)
                hold_minutes = (now - entry_dt).total_seconds() / 60
                if hold_minutes >= max_hold and pnl_pct < min_profit_for_hold:
                    tag = "모멘텀 " if is_momentum else ""
                    self._execute_sell(
                        code, pos, remaining, current,
                        f"{tag}{max_hold}분 횡보 — 전량 매도", pnl_pct,
                    )
                    continue

            logger.info(
                "%s | %s원 (%.1f%%) | 고점 %s | 잔량 %d주",
                pos["name"], f"{current:,}", pnl_pct, f"{pos['high_since_entry']:,}", remaining,
            )

    def _step_down_sell(self, code: str, name: str, qty: int, current_price: int) -> dict:
        """단계적 매도: 지정가(+0.3%) → 지정가(현재가) → 시장가.

        높은 가격에 먼저 팔아보고, 안 되면 점점 내려오는 전략.
        """
        offset_price = int(current_price * (1 + config.SELL_LIMIT_OFFSET_PCT / 100))

        steps = [
            ("지정가+{:.1f}%".format(config.SELL_LIMIT_OFFSET_PCT), offset_price),
            ("지정가(현재가)", 0),   # 0 = refresh price at step time
            ("시장가", -1),          # -1 = market order
        ]

        for i, (label, target_price) in enumerate(steps):
            # --- 시장가 (최종 폴백) ---
            if target_price == -1:
                logger.info("매도 %d단계 — %s %s", i + 1, name, label)
                return self.kis.place_sell_order(code, qty)

            # --- 지정가(현재가) → 실시간 가격 조회 ---
            if target_price == 0:
                try:
                    target_price = self.kis.get_current_price(code)["price"]
                except Exception:
                    logger.warning("가격 조회 실패 — 시장가 폴백")
                    return self.kis.place_sell_order(code, qty)

            logger.info("매도 %d단계 — %s %s원 (%s)", i + 1, name, f"{target_price:,}", label)
            result = self.kis.place_sell_order(code, qty, price=target_price)

            if result.get("rt_cd") != "0":
                logger.warning("매도 주문 제출 실패: %s — 다음 단계", result.get("msg1", ""))
                continue

            # --- 체결 대기 ---
            time.sleep(config.SELL_STEP_WAIT_SEC)

            # --- 미체결 확인 ---
            try:
                pending = self.kis.get_pending_orders(sll_buy_dvsn="01")
                still_pending = [p for p in pending if p["stock_code"] == code and p["remaining_qty"] > 0]
            except Exception as e:
                logger.warning("미체결 조회 실패: %s — 체결된 것으로 간주", e)
                return result

            if not still_pending:
                logger.info("매도 체결 완료 — %s %s원", name, f"{target_price:,}")
                return result

            # --- 부분 체결 확인 ---
            filled_so_far = qty - still_pending[0]["remaining_qty"]
            if filled_so_far > 0:
                logger.info("부분 체결 %d/%d주 — 나머지 다음 단계", filled_so_far, qty)
                qty = still_pending[0]["remaining_qty"]

            # --- 취소 후 다음 단계 ---
            for p in still_pending:
                try:
                    self.kis.cancel_order(p["ord_gno_brno"], p["odno"], p["remaining_qty"])
                except Exception as e:
                    logger.warning("매도 취소 실패: %s — 시장가 폴백", e)
                    return self.kis.place_sell_order(code, qty)

            time.sleep(1)  # 취소 처리 대기

        # safety net
        return self.kis.place_sell_order(code, qty)

    def _execute_sell(self, code: str, pos: dict, qty: int, price: int, reason: str, pnl_pct: float):
        name = pos["name"]
        entry = pos["entry_price"]
        pnl_amt = (price - entry) * qty

        now = datetime.now(KST)
        hold_minutes = 0.0
        entry_time_str = pos.get("entry_time", "")
        if entry_time_str:
            try:
                et = datetime.fromisoformat(entry_time_str)
                hold_minutes = (now - et).total_seconds() / 60
            except (ValueError, TypeError):
                pass

        high_water_mark_pct = 0.0
        if entry > 0:
            high_water_mark_pct = (pos.get("high_since_entry", entry) - entry) / entry * 100

        if "트레일링" in reason:
            exit_type = "trailing"
        elif "손절" in reason:
            exit_type = "stop_loss"
        elif "횡보" in reason or "분" in reason and "매도" in reason:
            exit_type = "time_exit"
        elif "강제" in reason:
            exit_type = "force_close"
        else:
            exit_type = "manual"

        # 긴급 매도 판별: 손절/강제/갭실패 → 시장가 즉시, 그 외 → 단계적 매도
        urgent = any(kw in reason for kw in ("손절", "강제", "갭 실패"))

        success = False
        result = {}
        if config.DRY_RUN:
            success = True
            logger.info("[모의] 매도 시뮬레이션: %s %d주 × %s원", name, qty, f"{price:,}")
        elif not urgent and config.SELL_STEP_DOWN:
            # --- 단계적 매도: 지정가 → 시장가 ---
            try:
                result = self._step_down_sell(code, name, qty, price)
                success = result.get("rt_cd") == "0"
            except Exception as e:
                logger.error("단계적 매도 실패 %s: %s — 시장가 폴백", name, e)
                try:
                    result = self.kis.place_sell_order(code, qty)
                    success = result.get("rt_cd") == "0"
                except Exception as e2:
                    self.bot.send_message(f"⚠️ {name} 매도 완전 실패: {e2}")
                    return
        else:
            # --- 긴급 매도: 시장가 즉시 ---
            for sell_attempt in range(3):
                try:
                    result = self.kis.place_sell_order(code, qty)
                    success = result.get("rt_cd") == "0"
                    if success:
                        break
                except Exception as e:
                    logger.error("매도 주문 실패 %s (시도 %d/3): %s", name, sell_attempt + 1, e)
                    if sell_attempt < 2:
                        time.sleep(2 ** sell_attempt)
                        continue
                    self.bot.send_message(f"⚠️ {name} 매도 3회 실패: {e}")
                    return

        if success:
            pos.pop("_last_sell_error", None)
            emoji = "🟢" if pnl_amt >= 0 else "🔴"
            sign = "+" if pnl_pct >= 0 else ""
            msg = (
                f"{emoji} <b>{name} 매도 완료</b>\n\n"
                f"사유: {reason}\n"
                f"수량: {qty}주 × {price:,}원\n"
                f"수익: {sign}{pnl_amt:,}원 ({sign}{pnl_pct:.1f}%)"
            )
            if pos["remaining_qty"] - qty > 0:
                msg += f"\n잔여: {pos['remaining_qty'] - qty}주 홀딩"
            self.bot.send_message(msg)

            self.trades_today.append({
                "code": code, "name": name, "qty": qty,
                "entry": entry, "exit": price,
                "pnl_amt": pnl_amt, "pnl_pct": round(pnl_pct, 1), "reason": reason,
                "exit_type": exit_type, "hold_minutes": round(hold_minutes, 1),
                "high_water_mark_pct": round(high_water_mark_pct, 2),
                "buy_slippage_pct": pos.get("buy_slippage_pct", 0.0),
                "score": pos.get("score", 0),
                "phase": pos.get("phase", "morning"),
            })
            self._save_trades_today()

            if self.db and not config.DRY_RUN:
                ok = self.db.save_trade(
                    stock_code=code,
                    stock_name=name,
                    action="sell",
                    quantity=qty,
                    price=price,
                    reason=reason,
                    pnl_amount=pnl_amt,
                    pnl_pct=pnl_pct,
                    exit_type=exit_type,
                    hold_minutes=hold_minutes,
                    high_water_mark_pct=high_water_mark_pct,
                    slippage_pct=pos.get("buy_slippage_pct", 0.0),
                    score=pos.get("score", 0),
                )
                if not ok:
                    self.bot.send_message(f"⚠️ {name} 매도 기록 DB 저장 실패")

            # KIS 실잔고로 확인 후 포지션 업데이트
            time.sleep(0.5)
            try:
                holdings = self.kis.get_balance()
                kis_qty = {h["stock_code"]: h["quantity"] for h in holdings}
                actual = kis_qty.get(code, 0)
                if actual <= 0:
                    self.remove_position(code)
                else:
                    pos["remaining_qty"] = actual
                    pos["quantity"] = actual
                    self._save_positions()
                    logger.info("%s KIS 실잔량: %d주 남음", name, actual)
            except Exception as e_bal:
                logger.warning("매도 후 잔고 확인 실패: %s — 계산값 사용", e_bal)
                if pos["remaining_qty"] <= qty:
                    self.remove_position(code)
                else:
                    pos["remaining_qty"] -= qty
                    self._save_positions()
        else:
            err = result.get("msg1", "알 수 없음")
            # "수량 초과" 오류 → 이미 매도된 상태일 가능성 → 실잔고 확인
            if "수량" in err and "초과" in err:
                logger.warning("%s 수량 초과 — 실잔고 확인 후 포지션 정리", name)
                try:
                    holdings = self.kis.get_balance()
                    held = {h["stock_code"]: h for h in holdings}
                    if code not in held:
                        self.bot.send_message(
                            f"🔄 {name} 이미 매도 확인 — 포지션 자동 정리"
                        )
                        self.remove_position(code)
                        return
                    actual_qty = held[code]["quantity"]
                    if actual_qty < qty:
                        pos["remaining_qty"] = actual_qty
                        self._save_positions()
                        self.bot.send_message(f"⚠️ {name} 잔량 불일치 — {qty}주→{actual_qty}주, {actual_qty}주 즉시 매도")
                        if actual_qty > 0:
                            self._execute_sell(code, pos, actual_qty, price, reason, pnl_pct)
                        return
                except Exception as e2:
                    logger.error("잔고 확인 실패: %s", e2)
            # 동일 에러 반복 방지: 이미 실패한 포지션은 에러 표시 저장
            last_err = pos.get("_last_sell_error", "")
            if err != last_err:
                self.bot.send_message(f"⚠️ {name} 매도 실패: {err}")
                pos["_last_sell_error"] = err
                self._save_positions()

    def get_daily_summary(self) -> str:
        if not self.trades_today and not self.positions:
            return "오늘 매매 내역 없음"

        lines = ["━━━ 📋 일일 리포트 ━━━"]
        lines.append(datetime.now(KST).strftime("%Y.%m.%d (%a)"))
        lines.append("")

        total_pnl = 0
        if self.trades_today:
            lines.append("■ 매매 내역")
            for t in self.trades_today:
                sign = "+" if t["pnl_amt"] >= 0 else ""
                emoji = "✅" if t["pnl_amt"] > 0 else ("❌" if t["pnl_amt"] < 0 else "➖")
                lines.append(f"{t['name']}  {sign}{t['pnl_amt']:,}원 ({sign}{t['pnl_pct']}%) {emoji}")
                total_pnl += t["pnl_amt"]

        lines.append("")
        sign = "+" if total_pnl >= 0 else ""
        lines.append(f"■ 오늘 총 수익: {sign}{total_pnl:,}원")

        if self.positions:
            lines.append("")
            lines.append("■ 잔여 포지션")
            for code, pos in self.positions.items():
                lines.append(f"  {pos['name']} {pos['remaining_qty']}주")

        wins = sum(1 for t in self.trades_today if t["pnl_amt"] > 0)
        losses = sum(1 for t in self.trades_today if t["pnl_amt"] < 0)
        if self.trades_today:
            lines.append(f"\n승률: {wins}승 {losses}패")

        return "\n".join(lines)

    def _save_positions(self):
        try:
            tmp = config.POSITIONS_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.positions, f, ensure_ascii=False, indent=2)
            os.rename(tmp, config.POSITIONS_FILE)
        except Exception as e:
            logger.error("포지션 저장 실패: %s", e)

    def _save_trades_today(self):
        try:
            data = {
                "date": datetime.now(KST).strftime("%Y-%m-%d"),
                "trades": self.trades_today,
            }
            tmp = config.TRADES_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.rename(tmp, config.TRADES_FILE)
        except Exception as e:
            logger.error("거래 내역 저장 실패: %s", e)

    def _load_trades_today(self):
        try:
            with open(config.TRADES_FILE, "r") as f:
                data = json.load(f)
            if data.get("date") == datetime.now(KST).strftime("%Y-%m-%d"):
                self.trades_today = data.get("trades", [])
                logger.info("오늘 거래 내역 로드: %d건", len(self.trades_today))
            else:
                self.trades_today = []
        except (FileNotFoundError, json.JSONDecodeError):
            self.trades_today = []

    def sync_with_balance(self) -> dict:
        """KIS 실잔고를 source of truth로 하여 positions.json 동기화."""
        if config.DRY_RUN:
            return {"added": [], "removed": [], "updated": []}
        try:
            holdings = self.kis.get_balance()
        except Exception as e:
            logger.error("잔고 조회 실패 — 동기화 스킵: %s", e)
            return {"added": [], "removed": [], "updated": []}

        kis_codes = {h["stock_code"]: h for h in holdings}
        pos_codes = set(self.positions.keys())

        added: list[dict] = []
        removed: list[str] = []
        updated: list[dict] = []

        # 1) KIS에 있는데 positions.json에 없는 종목 → 수동 매수로 추가
        for code, h in kis_codes.items():
            if code not in pos_codes:
                entry = h["avg_price"]
                if entry <= 0:
                    continue
                stop_loss = int(entry * (1 - config.MIN_STOP_LOSS_PCT / 100))
                self.add_position(
                    stock_code=code, name=h["name"],
                    quantity=h["quantity"], entry_price=entry,
                    target1=0, target2=0, stop_loss=stop_loss,
                )
                self.positions[code]["manual"] = True
                added.append(h)
                logger.info("동기화 추가 [수동]: %s %d주 @ %s원 (모니터링 제외)", h["name"], h["quantity"], f"{entry:,}")
            else:
                # 2) 양쪽에 있지만 수량 불일치 → KIS 수량으로 동기화
                pos = self.positions[code]
                kis_qty = h["quantity"]
                if pos["remaining_qty"] != kis_qty:
                    old_qty = pos["remaining_qty"]
                    pos["remaining_qty"] = kis_qty
                    pos["quantity"] = kis_qty
                    updated.append({"name": h["name"], "old": old_qty, "new": kis_qty})
                    logger.info("동기화 수량 업데이트: %s %d주→%d주 (KIS 기준)", h["name"], old_qty, kis_qty)

        # 3) positions.json에 있는데 KIS에 없는 종목 → 제거
        for code in list(pos_codes):
            if code not in kis_codes:
                name = self.positions[code].get("name", code)
                removed.append(name)
                self.remove_position(code)
                logger.info("동기화 제거: %s (실잔고에 없음)", name)

        if added or removed or updated:
            self._save_positions()

        return {"added": added, "removed": removed, "updated": updated}

    def _load_positions(self):
        try:
            with open(config.POSITIONS_FILE, "r") as f:
                self.positions = json.load(f)
            logger.info("포지션 로드: %d개", len(self.positions))
        except FileNotFoundError:
            self.positions = {}
        except Exception as e:
            logger.error("포지션 로드 실패: %s", e)
            self.positions = {}
