import logging
import threading
import time

import requests

import config

logger = logging.getLogger(__name__)

MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


class TelegramBot:
    _active_poller = None

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._last_update_id = 0
        self._update_lock = threading.Lock()
        self._poll_thread = None
        self._poll_active = False
        self._poll_paused = False
        self._poll_kis = None
        self._poll_monitor = None
        self._reinvest_requested = False

    def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        if config.DRY_RUN and not text.startswith("[\uBAA8\uC758]"):
            text = f"[\uBAA8\uC758] {text}"
        try:
            for chunk in self._split(text, 2000):
                resp = requests.post(
                    f"{self.base_url}/sendMessage",
                    json={"chat_id": self.chat_id, "text": chunk, "parse_mode": "HTML"},
                    timeout=10,
                )
                if resp.status_code == 400:
                    # HTML \ud30c\uc2f1 \uc5d0\ub7ec \uc2dc plain text\ub85c \uc7ac\uc2dc\ub3c4
                    logger.warning("\ud154\ub808\uadf8\ub7a8 HTML \ud30c\uc2f1 \uc2e4\ud328 \u2014 plain text\ub85c \uc7ac\uc2dc\ub3c4")
                    resp = requests.post(
                        f"{self.base_url}/sendMessage",
                        json={"chat_id": self.chat_id, "text": chunk},
                        timeout=10,
                    )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("\ud154\ub808\uadf8\ub7a8 \uc804\uc1a1 \uc2e4\ud328: %s", e)
            return False

    def start_polling(self, kis_client, monitor):
        """백그라운드 텔레그램 명령어 폴링 시작."""
        if TelegramBot._active_poller:
            TelegramBot._active_poller.stop_polling()
            time.sleep(1)
        self._poll_kis = kis_client
        self._poll_monitor = monitor
        self._poll_active = True
        self._poll_thread = threading.Thread(
            target=self._bg_poll, daemon=True, name="tg-cmd",
        )
        self._poll_thread.start()
        TelegramBot._active_poller = self
        logger.info("텔레그램 명령어 폴링 시작")

    def stop_polling(self):
        """백그라운드 폴링 중지."""
        self._poll_active = False
        if TelegramBot._active_poller is self:
            TelegramBot._active_poller = None

    def _bg_poll(self):
        consecutive_failures = 0
        while self._poll_active:
            if not self._poll_paused and self._poll_kis and self._poll_monitor:
                try:
                    self.process_updates(self._poll_kis, self._poll_monitor)
                    consecutive_failures = 0
                except Exception as e:
                    consecutive_failures += 1
                    logger.error("텔레그램 폴링 오류 (%d회 연속): %s", consecutive_failures, e)
                    if consecutive_failures >= 10:
                        logger.error("텔레그램 폴링 10회 연속 실패 — 30초 대기")
                        time.sleep(30)
                        consecutive_failures = 0
            time.sleep(5)

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

            ez_hi = ez.get("high", 0) or 0
            ez_lo = ez.get("low", 0) or 0
            t1_pct = f"+{(t1 - ez_hi) / ez_hi * 100:.1f}%" if ez_hi > 0 else ""
            t2_pct = f"+{(t2 - ez_hi) / ez_hi * 100:.1f}%" if ez_hi > 0 else ""
            sl_pct = f"-{abs(ez_lo - sl) / ez_lo * 100:.1f}%" if ez_lo > 0 else ""

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
            "━━━\n자동 매수 모드 활성화"
        )
        self.send_message(footer)

    def send_buy_orders(self, orders: list[dict]):
        lines = ["✅ 매수 주문 발송\n"]
        total = 0
        for o in orders:
            lines.append(f"{o['name']} | {o['quantity']}주 × {o['price']:,}원 = {o['amount']:,}원")
            total += o["amount"]
        lines.append(f"\n총 주문: {total:,}원")
        self.send_message("\n".join(lines))

    def send_fill_confirmation(self, fills: list[dict], strategy: str = ""):
        if not fills:
            self.send_message("⚠️ 체결된 주문이 없습니다.")
            return
        strategy_label = {
            'momentum': '🚀 모멘텀',
            'pullback': '📉 눌림목 반등',
        }.get(strategy, '✅')
        lines = [f"{strategy_label} <b>체결 완료</b>\n"]
        total = 0
        for f in fills:
            lines.append(f"{f['name']} {f['quantity']}주 × {f['price']:,}원")
            total += f.get('amount', f['quantity'] * f['price'])
        lines.append(f"\n총 투입: {total:,}원\n모니터링 시작 🔍")
        self.send_message('\n'.join(lines))

    def send_daily_report(self, summary: str):
        self.send_message(summary)

    def wait_for_buy_confirmation(self, timeout: int) -> bool:
        self._poll_paused = True
        self._update_lock.acquire()
        try:
            self._flush_updates()
            deadline = time.time() + timeout
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
        finally:
            self._update_lock.release()
            self._poll_paused = False

    def process_updates(self, kis_client, monitor):
        if not self._update_lock.acquire(blocking=False):
            return
        try:
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
                elif txt == "/reinvest":
                    if self._reinvest_requested:
                        self.send_message("이미 재투자 요청 중입니다. 잠시 대기해주세요.")
                    else:
                        self._reinvest_requested = True
                        self.send_message("💰 재투자 요청 접수 — 잔여 현금으로 추가 매수를 진행합니다.")
                elif txt == "/help":
                    self.send_message(
                        "📋 <b>명령어 목록</b>\n\n"
                        "/status — 포지션 현황\n"
                        "/balance — 계좌 잔고\n"
                        "/pnl — 오늘 매매 내역\n"
                        "/cash — 예수금 확인\n"
                        "/reinvest — 잔여 현금 즉시 재투자\n"
                        "/sell 종목코드 — 수동 전량 매도\n"
                        "/stop — 모니터링 종료\n"
                        "/help — 명령어 목록"
                    )
                elif txt == "/cash":
                    try:
                        cash = kis_client.get_available_cash()
                        self.send_message(f"💰 매수가능금액: {cash:,}원")
                    except Exception as e:
                        self.send_message(f"예수금 조회 실패: {e}")
                elif txt.startswith("/sell "):
                    code = txt.split(" ", 1)[1].strip()
                    if code in monitor.positions:
                        pos = monitor.positions[code]
                        qty = pos["remaining_qty"]
                        if config.DRY_RUN:
                            self.send_message(f"✅ {pos['name']} {qty}주 시장가 매도 (모의)")
                        else:
                            try:
                                result = kis_client.place_sell_order(code, qty)
                                if result.get("rt_cd") == "0":
                                    self.send_message(f"✅ {pos['name']} {qty}주 시장가 매도 주문 완료")
                                else:
                                    self.send_message(f"⚠️ 매도 실패: {result.get('msg1', '알 수 없음')}")
                            except Exception as e:
                                self.send_message(f"매도 오류: {e}")
                    else:
                        self.send_message(f"포지션에 {code} 없음. /status로 확인하세요.")
        finally:
            self._update_lock.release()

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
