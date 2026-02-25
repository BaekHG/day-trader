"""
정량 스코어링 모듈 — enriched stock 데이터로 0-100점 산출

스코어 구성:
  모멘텀 (25점)  — 5분봉 양봉 연속 + 거래량 증가 추세
  거래량 (20점)  — 전일 대비 당일 거래량 배율
  가격위치 (15점) — 20일 고점 대비 현재 위치
  수급 (15점)    — 외국인/기관 연속 순매수 일수
  뉴스 (10점)    — 뉴스 촉매 유무 + 건수 가산
  돌파 (15점)    — 일봉 연속 양봉 + 거래량 급증 (아이티켐형 발굴)
"""

import logging

logger = logging.getLogger(__name__)


def score_stock(stock: dict, is_market_open: bool) -> dict:
    momentum = _score_momentum(stock, is_market_open)
    volume_ratio = _score_volume_ratio(stock)
    price_position = _score_price_position(stock)
    supply_demand = _score_supply_demand(stock)
    news_catalyst = _score_news_catalyst(stock)
    breakout = _score_breakout(stock)

    total = max(0, min(100, momentum + volume_ratio + price_position + supply_demand + news_catalyst + breakout))

    breakdown = (
        f"총점 {total} = "
        f"모멘텀 {momentum}/25 + 거래량 {volume_ratio}/20 + "
        f"가격위치 {price_position}/15 + 수급 {supply_demand}/15 + "
        f"뉴스 {news_catalyst}/10 + 돌파 {breakout}/15"
    )

    return {
        "total": total,
        "momentum": momentum,
        "volume_ratio": volume_ratio,
        "price_position": price_position,
        "supply_demand": supply_demand,
        "news_catalyst": news_catalyst,
        "breakout": breakout,
        "breakdown": breakdown,
    }


def score_stocks(stocks: list[dict], is_market_open: bool) -> list[dict]:
    for s in stocks:
        result = score_stock(s, is_market_open)
        s["score"] = result["total"]
        s["score_detail"] = result
    stocks.sort(key=lambda x: x.get("score", 0), reverse=True)
    return stocks


def _score_momentum(stock: dict, is_market_open: bool) -> int:
    """0~25점. 장중: 5분봉 양봉연속+거래량증가. 장전: 일봉 양봉+거래량."""
    score = 0

    if is_market_open:
        candles = stock.get("minute_candles_5m", [])
        if not candles:
            return 0

        consec_bull = 0
        for c in candles:
            o = _to_int(c.get("open", 0))
            cl = _to_int(c.get("close", 0))
            if cl > o:
                consec_bull += 1
            else:
                break

        score += min(consec_bull * 5, 18)

        vols = [_to_int(c.get("volume", 0)) for c in candles[:4]]
        if len(vols) >= 4:
            recent_avg = (vols[0] + vols[1]) / 2 if (vols[0] + vols[1]) > 0 else 0
            older_avg = (vols[2] + vols[3]) / 2 if (vols[2] + vols[3]) > 0 else 1
            if older_avg > 0 and recent_avg >= older_avg * 1.5:
                score += 7
            elif older_avg > 0 and recent_avg >= older_avg:
                score += 3
    else:
        daily = stock.get("recent_daily_candles", [])
        if daily:
            latest = daily[0]
            o = _to_int(latest.get("open", 0))
            cl = _to_int(latest.get("close", 0))
            if cl > o:
                score += 10
                for d in daily[1:3]:
                    do = _to_int(d.get("open", 0))
                    dc = _to_int(d.get("close", 0))
                    if dc > do:
                        score += 4
                    else:
                        break

            if len(daily) >= 2:
                v0 = _to_int(daily[0].get("volume", 0))
                v1 = _to_int(daily[1].get("volume", 0))
                if v1 > 0 and v0 >= v1 * 1.5:
                    score += 7
                elif v1 > 0 and v0 >= v1:
                    score += 3

    return min(score, 25)


