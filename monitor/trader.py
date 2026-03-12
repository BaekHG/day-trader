from __future__ import annotations

import logging

import config
from ai_analyzer import AIAnalyzer
from buy_lock import claim_stock_for_buy
from db import Database
from kis_client import KISClient
from telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


def round_to_tick(price: int) -> int:
    """주문 가격을 한국 주식시장 호가 단위로 올림 처리."""
    if price < 2_000:
        return price
    elif price < 5_000:
        tick = 5
    elif price < 20_000:
        tick = 10
    elif price < 50_000:
        tick = 50
    elif price < 200_000:
        tick = 100
    elif price < 500_000:
        tick = 500
    else:
        tick = 1_000
    # 올림: 매수 시 체결 가능성 높이기 위해 ceil
    return ((price + tick - 1) // tick) * tick


class Trader:
    def __init__(self, kis: KISClient, bot: TelegramBot, db: Database | None = None):
        self.kis = kis
        self.bot = bot
        self.db = db

    def calculate_orders(
        self,
        picks: list[dict],
        total_capital: int,
        sold_codes: set | None = None,
        phase: str = "morning",
    ) -> list[dict]:
        sold_codes = sold_codes or set()
        max_pos_pct = (
            config.AFTERNOON_MAX_POSITION_PCT
            if phase == "afternoon"
            else config.MAX_POSITION_PCT
        )
        orders = []
        for pick in picks[: config.MAX_PICKS]:
            if pick["symbol"] in sold_codes:
                logger.info(
                    "손실종목 재진입 차단: %s (%s)", pick["name"], pick["symbol"]
                )
                continue
            alloc = min(pick.get("allocation", 0), max_pos_pct)
            if alloc <= 0:
                continue
            allocated = total_capital * alloc / 100
            entry_low = pick.get("entryZone", {}).get("low", 0)
            if entry_low <= 0:
                continue
            qty = int(allocated // entry_low)
            if qty < 1:
                continue
            raw_reason = pick.get("reason", {})
            if isinstance(raw_reason, dict):
                reason_str = " / ".join(f"{k}: {v}" for k, v in raw_reason.items() if v)
            else:
                reason_str = str(raw_reason) if raw_reason else "AI 추천 매수"

            orders.append(
                {
                    "stock_code": pick["symbol"],
                    "name": pick["name"],
                    "quantity": qty,
                    "price": entry_low,
                    "amount": qty * entry_low,
                    "allocation": alloc,
                    "target1": pick.get("target1", 0),
                    "target2": pick.get("target2", 0),
                    "stop_loss": pick.get("stopLoss", 0),
                    "sell_strategy": pick.get("sellStrategy", {}),
                    "reason": reason_str,
                    "score": pick.get("score", 0),
                }
            )
        max_alloc = max_pos_pct * config.MAX_PICKS
        total_alloc = sum(o["allocation"] for o in orders)
        if total_alloc > max_alloc:
            logger.warning("배분 합계 %d%% > %d%% — 비례 축소", total_alloc, max_alloc)
            for o in orders:
                o["allocation"] = round(o["allocation"] * max_alloc / total_alloc, 1)
                o["amount"] = int(total_capital * o["allocation"] / 100)
                o["quantity"] = int(o["amount"] // o["price"]) if o["price"] > 0 else 0
            orders = [o for o in orders if o["quantity"] >= 1]
        return orders

    def execute_buy_orders(self, orders: list[dict]) -> list[dict]:
        results = []
        for order in orders:
            is_pyramid = order.get("reason", "").startswith("피라미딩")
            if not is_pyramid and not claim_stock_for_buy(order["stock_code"]):
                msg = "다른 봇이 이미 매수 — 중복 방지 스킵"
                logger.info("%s %s", order["name"], msg)
                self.bot.send_message(f"🔒 {order['name']} {msg}")
                results.append({**order, "success": False, "message": msg})
                continue
            try:
                # ── 현재가 확인 및 주문가 조정 ──
                try:
                    price_data = self.kis.get_current_price(order["stock_code"])
                    current_price = price_data["price"]
                except Exception as e:
                    logger.warning(
                        "%s 현재가 조회 실패 — AI 지정가 그대로 사용: %s",
                        order["name"],
                        e,
                    )
                    current_price = 0

                if current_price <= 0:
                    msg = "현재가 조회 실패 — 블라인드 주문 방지를 위해 매수 스킵"
                    logger.warning("%s %s", order["name"], msg)
                    self.bot.send_message(f"⏭ {order['name']} {msg}")
                    results.append({**order, "success": False, "message": msg})
                    continue

                ai_price = order["price"]
                deviation_pct = (
                    abs(current_price - ai_price) / ai_price * 100
                    if ai_price > 0
                    else 0
                )

                if current_price > ai_price * (
                    1 + config.MAX_ENTRY_DEVIATION_PCT / 100
                ):
                    msg = (
                        f"현재가({current_price:,}) > 지정가({ai_price:,}) "
                        f"{deviation_pct:.1f}%↑ — 진입구간 이탈로 매수 스킵"
                    )
                    logger.warning("%s %s", order["name"], msg)
                    self.bot.send_message(f"⏭ {order['name']} {msg}")
                    results.append({**order, "success": False, "message": msg})
                    continue

                if ai_price > current_price * (
                    1 + config.MAX_ENTRY_DEVIATION_PCT / 100
                ):
                    msg = (
                        f"지정가({ai_price:,}) > 현재가({current_price:,}) "
                        f"{deviation_pct:.1f}%↑ — 지정가 과대 괴리로 매수 스킵"
                    )
                    logger.warning("%s %s", order["name"], msg)
                    self.bot.send_message(f"⏭ {order['name']} {msg}")
                    results.append({**order, "success": False, "message": msg})
                    continue

                if current_price != ai_price:
                    if order.get("is_momentum"):
                        # 모멘텀: 최신 현재가 기준 +1% 상한 지정가 유지
                        adjusted_price = round_to_tick(int(current_price * 1.01))
                        logger.info(
                            "%s 모멘텀 상한지정가 갱신: %s → %s (현재가 %s +1%%)",
                            order["name"],
                            f"{ai_price:,}",
                            f"{adjusted_price:,}",
                            f"{current_price:,}",
                        )
                    else:
                        adjusted_price = current_price
                        logger.info(
                            "%s 주문가 조정: AI %s → 현재가 %s (%.1f%%)",
                            order["name"],
                            f"{ai_price:,}",
                            f"{current_price:,}",
                            deviation_pct,
                        )
                    order["price"] = adjusted_price
                    order["quantity"] = (
                        int(order["amount"] // adjusted_price)
                        if adjusted_price > 0
                        else order["quantity"]
                    )
                    if order["quantity"] < 1:
                        results.append(
                            {
                                **order,
                                "success": False,
                                "message": "현재가 기준 수량 부족",
                            }
                        )
                        continue
                    order["amount"] = order["quantity"] * adjusted_price

                    # 손절가도 현재가 기준으로 재계산
                    if ai_price > 0 and order.get("stop_loss", 0) > 0:
                        stop_pct = (ai_price - order["stop_loss"]) / ai_price
                    else:
                        stop_pct = 0
                    stop_pct = max(stop_pct, config.MIN_STOP_LOSS_PCT / 100)
                    order["stop_loss"] = int(current_price * (1 - stop_pct))
                    logger.info(
                        "%s 손절가 조정: → %s원 (%.1f%%)",
                        order["name"],
                        f"{order['stop_loss']:,}",
                        stop_pct * 100,
                    )

                if config.DRY_RUN:
                    logger.info(
                        "[모의] 매수 시뮬레이션: %s %d주 × %s원",
                        order["name"],
                        order["quantity"],
                        f"{order['price']:,}",
                    )
                    results.append(
                        {
                            **order,
                            "success": True,
                            "message": "[모의] 시뮬레이션 체결",
                            "odno": "DRY_RUN",
                            "ord_gno_brno": "DRY_RUN",
                        }
                    )
                    continue

                result = self.kis.place_buy_order(
                    order["stock_code"],
                    order["quantity"],
                    order["price"],
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
                    logger.info(
                        "매수 주문 성공: %s %d주 × %s원",
                        order["name"],
                        order["quantity"],
                        f"{order['price']:,}",
                    )
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
        if config.DRY_RUN:
            return []
        cancelled = []
        for order in pending_orders:
            odno = order.get("odno", "")
            ord_gno_brno = order.get("ord_gno_brno", "")
            if not odno or not ord_gno_brno:
                logger.warning("주문번호 누락 — 취소 불가: %s", order.get("name", "?"))
                continue
            try:
                result = self.kis.cancel_order(
                    ord_gno_brno, odno, order["remaining_qty"]
                )
                success = result.get("rt_cd", "") == "0"
                if success:
                    logger.info("주문 취소 성공: %s (ODNO: %s)", order["name"], odno)
                    cancelled.append(order)
                else:
                    logger.error(
                        "주문 취소 실패: %s — %s", order["name"], result.get("msg1", "")
                    )
            except Exception as e:
                logger.error("주문 취소 오류: %s — %s", order["name"], e)
        return cancelled

    def retry_with_reanalysis(
        self,
        cancelled_orders: list[dict],
        analyzer: AIAnalyzer,
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

                suggested_price = round_to_tick(
                    int(reanalysis.get("suggested_price", current_price))
                )
                qty = order["remaining_qty"]

                result = self.kis.place_buy_order(code, qty, suggested_price)
                success = result.get("rt_cd", "") == "0"
                output = result.get("output", {})
                msg_text = result.get("msg1", "")

                if success:
                    logger.info(
                        "재주문 성공: %s %d주 × %s원", name, qty, f"{suggested_price:,}"
                    )
                    self.bot.send_message(
                        f"🔄 {name} 재주문 성공\n"
                        f"현재가 매수: {qty}주 × {suggested_price:,}원\n"
                        f"재분석 사유: {reason}"
                    )
                    if self.db:
                        self.db.save_trade(
                            stock_code=code,
                            stock_name=name,
                            action="buy",
                            quantity=qty,
                            price=suggested_price,
                            reason=f"재분석 매수: {reason}",
                        )
                else:
                    logger.error("재주문 실패: %s — %s", name, msg_text)
                    self.bot.send_message(f"⚠️ {name} 재주문 실패: {msg_text}")

                retry_results.append(
                    {
                        **order,
                        "retried": True,
                        "success": success,
                        "retry_price": suggested_price,
                        "odno": output.get("ODNO", ""),
                        "ord_gno_brno": output.get("KRX_FWDG_ORD_ORGNO", ""),
                        "reason": reason,
                    }
                )
            except Exception as e:
                logger.error("재분석/재주문 오류: %s — %s", name, e)
                self.bot.send_message(f"⚠️ {name} 재분석 오류: {e}")
                retry_results.append({**order, "retried": False, "reason": str(e)})
        return retry_results

    def check_fills(self, orders: list[dict]) -> list[dict]:
        if config.DRY_RUN:
            return [
                {
                    "stock_code": o["stock_code"],
                    "name": o["name"],
                    "quantity": o["quantity"],
                    "price": o["price"],
                    "amount": o["quantity"] * o["price"],
                }
                for o in orders
            ]
        try:
            fills_raw = self.kis.get_order_fills(sll_buy_dvsn="02")
        except Exception as e:
            logger.error("체결 조회 실패: %s", e)
            return None

        # 주문번호(odno)로 매칭 — 동일 종목 이전 체결 중복 방지
        order_odnos = {o["odno"] for o in orders if o.get("odno")}
        fills = []
        if order_odnos:
            # odno로 정확히 매칭 (정상 케이스)
            for f in fills_raw:
                if f.get("odno") in order_odnos and f["quantity"] > 0:
                    fills.append(f)
        else:
            # odno 없으면 stock_code fallback (하위 호환)
            order_codes = {o["stock_code"] for o in orders}
            for f in fills_raw:
                if f["stock_code"] in order_codes and f["quantity"] > 0:
                    fills.append(f)
        return fills
