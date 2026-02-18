import logging
import time

import requests

import config

logger = logging.getLogger(__name__)

MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


class TelegramBot:
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._last_update_id = 0

    def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        try:
            for chunk in self._split(text, 4000):
                resp = requests.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": self.chat_id, "text": chunk, "parse_mode": "HTML"},
                    timeout=10,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("텔레그램 전송 실패: %s", e)
            return False

    def send_analysis_result(self, analysis: dict, total_capital: int):
        ma = analysis.get("marketAssessment", {})
        kospi = analysis.get("_kospi", {})
        kosdaq = analysis.get("_kosdaq", {})
        exr = analysis.get("_exchange_rate", {})

        header = (
            "━━━ 📊 데일리 분석 ━━━\n\n"
            f"■ 시장 상황\n"
            f"KOSPI: {kospi.get('index_price', '-')} ({kospi.get('change_rate', '-')}%)\n"
            f"KOSDAQ: {kosdaq.get('index_price', '-')} ({kosdaq.get('change_rate', '-')}%)\n"
            f"USD/KRW: {exr.get('exchange_rate', '-')}\n"
            f"단타 적합도: {ma.get('score', 0)}점 [{ma.get('recommendation', '-')}]\n\n"
        )

        themes = ma.get("favorableThemes", [])
        if themes:
            header += "■ 유리한 테마\n" + " ".join(f"#{t}" for t in themes) + "\n\n"

        header += f"■ 리스크 요인\n{ma.get('riskFactors', '-')}"
        self.send_message(header)

        picks = analysis.get("picks", [])
        for pick in picks:
            rank = pick.get("rank", 1)
            medal = MEDAL.get(rank, f"#{rank}")
            alloc = pick.get("allocation", 0)
            amount = int(total_capital * alloc / 100)
            price = pick.get("currentPrice", 0)
            conf = pick.get("confidence", 0)
            reason = pick.get("reason", {})
            ez = pick.get("entryZone", {})
            t1 = pick.get("target1", 0)
            t2 = pick.get("target2", 0)
            sl = pick.get("stopLoss", 0)
            ss = pick.get("sellStrategy", {})

            ez_hi = ez.get("high", 0)
            t1_pct = f"+{(t1 - ez_hi) / ez_hi * 100:.1f}%" if ez_hi else ""
            t2_pct = f"+{(t2 - ez_hi) / ez_hi * 100:.1f}%" if ez_hi else ""
            sl_pct = f"-{(ez.get('low', 0) - sl) / ez.get('low', 1) * 100:.1f}%" if ez.get("low") else ""

            msg = (
                f"━━━ {medal} {rank}순위: {pick.get('name', '')} ({pick.get('symbol', '')}) ━━━\n"
                f"배분: {alloc}% ({amount:,}원)\n"
                f"현재가: {price:,}원 | 신뢰도: {conf}%\n\n"
                f"📰 뉴스: {reason.get('news', '-')}\n"
                f"📈 수급: {reason.get('supply', '-')}\n"
                f"📊 차트: {reason.get('chart', '-')}\n\n"
                f"매수구간: {ez.get('low', 0):,} ~ {ez.get('high', 0):,}원\n"
                f"1차목표: {t1:,}원 ({t1_pct})\n"
                f"2차목표: {t2:,}원 ({t2_pct})\n"
                f"손절가: {sl:,}원 ({sl_pct})\n\n"
                f"매도전략:\n"
                f" ├ 돌파 성공 → {ss.get('breakoutHold', '-')}\n"
                f" ├ 돌파 실패 → {ss.get('breakoutFail', '-')}\n"
                f" ├ 거래대금 급감 → {ss.get('volumeDrop', '-')}\n"
                f" └ 11시 횡보 → {ss.get('sideways', '-')}"
            )
            self.send_message(msg)

            tags = pick.get("tags", [])
            if tags:
                self.send_message(" ".join(f"#{t}" for t in tags))

        ra = analysis.get("riskAnalysis", {})
        prob = ra.get("successProbability", 0)
        summary = analysis.get("marketSummary", "")

        footer = (
            f"━━━ ⚠️ 리스크 분석 ━━━\n"
            f"성공확률: {prob}%\n"
            f"{ra.get('failureFactors', '-')}\n\n"
            f"📋 시장 요약: {summary}\n\n"
            "━━━\n매수 진행? (ㅇㅇ / ㄴㄴ)"
        )
        self.send_message(footer)

    def send_buy_orders(self, orders: list[dict]):
        lines = ["✅ 매수 주문 발송\n"]
        total = 0
        for o in orders:
            lines.append(f"{o['name']} | {o['quantity']}주 × {o['price']:,}원 = {o['amount']:,}원")
            total += o["amount"]
        lines.append(f"\n총 주문: {total:,}원 / {config.TOTAL_CAPITAL:,}원")
        self.send_message("\n".join(lines))

    def send_fill_confirmation(self, fills: list[dict]):
        if not fills:
            self.send_message("⚠️ 체결된 주문이 없습니다.")
            return
        lines = ["✅ 체결 완료\n"]
        total = 0
        for f in fills:
            lines.append(f"{f['name']} {f['quantity']}주 × {f['price']:,}원")
            total += f.get("amount", f["quantity"] * f["price"])
        lines.append(f"\n총 투입: {total:,}원\n모니터링 시작 🔍")
        self.send_message("\n".join(lines))

    def send_daily_report(self, summary: str):
        self.send_message(summary)

    def wait_for_buy_confirmation(self, timeout: int) -> bool:
        deadline = time.time() + timeout
        self._flush_updates()
        while time.time() < deadline:
            updates = self._get_updates()
            for u in updates:
                msg = u.get("message", {})
                txt = msg.get("text", "").strip()
                cid = str(msg.get("chat", {}).get("id", ""))
                if cid != str(self.chat_id):
                    continue
                if txt in ("ㅇㅇ", "ㅇ", "go", "ㄱㄱ"):
                    self.send_message("👍 매수 진행합니다!")
                    return True
                if txt in ("ㄴㄴ", "ㄴ", "no"):
                    self.send_message("매수 취소.")
                    return False
            time.sleep(2)
        self.send_message("⏰ 시간 초과 — 오늘 매매 건너뜁니다.")
        return False

    def process_updates(self, kis_client, monitor):
        updates = self._get_updates()
        for u in updates:
            msg = u.get("message", {})
            txt = msg.get("text", "").strip()
            cid = str(msg.get("chat", {}).get("id", ""))
            if cid != str(self.chat_id):
                continue
            if txt == "/status":
                self._send_status(monitor, kis_client)
            elif txt == "/balance":
                self._send_balance(kis_client)
            elif txt == "/pnl":
                self.send_message(monitor.get_daily_summary())
            elif txt == "/stop":
                self.send_message("모니터링 종료합니다.")
                monitor.should_stop = True

    def _send_status(self, monitor, kis_client):
        if not monitor.positions:
            self.send_message("보유 종목 없음")
            return
        lines = ["<b>포지션 현황</b>\n"]
        for code, pos in monitor.positions.items():
            try:
                pd = kis_client.get_current_price(code)
                cur = pd["price"]
            except Exception:
                cur = 0
            entry = pos["entry_price"]
            pnl = (cur - entry) / entry * 100 if entry else 0
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"<b>{pos['name']}</b> ({code})\n"
                f"  현재 {cur:,}원 ({sign}{pnl:.1f}%)\n"
                f"  잔량 {pos['remaining_qty']}주 | T1{'✅' if pos['target1_hit'] else '❌'}\n"
                f"  목표1 {pos['target1']:,} | 목표2 {pos['target2']:,} | 손절 {pos['stop_loss']:,}\n"
            )
        self.send_message("\n".join(lines))

    def _send_balance(self, kis_client):
        try:
            holdings = kis_client.get_balance()
            if not holdings:
                self.send_message("보유 종목 없음")
                return
            lines = ["<b>계좌 잔고</b>\n"]
            for h in holdings:
                sign = "+" if h["pnl_pct"] >= 0 else ""
                lines.append(
                    f"<b>{h['name']}</b> {h['quantity']}주\n"
                    f"  {h['current_price']:,}원 ({sign}{h['pnl_pct']:.1f}%) {h['pnl_amt']:,}원\n"
                )
            cash = kis_client.get_available_cash()
            lines.append(f"\n예수금: {cash:,}원")
            self.send_message("\n".join(lines))
        except Exception as e:
            self.send_message(f"잔고 조회 오류: {e}")

    def _get_updates(self) -> list[dict]:
        try:
            resp = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self._last_update_id + 1, "timeout": 1, "allowed_updates": '["message"]'},
                timeout=5,
            )
            resp.raise_for_status()
            results = resp.json().get("result", [])
            if results:
                self._last_update_id = results[-1]["update_id"]
            return results
        except Exception:
            return []

    def _flush_updates(self):
        try:
            resp = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": -1, "timeout": 0},
                timeout=5,
            )
            results = resp.json().get("result", [])
            if results:
                self._last_update_id = results[-1]["update_id"]
        except Exception:
            pass

    @staticmethod
    def _split(text: str, max_len: int) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            idx = text.rfind("\n", 0, max_len)
            if idx == -1:
                idx = max_len
            chunks.append(text[:idx])
            text = text[idx:].lstrip("\n")
        return chunks
