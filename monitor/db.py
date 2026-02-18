"""
Supabase DB 모듈 — 매매 이력, AI 분석, 일일 리포트 저장
"""

import json
import logging
import os
from datetime import datetime

import pytz
import requests

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


class Database:
    def __init__(self, url: str = "", key: str = ""):
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.key = key or SUPABASE_KEY
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        self.enabled = bool(self.url and self.key)
        if not self.enabled:
            logger.warning("Supabase 미설정 — DB 저장 비활성화")

    def _post(self, table: str, data: dict) -> bool:
        if not self.enabled:
            return False
        try:
            resp = requests.post(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                json=data,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                return True
            logger.error("DB insert 실패 [%s]: %s %s", table, resp.status_code, resp.text[:200])
            return False
        except Exception as e:
            logger.error("DB 연결 실패 [%s]: %s", table, e)
            return False

    # ──────────────────────────────────────
    # 매매 기록
    # ──────────────────────────────────────

    def save_trade(
        self,
        stock_code: str,
        stock_name: str,
        action: str,
        quantity: int,
        price: int,
        reason: str = "",
        pnl_amount: int = 0,
        pnl_pct: float = 0.0,
    ) -> bool:
        return self._post("trades", {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "action": action,
            "quantity": quantity,
            "price": price,
            "amount": price * quantity,
            "reason": reason,
            "pnl_amount": pnl_amount,
            "pnl_pct": round(pnl_pct, 2),
            "traded_at": datetime.now(KST).isoformat(),
        })

    # ──────────────────────────────────────
    # AI 분석 결과
    # ──────────────────────────────────────

    def save_analysis(self, analysis: dict) -> bool:
        assessment = analysis.get("marketAssessment", {})
        picks = analysis.get("picks", [])
        return self._post("ai_analyses", {
            "market_score": analysis.get("marketScore", 0),
            "recommendation": assessment.get("recommendation", ""),
            "risk_factors": assessment.get("riskFactors", ""),
            "favorable_themes": json.dumps(assessment.get("favorableThemes", []), ensure_ascii=False),
            "picks": json.dumps(picks, ensure_ascii=False),
            "risk_analysis": json.dumps(analysis.get("riskAnalysis", {}), ensure_ascii=False),
            "market_summary": analysis.get("marketSummary", ""),
            "success_probability": analysis.get("riskAnalysis", {}).get("successProbability", 0),
            "analyzed_at": datetime.now(KST).isoformat(),
        })

    # ──────────────────────────────────────
    # 일일 리포트
    # ──────────────────────────────────────

    def save_daily_report(
        self,
        trades: list[dict],
        remaining_positions: list[dict],
    ) -> bool:
        total_pnl = sum(t.get("pnl_amt", 0) for t in trades)
        total_invested = sum(t.get("entry", 0) * t.get("qty", 0) for t in trades)
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
        win = sum(1 for t in trades if t.get("pnl_amt", 0) > 0)
        loss = sum(1 for t in trades if t.get("pnl_amt", 0) < 0)

        return self._post("daily_reports", {
            "report_date": datetime.now(KST).strftime("%Y-%m-%d"),
            "total_trades": len(trades),
            "total_pnl": total_pnl,
            "total_pnl_pct": round(total_pnl_pct, 2),
            "win_count": win,
            "loss_count": loss,
            "trades": json.dumps(trades, ensure_ascii=False),
            "remaining_positions": json.dumps(remaining_positions, ensure_ascii=False),
        })
