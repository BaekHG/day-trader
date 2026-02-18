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

            if current <= pos["stop_loss"]:
                self._execute_sell(code, pos, remaining, current, "손절", pnl_pct)
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

            if pos["target1_hit"]:
                trailing_price = int(pos["high_since_entry"] * (1 - config.TRAILING_STOP_PCT / 100))
                if current <= trailing_price:
                    self._execute_sell(
                        code, pos, remaining, current,
                        f"트레일링 스탑 (고점 {pos['high_since_entry']:,}→{trailing_price:,})", pnl_pct,
                    )
                    continue

            if now.hour >= 11 and not pos["target1_hit"]:
                entry_date = pos.get("entry_time", "")[:10]
                today_str = now.strftime("%Y-%m-%d")
                if entry_date == today_str and abs(pnl_pct) < 1.0:
                    self._execute_sell(code, pos, remaining, current, "11시 횡보 — 전량 매도", pnl_pct)
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
            self.bot.send_message(f"⚠️ {name} 매도 실패: {err}")

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
