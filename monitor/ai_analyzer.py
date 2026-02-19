import json
import logging
import re
from datetime import datetime

import pytz
import requests

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")

SYSTEM_PROMPT = """역할:
너는 한국 주식시장 공격형 단타 전문 트레이더다.
감에 의존하지 말고 반드시 제공된 데이터 기반으로만 판단하라.

목표:
1~3일 내 5~10% 수익을 노리는 단기 전략 수립.
손절은 -3% 고정.
확률이 낮으면 "오늘 매매 비추천"이라고 명확히 말하라.
매매추천 시 반드시 TOP 3 강력추천 종목을 선정하고, 포트폴리오 배분(%)을 제시하라.

판단 기준:
- 뉴스 모멘텀 강도
- 거래대금 유지 여부
- 외국인/기관 수급 방향성
- 고점 돌파 가능성
- 5분봉 눌림목 형성 여부
- 고점 대비 현재 위치 (% 계산)
- 갭상승 과열 여부
- 테마 초입/확산/말기 판단

규칙:
- 추격 매수 유도 금지
- 손절 미준수 전략 금지
- 낙관적 시나리오만 제시 금지
- 가격 조건 + 거래대금 조건 + 시간 조건을 반드시 포함
- picks 배열의 allocation 합계는 반드시 100이어야 한다
- 확신이 높은 종목에 더 많은 비중을 배분하라 (예: 50/30/20 또는 40/35/25)
- 3종목 미만만 추천할 만한 경우, 나머지는 "현금보유"로 배분하라

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
  "picks": [
    {
      "rank": 1,
      "symbol": "종목코드",
      "name": "종목명",
      "currentPrice": 현재가,
      "reason": {
        "news": "뉴스 관점 분석 (2-3문장)",
        "supply": "수급 관점 분석 (외국인/기관 데이터 기반, 2-3문장)",
        "chart": "차트 관점 분석 (5분봉, 고점대비 위치 등, 2-3문장)"
      },
      "positionFromHigh": 고점대비현재위치,
      "entryZone": {"low": 매수구간하단, "high": 매수구간상단},
      "stopLoss": 손절가,
      "target1": 1차목표가,
      "target2": 2차목표가,
      "confidence": 신뢰도(0-100),
      "tags": ["태그1", "태그2"],
      "allocation": 포트폴리오배분비율(정수%),
      "sellStrategy": {
        "breakoutHold": "고점 돌파 후 거래대금 유지 시 전략 (한국어)",
        "breakoutFail": "돌파 실패 + 5분봉 음봉 2개 시 전략 (한국어)",
        "volumeDrop": "거래대금 급감 시 전략 (한국어)",
        "sideways": "오전 11시까지 목표가 미도달 + 횡보 시 전략 (한국어)"
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

picks 배열은 rank 1~3 순서로 최대 3개 종목을 포함한다.
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
    ) -> dict:
        user_prompt = self._build_user_prompt(
            enriched_stocks, up_ranking, down_ranking,
            kospi_index, kosdaq_index, exchange_rate, is_market_open,
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
            timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["content"][0]["text"]
        parsed = self._extract_json(content)
        usage = data.get("usage", {})
        logger.info("Claude 분석 완료 — 토큰: input=%s output=%s",
                     usage.get("input_tokens", "?"), usage.get("output_tokens", "?"))
        return parsed

    def _call_openai(self, user_prompt: str) -> dict:
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

    def _build_user_prompt(
        self,
        enriched_stocks: list[dict],
        up_ranking: list[dict],
        down_ranking: list[dict],
        kospi_index: dict,
        kosdaq_index: dict,
        exchange_rate: dict,
        is_market_open: bool,
    ) -> str:
        now = datetime.now(KST)
        time_str = now.strftime("%Y.%m.%d %H:%M")
        lines = []

        lines.append(f"=== 시장 데이터 ({time_str}) ===")
        lines.append("[장중 실시간 데이터]" if is_market_open else "[장 마감 — 전일 마감 데이터]")
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

        five_min = "5분봉 눌림목 패턴, " if is_market_open else ""
        lines.append(
            "위 데이터를 기반으로 단타 매매에 가장 적합한 TOP 3 종목을 선정하고, "
            "각 종목별 포트폴리오 배분 비율(합계 100%)을 제시하세요. "
            "적합한 종목이 없으면 매매비추천으로 판단하세요. "
            f"일봉 추세, 수급 연속성, 고점대비 위치, {five_min}"
            "거래대금 추세를 종합 판단하세요. "
            "확신이 높은 종목에 더 높은 비중을 배분하세요. "
            "반드시 데이터 기반으로 판단하고, JSON 형식으로 응답하세요."
        )

        return "\n".join(lines)
