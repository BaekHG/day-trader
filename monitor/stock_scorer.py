"""
정량 스코어링 모듈 — enriched stock 데이터로 0-100점 산출

스코어 구성:
  모멘텀 (30점)  — 5분봉 양봉 연속 + 거래량 증가 추세
  거래량 (20점)  — 전일 대비 당일 거래량 배율
  가격위치 (20점) — 20일 고점 대비 현재 위치
  수급 (20점)    — 외국인/기관 연속 순매수 일수
  뉴스 (10점)    — 뉴스 촉매 유무 + 건수 가산
"""

import logging

logger = logging.getLogger(__name__)


def score_stock(stock: dict, is_market_open: bool) -> dict:
    momentum = _score_momentum(stock, is_market_open)
    volume_ratio = _score_volume_ratio(stock)
    price_position = _score_price_position(stock)
    supply_demand = _score_supply_demand(stock)
    news_catalyst = _score_news_catalyst(stock)

    total = max(0, min(100, momentum + volume_ratio + price_position + supply_demand + news_catalyst))

    breakdown = (
        f"총점 {total} = "
        f"모멘텀 {momentum}/30 + 거래량 {volume_ratio}/20 + "
        f"가격위치 {price_position}/20 + 수급 {supply_demand}/20 + "
        f"뉴스 {news_catalyst}/10"
    )

    return {
        "total": total,
        "momentum": momentum,
        "volume_ratio": volume_ratio,
        "price_position": price_position,
        "supply_demand": supply_demand,
        "news_catalyst": news_catalyst,
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
    """0~30점. 장중: 5분봉 양봉연속+거래량증가. 장전: 일봉 양봉+거래량."""
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

        score += min(consec_bull * 6, 22)

        vols = [_to_int(c.get("volume", 0)) for c in candles[:4]]
        if len(vols) >= 4:
            recent_avg = (vols[0] + vols[1]) / 2 if (vols[0] + vols[1]) > 0 else 0
            older_avg = (vols[2] + vols[3]) / 2 if (vols[2] + vols[3]) > 0 else 1
            if older_avg > 0 and recent_avg >= older_avg * 1.5:
                score += 8
            elif older_avg > 0 and recent_avg >= older_avg:
                score += 4
    else:
        daily = stock.get("recent_daily_candles", [])
        if daily:
            latest = daily[0]
            o = _to_int(latest.get("open", 0))
            cl = _to_int(latest.get("close", 0))
            if cl > o:
                score += 12
                for d in daily[1:3]:
                    do = _to_int(d.get("open", 0))
                    dc = _to_int(d.get("close", 0))
                    if dc > do:
                        score += 5
                    else:
                        break

            if len(daily) >= 2:
                v0 = _to_int(daily[0].get("volume", 0))
                v1 = _to_int(daily[1].get("volume", 0))
                if v1 > 0 and v0 >= v1 * 1.5:
                    score += 8
                elif v1 > 0 and v0 >= v1:
                    score += 3

    return min(score, 30)


def _score_volume_ratio(stock: dict) -> int:
    """0~20점. 거래량 배율: 3x→20, 2x→14, 1.5x→10, 1x→5."""
    daily = stock.get("recent_daily_candles", [])
    acml_vol = _to_int(stock.get("acml_vol", 0))

    if acml_vol > 0 and daily:
        prev_vol = _to_int(daily[0].get("volume", 0))
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
    """0~20점. 고점대비: -1%이내→20, -2%→16, -3%→12, -4%→8, -5%→4."""
    pos = stock.get("position_from_high", -999)
    if not isinstance(pos, (int, float)):
        return 0

    if pos >= -1.0:
        return 20
    if pos >= -2.0:
        return 16
    if pos >= -3.0:
        return 12
    if pos >= -4.0:
        return 8
    if pos >= -5.0:
        return 4
    return 0


def _score_supply_demand(stock: dict) -> int:
    """0~20점. 외국인 연속순매수: 2일→6, 3일→10, 4일→14, 5일→16. 기관동반→+4."""
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
        score += 16
    elif frgn_consec >= 4:
        score += 14
    elif frgn_consec >= 3:
        score += 10
    elif frgn_consec >= 2:
        score += 6

    orgn_consec = 0
    for d in foreign[:5]:
        qty = _to_int(d.get("orgn_ntby_qty", 0))
        if qty > 0:
            orgn_consec += 1
        else:
            break

    if orgn_consec >= 2:
        score += 4

    return min(score, 20)


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
