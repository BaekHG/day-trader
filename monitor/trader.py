import logging

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
                results.append({**order, "success": success, "message": msg})
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
