import json
import logging
import re
import time
from datetime import datetime

import pytz
import requests

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

SYSTEM_PROMPT = """역할:
너는 300만원 소자본 한국 주식 초단타 리스크 심사관이다.
종목 선정은 정량 스코어링 시스템이 이미 완료했다.
너의 역할은 스코어 1위 종목의 뉴스/리스크를 확인하여 매수 승인 또는 거부(veto)하는 것이다.

판단 기준:
1. 뉴스 리스크: 악재 뉴스(소송, 횡령, 적자, 감사의견 거절, 대규모 유상증자 등)가 있으면 거부
2. 시장 리스크: 시장 전체가 급락(-2%+) 중이면 거부
3. 종목 리스크: VI 발동 이력, 시총 1000억 미만, 당일 +10% 이상 급등은 거부
4. 뉴스 촉매 확인: 긍정적 촉매(실적, 수주, 정책, 테마)가 있으면 승인에 가산

원칙:
- 확실한 악재가 없으면 승인하라. 스코어링이 이미 수급/차트/모멘텀을 검증했다.
- 애매하면 승인하라. 거부는 명확한 근거가 있을 때만.
- 수익률 예측 금지. 거부 사유 또는 승인 근거만 서술.

반드시 아래 JSON 형식으로만 응답하세요.
절대로 ```json 코드블록, 설명, 주석, 마크다운 등 JSON 외의 텍스트를 포함하지 마세요.
순수 JSON만 출력하세요. 첫 문자는 반드시 { 이어야 합니다:
{
  "marketAssessment": {
    "score": 단타적합도점수(0-100),
    "riskFactors": "시장 리스크 요인 (한국어)",
    "favorableThemes": ["유리한 테마1", "테마2"],
    "recommendation": "매매추천" 또는 "매매비추천"
  },
  "vetoResult": {
    "approved": true 또는 false,
    "reason": "승인/거부 근거 (한국어, 2-3문장)",
    "newsRisk": "뉴스 기반 리스크 분석 (한국어, 1-2문장)",
    "confidence": 신뢰도(0-100)
  },
  "picks": [
    {
      "rank": 1,
      "symbol": "종목코드",
      "name": "종목명",
      "currentPrice": 현재가,
      "reason": {
        "news": "뉴스 촉매 유무 및 내용 (1문장)",
        "supply": "수급 분석 요약 (1문장)",
        "chart": "차트 패턴 요약 (1문장)"
      },
      "setupType": ["해당_셋업_태그"],
      "positionFromHigh": 고점대비현재위치,
      "entryZone": {"low": 매수구간하단, "high": 매수구간상단},
      "stopLoss": 손절가,
      "target1": 1차목표가,
      "target2": 2차목표가,
      "confidence": 신뢰도(0-100),
      "tags": ["태그1", "태그2"],
      "allocation": 70,
      "sellStrategy": {
        "breakoutHold": "돌파 시 트레일링 스탑 유지 (한국어)",
        "breakoutFail": "돌파 실패 시 즉시 손절 (한국어)",
        "volumeDrop": "거래대금 급감 시 청산 (한국어)",
        "sideways": "30분 횡보 시 시간 청산 (한국어)"
      }
    }
  ],
  "riskAnalysis": {
    "failureFactors": "실패 확률 요인 (한국어, 2-3문장)",
    "successProbability": 종합성공확률(0-100)
  },
  "marketSummary": "전체 시장 요약 (한국어, 3-4문장)",
  "marketScore": 시장점수(0-100)
}

vetoResult.approved가 false이면 picks는 빈 배열 []로 설정.
vetoResult.approved가 true이면 스코어 1위 종목을 picks에 포함 (allocation=70 고정).
entryZone은 현재가 ±0.5%, target1=현재가×1.02, target2=현재가×1.03, stopLoss=현재가×0.988.
매매비추천인 경우 picks는 빈 배열 []로 설정하되 나머지는 반드시 채워라.
모든 텍스트는 반드시 한국어로 작성하세요."""


