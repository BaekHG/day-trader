import logging

from ai_analyzer import AIAnalyzer
from db import Database
from kis_client import KISClient
from telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


class Trader:
    def __init__(self, kis: KISClient, bot: TelegramBot, db: Database | None = None):
        self.kis = kis
        self.bot = bot
        self.db = db

    def calculate_orders(self, picks: list[dict], total_capital: int) -> list[dict]:
        orders = []
        for pick in picks:
            alloc = pick.get("allocation", 0)
            if alloc <= 0:
                continue
            allocated = total_capital * alloc / 100
            entry_high = pick.get("entryZone", {}).get("high", 0)
            if entry_high <= 0:
                continue
            qty = int(allocated // entry_high)
            if qty < 1:
                continue
            raw_reason = pick.get("reason", {})
            if isinstance(raw_reason, dict):
                reason_str = " / ".join(f"{k}: {v}" for k, v in raw_reason.items() if v)
            else:
                reason_str = str(raw_reason) if raw_reason else "AI 추천 매수"

            orders.append({
                "stock_code": pick["symbol"],
                "name": pick["name"],
                "quantity": qty,
                "price": entry_high,
                "amount": qty * entry_high,
                "allocation": alloc,
                "target1": pick.get("target1", 0),
                "target2": pick.get("target2", 0),
                "stop_loss": pick.get("stopLoss", 0),
                "sell_strategy": pick.get("sellStrategy", {}),
                "reason": reason_str,
            })
        return orders

    def execute_buy_orders(self, orders: list[dict]) -> list[dict]:
        results = []
        for order in orders:
            try:
                result = self.kis.place_buy_order(
                    order["stock_code"], order["quantity"], order["price"],
                )
                rt_cd = result.get("rt_cd", "")
                msg = result.get("msg1", "")
                success = rt_cd == "0"
                output = result.get("output", {})
                order_info = {
                    **order,
                    "success": success,
                    "message": msg,
                    "odno": output.get("ODNO", ""),
                    "ord_gno_brno": output.get("KRX_FWDG_ORD_ORGNO", ""),
                }
                results.append(order_info)
                if success:
                    logger.info("매수 주문 성공: %s %d주 × %s원", order["name"], order["quantity"], f"{order['price']:,}")
                    if self.db:
                        self.db.save_trade(
                            stock_code=order["stock_code"],
                            stock_name=order["name"],
                            action="buy",
                            quantity=order["quantity"],
                            price=order["price"],
                            reason="AI 추천 매수",
                        )
                else:
                    logger.error("매수 주문 실패: %s — %s", order["name"], msg)
            except Exception as e:
                logger.error("매수 주문 오류: %s — %s", order["name"], e)
                results.append({**order, "success": False, "message": str(e)})
        return results

    def cancel_unfilled_orders(self, pending_orders: list[dict]) -> list[dict]:
        cancelled = []
        for order in pending_orders:
            odno = order.get("odno", "")
            ord_gno_brno = order.get("ord_gno_brno", "")
            if not odno or not ord_gno_brno:
                logger.warning("주문번호 누락 — 취소 불가: %s", order.get("name", "?"))
                continue
            try:
                result = self.kis.cancel_order(ord_gno_brno, odno, order["remaining_qty"])
                success = result.get("rt_cd", "") == "0"
                if success:
                    logger.info("주문 취소 성공: %s (ODNO: %s)", order["name"], odno)
                    cancelled.append(order)
                else:
                    logger.error("주문 취소 실패: %s — %s", order["name"], result.get("msg1", ""))
            except Exception as e:
                logger.error("주문 취소 오류: %s — %s", order["name"], e)
        return cancelled

    def retry_with_reanalysis(
        self, cancelled_orders: list[dict], analyzer: AIAnalyzer,
    ) -> list[dict]:
        retry_results = []
        for order in cancelled_orders:
            code = order["stock_code"]
            name = order["name"]
            try:
                price_data = self.kis.get_current_price(code)
                current_price = price_data["price"]
                if current_price <= 0:
                    logger.warning("현재가 조회 실패: %s", name)
                    continue

                reanalysis = analyzer.reanalyze_entry(
                    stock_name=name,
                    stock_code=code,
                    original_price=order["order_price"],
                    current_price=current_price,
                    original_reason=order.get("reason", "AI 추천 매수"),
                )

                should_buy = reanalysis.get("should_buy", False)
                reason = reanalysis.get("reason", "")

                if not should_buy:
                    msg = f"❌ {name} 재분석 결과 매수 비추천\n현재가: {current_price:,}원\n사유: {reason}"
                    logger.info("재분석 매수 비추천: %s — %s", name, reason)
                    self.bot.send_message(msg)
                    retry_results.append({**order, "retried": False, "reason": reason})
                    continue

                suggested_price = reanalysis.get("suggested_price", current_price)
                qty = order["remaining_qty"]

                result = self.kis.place_buy_order(code, qty, suggested_price)
                success = result.get("rt_cd", "") == "0"
                output = result.get("output", {})
                msg_text = result.get("msg1", "")

                if success:
                    logger.info("재주문 성공: %s %d주 × %s원", name, qty, f"{suggested_price:,}")
                    self.bot.send_message(
                        f"🔄 {name} 재주문 성공\n"
                        f"현재가 매수: {qty}주 × {suggested_price:,}원\n"
                        f"재분석 사유: {reason}"
                    )
                    if self.db:
                        self.db.save_trade(
                            stock_code=code, stock_name=name,
                            action="buy", quantity=qty, price=suggested_price,
                            reason=f"재분석 매수: {reason}",
                        )
                else:
                    logger.error("재주문 실패: %s — %s", name, msg_text)
                    self.bot.send_message(f"⚠️ {name} 재주문 실패: {msg_text}")

                retry_results.append({
                    **order,
                    "retried": True,
                    "success": success,
                    "retry_price": suggested_price,
                    "odno": output.get("ODNO", ""),
                    "ord_gno_brno": output.get("KRX_FWDG_ORD_ORGNO", ""),
                    "reason": reason,
                })
            except Exception as e:
                logger.error("재분석/재주문 오류: %s — %s", name, e)
                self.bot.send_message(f"⚠️ {name} 재분석 오류: {e}")
                retry_results.append({**order, "retried": False, "reason": str(e)})
        return retry_results

    def check_fills(self, orders: list[dict]) -> list[dict]:
        try:
            fills_raw = self.kis.get_order_fills()
        except Exception as e:
            logger.error("체결 조회 실패: %s", e)
            return []

        order_codes = {o["stock_code"] for o in orders}
        fills = []
        for f in fills_raw:
            if f["stock_code"] in order_codes and f["quantity"] > 0:
                fills.append(f)
        return fills