def _score_volume_ratio(stock: dict) -> int:
    """0~20점. 거래량 배율: 3x→20, 2x→14, 1.5x→10, 1x→5."""
    daily = stock.get("recent_daily_candles", [])
    acml_vol = _to_int(stock.get("acml_vol", 0))

    if acml_vol > 0 and daily:
        prev_idx = 1 if len(daily) >= 2 else 0
        prev_vol = _to_int(daily[prev_idx].get("volume", 0))
        if prev_vol > 0:
            ratio = acml_vol / prev_vol
        else:
            ratio = 0
    elif len(daily) >= 2:
        v0 = _to_int(daily[0].get("volume", 0))
        v1 = _to_int(daily[1].get("volume", 0))
        ratio = v0 / v1 if v1 > 0 else 0
    else:
        return 0

    if ratio >= 3.0:
        return 20
    if ratio >= 2.0:
        return 14
    if ratio >= 1.5:
        return 10
    if ratio >= 1.0:
        return 5
    return 0


def _score_price_position(stock: dict) -> int:
    """0~15점. 고점대비: -1%이내→15, -2%→12, -3%→9, -5%→6, -7%→3."""
    pos = stock.get("position_from_high", -999)
    if not isinstance(pos, (int, float)):
        return 0

    if pos >= -1.0:
        return 15
    if pos >= -2.0:
        return 12
    if pos >= -3.0:
        return 9
    if pos >= -5.0:
        return 6
    if pos >= -7.0:
        return 3
    if pos >= -10.0:
        return 1
    return 0


def _score_supply_demand(stock: dict) -> int:
    """0~15점. 외국인 연속순매수: 2일→4, 3일→7, 4일→10, 5일→12. 기관동반→+3."""
    foreign = stock.get("foreign_institution", [])
    if not foreign:
        return 0

    score = 0
    frgn_consec = 0
    for d in foreign[:5]:
        qty = _to_int(d.get("frgn_ntby_qty", 0))
        if qty > 0:
            frgn_consec += 1
        else:
            break

    if frgn_consec >= 5:
        score += 12
    elif frgn_consec >= 4:
        score += 10
    elif frgn_consec >= 3:
        score += 7
    elif frgn_consec >= 2:
        score += 4

    orgn_consec = 0
    for d in foreign[:5]:
        qty = _to_int(d.get("orgn_ntby_qty", 0))
        if qty > 0:
            orgn_consec += 1
        else:
            break

    if orgn_consec >= 2:
        score += 3

    return min(score, 15)


def _score_breakout(stock: dict) -> int:
    """0~15점. 일봉 연속 양봉 + 거래량 급증 = 돌파 신호 (아이티켐형 발굴).

    - 연속 양봉 2일→3, 3일→6, 4일→9, 5일→11
    - 거래량 급증 (최근 vs 이전): 2배→+2, 3배→+4
    """
    daily = stock.get("recent_daily_candles", [])
    if len(daily) < 2:
        return 0

    # 연속 양봉 카운트
    consec_bull = 0
    for d in daily[:5]:
        o = _to_int(d.get("open", 0))
        c = _to_int(d.get("close", 0))
        if c > o:
            consec_bull += 1
        else:
            break

    if consec_bull < 2:
        return 0

    score = 0
    if consec_bull >= 5:
        score = 11
    elif consec_bull >= 4:
        score = 9
    elif consec_bull >= 3:
        score = 6
    else:
        score = 3

    # 거래량 급증 보너스: 최근 2일 평균 vs 이전 2일 평균
    if len(daily) >= 4:
        recent_vol = (_to_int(daily[0].get("volume", 0)) + _to_int(daily[1].get("volume", 0))) / 2
        older_vol = (_to_int(daily[2].get("volume", 0)) + _to_int(daily[3].get("volume", 0))) / 2
        if older_vol > 0:
            vol_ratio = recent_vol / older_vol
            if vol_ratio >= 3.0:
                score += 4
            elif vol_ratio >= 2.0:
                score += 2

    return min(score, 15)


def _score_news_catalyst(stock: dict) -> int:
    """0~10점. 뉴스 있으면 6, 3건이상 10."""
    headlines = stock.get("news_headlines", [])
    if not headlines:
        return 0
    if len(headlines) >= 3:
        return 10
    return 6


def _to_int(val) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        cleaned = val.replace(",", "").strip()
        if not cleaned:
            return 0
        try:
            return int(cleaned)
        except ValueError:
            try:
                return int(float(cleaned))
            except ValueError:
                return 0
    return 0