class AIAnalyzer:
    def __init__(self, api_key: str, provider: str = "anthropic"):
        self.api_key = api_key
        self.provider = provider

    def analyze(
        self,
        enriched_stocks: list[dict],
        up_ranking: list[dict],
        down_ranking: list[dict],
        kospi_index: dict,
        kosdaq_index: dict,
        exchange_rate: dict,
        is_market_open: bool,
        current_positions=None,
    ) -> dict:
        user_prompt = self._build_user_prompt(
            enriched_stocks, up_ranking, down_ranking,
            kospi_index, kosdaq_index, exchange_rate, is_market_open,
            current_positions=current_positions,
        )

        if self.provider == "anthropic":
            return self._call_anthropic(user_prompt)
        return self._call_openai(user_prompt)

    @staticmethod
    def _extract_json(text: str) -> dict:
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass

        md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if md_match:
            try:
                return json.loads(md_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return json.loads(text[first:last + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Claude 응답에서 유효한 JSON을 추출할 수 없습니다: {text[:200]}...")

    def _call_anthropic(self, user_prompt: str) -> dict:
        last_error = Exception("재시도 모두 실패")
        for attempt in range(3):
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 6000,
                        "system": SYSTEM_PROMPT,
                        "messages": [
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["content"][0]["text"]
                parsed = self._extract_json(content)
                usage = data.get("usage", {})
                logger.info("Claude 분석 완료 — 토큰: input=%s output=%s",
                            usage.get("input_tokens", "?"), usage.get("output_tokens", "?"))
                return parsed
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (429, 503, 529) and attempt < 2:
                    wait = 2 ** attempt * 5
                    logger.warning("Claude API 재시도 %d/3 (HTTP %d)", attempt + 1, status)
                    time.sleep(wait)
                    last_error = e
                else:
                    raise
        raise last_error  # type: ignore[misc]

    def _call_openai(self, user_prompt: str) -> dict:
        last_error = Exception("재시도 모두 실패")
        for attempt in range(3):
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2,
                        "max_tokens": 6000,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                logger.info("OpenAI 분석 완료 — 토큰 사용: %s", data.get("usage", {}))
                return parsed
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (429, 503, 529) and attempt < 2:
                    wait = 2 ** attempt * 5
                    logger.warning("OpenAI API 재시도 %d/3 (HTTP %d)", attempt + 1, status)
                    time.sleep(wait)
                    last_error = e
                else:
                    raise
        raise last_error  # type: ignore[misc]

    def reanalyze_entry(
        self,
        stock_name: str,
        stock_code: str,
        original_price: int,
        current_price: int,
        original_reason: str,
    ) -> dict:
        price_diff_pct = ((current_price - original_price) / original_price) * 100
        prompt = (
            f"기존에 {stock_name}({stock_code})을 {original_price:,}원에 지정가 매수 주문했으나 미체결되었습니다.\n"
            f"현재가: {current_price:,}원 (주문가 대비 {price_diff_pct:+.1f}%)\n"
            f"기존 매수 근거: {original_reason}\n\n"
            f"현재가 {current_price:,}원에 매수 진입해도 괜찮은지 판단해주세요.\n"
            f"초단타(15~30분 보유, +2% 목표, -1.2% 손절) 관점에서 리스크/리워드를 분석하세요.\n\n"
            "반드시 아래 JSON 형식으로만 응답하세요. "
            "절대로 JSON 외의 텍스트를 포함하지 마세요. 첫 문자는 반드시 { 이어야 합니다:\n"
            '{\n'
            '  "should_buy": true 또는 false,\n'
            '  "reason": "판단 근거 (한국어, 2-3문장)",\n'
            '  "suggested_price": 추천매수가격(정수)\n'
            '}'
        )

        if self.provider == "anthropic":
            return self._call_anthropic_light(prompt)
        return self._call_openai_light(prompt)

    def _call_anthropic_light(self, prompt: str) -> dict:
        last_error = Exception("재시도 모두 실패")
        for attempt in range(2):
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 500,
                        "system": "너는 한국 주식 단타 전문가다. 미체결 주문의 현재가 재진입 여부를 판단한다. 순수 JSON만 출력하라.",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                content = resp.json()["content"][0]["text"]
                return self._extract_json(content)
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (429, 503, 529) and attempt < 1:
                    wait = 5
                    logger.warning("Claude light API 재시도 %d/2 (HTTP %d)", attempt + 1, status)
                    time.sleep(wait)
                    last_error = e
                else:
                    raise
        raise last_error  # type: ignore[misc]

    def _call_openai_light(self, prompt: str) -> dict:
        last_error = Exception("재시도 모두 실패")
        for attempt in range(2):
            try:
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [
                            {"role": "system", "content": "너는 한국 주식 단타 전문가다. 미체결 주문의 현재가 재진입 여부를 판단한다."},
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0,
                        "max_tokens": 500,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                return json.loads(resp.json()["choices"][0]["message"]["content"])
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status in (429, 503, 529) and attempt < 1:
                    wait = 5
                    logger.warning("OpenAI light API 재시도 %d/2 (HTTP %d)", attempt + 1, status)
                    time.sleep(wait)
                    last_error = e
                else:
                    raise
        raise last_error  # type: ignore[misc]

    def _build_user_prompt(
        self,
        enriched_stocks: list[dict],
        up_ranking: list[dict],
        down_ranking: list[dict],
        kospi_index: dict,
        kosdaq_index: dict,
        exchange_rate: dict,
        is_market_open: bool,
        current_positions=None,
    ) -> str:
        now = datetime.now(KST)
        time_str = now.strftime("%Y.%m.%d %H:%M")
        lines = []

        lines.append(f"=== 시장 데이터 ({time_str}) ===")
        if is_market_open:
            lines.append("[장중 실시간 데이터]")
        elif now.hour < 9:
            lines.append("[장 시작 전 — 전일 마감 데이터 기반 프리마켓 분석]")
            lines.append("※ 당일 거래량/거래대금 0은 정상 (장 시작 전). 전일 일봉, 수급, 뉴스로 오늘 종목을 선정하세요.")
        else:
            lines.append("[장 마감 — 전일 마감 데이터]")
        lines.append("")

        # Market indices
        lines.append("【시장 지수】")
        if kospi_index:
            lines.append(
                f"KOSPI: {kospi_index.get('index_price', '-')} "
                f"({kospi_index.get('change_rate', '-')}%) "
                f"거래대금: {kospi_index.get('trading_value', '-')}"
            )
        if kosdaq_index:
            lines.append(
                f"KOSDAQ: {kosdaq_index.get('index_price', '-')} "
                f"({kosdaq_index.get('change_rate', '-')}%) "
                f"거래대금: {kosdaq_index.get('trading_value', '-')}"
            )
        if exchange_rate:
            lines.append(
                f"USD/KRW: {exchange_rate.get('exchange_rate', '-')} "
                f"({exchange_rate.get('change_rate', '-')})"
            )
        lines.append("")

        # Enriched stocks
        lines.append("【거래량 상위 종목 — 심층 데이터】")
        for i, item in enumerate(enriched_stocks):
            name = item.get("hts_kor_isnm", "")
            code = item.get("mksc_shrn_iscd", "")
            price = item.get("stck_prpr", "")
            rate = item.get("prdy_ctrt", "")
            vol = item.get("acml_vol", "")
            tv = item.get("acml_tr_pbmn", "")

            lines.append(f"{i+1}. {name} ({code})")
            lines.append(f"   현재가: {price} | 등락률: {rate}% | 거래량: {vol} | 거래대금: {tv}")

            pos = item.get("position_from_high")
            high20 = item.get("high_20d")
            if pos is not None and high20 is not None:
                lines.append(f"   20일고점: {high20} | 고점대비: {pos:.1f}%")

            foreign = item.get("foreign_institution", [])
            if foreign:
                parts = []
                for j, d in enumerate(foreign[:5]):
                    dt = d.get("stck_bsop_date", f"D-{j}")
                    fq = d.get("frgn_ntby_qty", "-")
                    oq = d.get("orgn_ntby_qty", "-")
                    parts.append(f"[{dt}]외{fq}/기{oq}")
                lines.append(f"   수급(최근{len(foreign[:5])}일): {' '.join(parts)}")

                consec = 0
                for d in foreign[:5]:
                    qty = int(str(d.get("frgn_ntby_qty", "0")).replace(",", "") or "0")
                    if qty > 0:
                        consec += 1
                    else:
                        break
                if consec >= 2:
                    lines.append(f"   → 외국인 {consec}일 연속 순매수")

            candles = item.get("recent_daily_candles", [])
            if candles:
                lines.append("   최근일봉:")
                for c in candles:
                    lines.append(
                        f"     {c['date']} 시{c['open']} 고{c['high']} "
                        f"저{c['low']} 종{c['close']} 거래량{c['volume']}"
                    )

            m_candles = item.get("minute_candles_5m", [])
            if m_candles:
                lines.append("   5분봉(최근1시간):")
                for c in m_candles:
                    lines.append(
                        f"     {c['time']} 시{c['open']} 고{c['high']} "
                        f"저{c['low']} 종{c['close']} 거래량{c['volume']}"
                    )

            news = item.get("news_headlines", [])
            if news:
                titles = [n["title"] if isinstance(n, dict) else str(n) for n in news[:5]]
                lines.append(f"   뉴스: {' | '.join(titles)}")

            lines.append("")

        # Up/down rankings
        lines.append("【상승률 상위 TOP 15】")
        for i, item in enumerate(up_ranking[:15]):
            lines.append(
                f"{i+1}. {item.get('hts_kor_isnm', '')} "
                f"({item.get('mksc_shrn_iscd', '')}) "
                f"{item.get('stck_prpr', '')} {item.get('prdy_ctrt', '')}% "
                f"거래량{item.get('acml_vol', '')} 거래대금{item.get('acml_tr_pbmn', '')}"
            )
        lines.append("")

        lines.append("【하락률 상위 TOP 15】")
        for i, item in enumerate(down_ranking[:15]):
            lines.append(
                f"{i+1}. {item.get('hts_kor_isnm', '')} "
                f"({item.get('mksc_shrn_iscd', '')}) "
                f"{item.get('stck_prpr', '')} {item.get('prdy_ctrt', '')}% "
                f"거래량{item.get('acml_vol', '')} 거래대금{item.get('acml_tr_pbmn', '')}"
            )
        lines.append("")

        if current_positions:
            lines.append("【현재 보유 포지션 — 중복 추천 금지】")
            for pos in current_positions:
                lines.append(f"  - {pos.get('name', '?')} ({pos.get('code', '?')}) {pos.get('remaining_qty', '?')}주")
            lines.append("위 보유 종목은 반드시 추천에서 제외하세요.")
            lines.append("")

        top_stock = enriched_stocks[0] if enriched_stocks else None
        if top_stock:
            score_detail = top_stock.get("score_detail", {})
            lines.append("【정량 스코어 1위 종목 — 매수 후보】")
            lines.append(
                f"  {top_stock.get('hts_kor_isnm', '?')} ({top_stock.get('mksc_shrn_iscd', '?')}) "
                f"스코어: {top_stock.get('score', 0)}점"
            )
            lines.append(f"  {score_detail.get('breakdown', '')}")
            lines.append("")

        lines.append(
            "정량 스코어링 시스템이 위 종목을 1위로 선정했습니다. "
            "너의 역할은 뉴스/리스크 기반으로 이 종목의 매수를 승인 또는 거부(veto)하는 것입니다. "
            "명확한 악재가 없으면 승인하세요. allocation은 70 고정. "
            "시장 전체 리스크도 평가하세요. "
            "반드시 데이터 기반으로 판단하고, JSON 형식으로 응답하세요."
        )

        return "\n".join(lines)
