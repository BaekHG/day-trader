import json
import logging
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
        self._load_positions()
        self._load_trades_today()

    def add_position(
        self, stock_code: str, name: str, quantity: int, entry_price: int,
        target1: int, target2: int, stop_loss: int, sell_strategy: dict | None = None,
    ):
        self.positions[stock_code] = {
            "name": name, "quantity": quantity, "remaining_qty": quantity,
            "entry_price": entry_price, "target1": target1, "target2": target2,
            "stop_loss": stop_loss, "high_since_entry": entry_price,
            "target1_hit": False, "sell_strategy": sell_strategy or {},
            "entry_time": datetime.now(KST).isoformat(),
        }
        self._save_positions()
        logger.info("포지션 추가: %s %d주 @ %s원", name, quantity, f"{entry_price:,}")

    def remove_position(self, stock_code: str):
        if stock_code in self.positions:
            del self.positions[stock_code]
            self._save_positions()

    def check_positions(self):
        now = datetime.now(KST)
        force_hh, force_mm = map(int, config.FORCE_CLOSE_TIME.split(":"))

        for code, pos in list(self.positions.items()):
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

            if now.hour > force_hh or (now.hour == force_hh and now.minute >= force_mm):
                self._execute_sell(code, pos, remaining, current, f"{config.FORCE_CLOSE_TIME} 강제 청산", pnl_pct)
                continue

            # 진입 직후 손절 유예 체크
            entry_time_val = pos.get("entry_time", "")
            in_grace = False
            if entry_time_val:
                try:
                    et = datetime.fromisoformat(entry_time_val)
                    secs_since = (now - et).total_seconds()
                    if secs_since < config.STOP_LOSS_GRACE_MINUTES * 60:
                        in_grace = True
                        logger.info(
                            "%s | 진입 후 %.0f초 — 손절 유예 중 (%d분 유예)",
                            pos["name"], secs_since, config.STOP_LOSS_GRACE_MINUTES,
                        )
                except (ValueError, TypeError):
                    pass

            if not in_grace:
                effective_stop = pos["stop_loss"]
                high_pnl = (pos["high_since_entry"] - entry) / entry * 100 if entry else 0
                for level_pnl, stop_pnl in config.TRAILING_STOP_LEVELS:
                    if high_pnl >= level_pnl:
                        trailing_stop = int(entry * (1 + stop_pnl / 100))
                        effective_stop = max(effective_stop, trailing_stop)
                        break
                if current <= effective_stop:
                    if effective_stop > pos["stop_loss"]:
                        reason = f"트레일링 스탑 (고점 +{high_pnl:.1f}% → 손절선 +{((effective_stop - entry) / entry * 100):.1f}%)"
                    else:
                        reason = "손절"
                    self._execute_sell(code, pos, remaining, current, reason, pnl_pct)
                    continue

            if current >= pos["target1"] and not pos["target1_hit"]:
                sell_qty = remaining // 2
                if sell_qty < 1:
                    sell_qty = remaining
                self._execute_sell(code, pos, sell_qty, current, "1차 목표 도달", pnl_pct)
                if remaining - sell_qty > 0:
                    pos["target1_hit"] = True
                    pos["remaining_qty"] = remaining - sell_qty
                    self._save_positions()
                continue

            if current >= pos["target2"] and pos["target1_hit"]:
                self._execute_sell(code, pos, remaining, current, "2차 목표 도달", pnl_pct)
                continue

            entry_time_str = pos.get("entry_time", "")
            if entry_time_str:
                entry_dt = datetime.fromisoformat(entry_time_str)
                hold_minutes = (now - entry_dt).total_seconds() / 60
                if hold_minutes >= config.MAX_HOLD_MINUTES and not pos["target1_hit"] and abs(pnl_pct) < 1.0:
                    self._execute_sell(
                        code, pos, remaining, current,
                        f"{config.MAX_HOLD_MINUTES}분 횡보 — 전량 매도", pnl_pct,
                    )
                    continue

            logger.info(
                "%s | %s원 (%.1f%%) | 고점 %s | 잔량 %d주",
                pos["name"], f"{current:,}", pnl_pct, f"{pos['high_since_entry']:,}", remaining,
            )

    def _execute_sell(self, code: str, pos: dict, qty: int, price: int, reason: str, pnl_pct: float):
        name = pos["name"]
        entry = pos["entry_price"]
        pnl_amt = (price - entry) * qty

        try:
            result = self.kis.place_sell_order(code, qty)
            success = result.get("rt_cd") == "0"
        except Exception as e:
            logger.error("매도 주문 실패 %s: %s", name, e)
            self.bot.send_message(f"⚠️ {name} 매도 실패: {e}")
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
            })
            self._save_trades_today()

            if self.db:
                self.db.save_trade(
                    stock_code=code,
                    stock_name=name,
                    action="sell",
                    quantity=qty,
                    price=price,
                    reason=reason,
                    pnl_amount=pnl_amt,
                    pnl_pct=pnl_pct,
                )

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
                        self.bot.send_message(
                            f"⚠️ {name} 잔량 불일치 — {qty}주→{actual_qty}주 수정"
                        )
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
            with open(config.POSITIONS_FILE, "w") as f:
                json.dump(self.positions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("포지션 저장 실패: %s", e)

    def _save_trades_today(self):
        try:
            data = {
                "date": datetime.now(KST).strftime("%Y-%m-%d"),
                "trades": self.trades_today,
            }
            with open(config.TRADES_FILE, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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
        try:
            holdings = self.kis.get_balance()
        except Exception as e:
            logger.error("잔고 조회 실패 — 동기화 스킵: %s", e)
            return {"added": [], "removed": []}

        kis_codes = {h["stock_code"]: h for h in holdings}
        pos_codes = set(self.positions.keys())

        added: list[dict] = []
        removed: list[str] = []

        for code, h in kis_codes.items():
            if code not in pos_codes:
                entry = h["avg_price"]
                if entry <= 0:
                    continue
                target1 = int(entry * 1.05)
                target2 = int(entry * 1.10)
                stop_loss = int(entry * 0.97)
                self.add_position(
                    stock_code=code, name=h["name"],
                    quantity=h["quantity"], entry_price=entry,
                    target1=target1, target2=target2, stop_loss=stop_loss,
                )
                added.append(h)
                logger.info("동기화 추가: %s %d주 @ %s원", h["name"], h["quantity"], f"{entry:,}")

        for code in list(pos_codes):
            if code not in kis_codes:
                name = self.positions[code].get("name", code)
                removed.append(name)
                self.remove_position(code)
                logger.info("동기화 제거: %s (실잔고에 없음)", name)

        if added or removed:
            self._save_positions()

        return {"added": added, "removed": removed}

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
