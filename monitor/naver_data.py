import logging
import re

import requests

logger = logging.getLogger(__name__)

_BASE = "https://m.stock.naver.com/api/stocks"


def _remove_comma(val):
    if val is None:
        return "0"
    return str(val).replace(",", "")


def _parse_volume(val):
    if val is None:
        return 0
    return int(str(val).replace(",", "") or "0")


def _to_kis_format(naver: dict) -> dict:
    price = _remove_comma(naver.get("closePrice"))
    return {
        "hts_kor_isnm": naver.get("stockName", ""),
        "mksc_shrn_iscd": naver.get("itemCode", ""),
        "stck_prpr": price,
        "prdy_ctrt": str(naver.get("fluctuationsRatio", "0")),
        "acml_vol": _remove_comma(naver.get("accumulatedTradingVolume")),
        "acml_tr_pbmn": _remove_comma(naver.get("accumulatedTradingValue")),
        "stck_hgpr": price,
        "stck_sdpr": price,
    }


class NaverFinanceService:

    def get_market_cap_ranking(self, count: int = 20) -> list[dict]:
        all_stocks = []
        try:
            for market in ("KOSPI", "KOSDAQ"):
                resp = requests.get(
                    f"{_BASE}/marketValue/{market}",
                    params={"page": 1, "pageSize": 30},
                    timeout=8,
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    all_stocks.extend(data.get("stocks", []))
        except Exception as e:
            logger.error("네이버 시가총액 순위 조회 실패: %s", e)
            return []

        seen = set()
        unique = []
        for s in all_stocks:
            code = s.get("itemCode", "")
            if code and code not in seen:
                seen.add(code)
                unique.append(s)

        return [_to_kis_format(s) for s in unique[:count]]

    def get_volume_ranking(self, count: int = 10) -> list[dict]:
        all_stocks = []
        try:
            for market in ("KOSPI", "KOSDAQ"):
                for direction in ("up", "down"):
                    resp = requests.get(
                        f"{_BASE}/{direction}/{market}",
                        params={"page": 1, "pageSize": 30},
                        timeout=8,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, dict):
                        stocks = data.get("stocks", [])
                        all_stocks.extend(stocks)
        except Exception as e:
            logger.error("네이버 거래량 순위 조회 실패: %s", e)
            return []

        seen = set()
        unique = []
        for s in all_stocks:
            code = s.get("itemCode", "")
            if code and code not in seen:
                seen.add(code)
                unique.append(s)

        unique.sort(key=lambda x: _parse_volume(x.get("accumulatedTradingVolume")), reverse=True)
        return [_to_kis_format(s) for s in unique[:count]]

    def get_up_ranking(self, count: int = 15) -> list[dict]:
        return self._get_ranking("up", count)

    def get_down_ranking(self, count: int = 15) -> list[dict]:
        return self._get_ranking("down", count)

    def _get_ranking(self, direction: str, count: int) -> list[dict]:
        all_stocks = []
        try:
            for market in ("KOSPI", "KOSDAQ"):
                resp = requests.get(
                    f"{_BASE}/{direction}/{market}",
                    params={"page": 1, "pageSize": count},
                    timeout=8,
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    all_stocks.extend(data.get("stocks", []))
        except Exception as e:
            logger.error("네이버 등락 순위 조회 실패: %s", e)
            return []

        all_stocks.sort(
            key=lambda x: abs(float(x.get("fluctuationsRatio", 0) or 0)),
            reverse=True,
        )
        return [_to_kis_format(s) for s in all_stocks[:count]]


class NaverNewsService:

    def get_stock_news(self, stock_code: str) -> list[dict]:
        try:
            resp = requests.get(
                f"https://m.stock.naver.com/api/news/stock/{stock_code}",
                params={"pageSize": 5},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict):
                items = data.get("items", [])
                if items:
                    return self._parse_items(items)

            if isinstance(data, list):
                articles = []
                for group in data:
                    if isinstance(group, dict):
                        articles.extend(self._parse_items(group.get("items", [])))
                return articles[:10]

            return []
        except Exception:
            return self._get_news_alt(stock_code)

    @staticmethod
    def _parse_items(items: list) -> list[dict]:
        articles = []
        for it in items:
            if not isinstance(it, dict):
                continue
            title = re.sub(r"<[^>]*>", "", it.get("title", "") or it.get("titleFull", ""))
            if not title:
                continue
            office_id = it.get("officeId", "")
            article_id = it.get("articleId", "")
            url = f"https://n.news.naver.com/article/{office_id}/{article_id}" if office_id and article_id else ""
            articles.append({"title": title, "url": url, "source": it.get("officeName", "")})
        return articles

    def _get_news_alt(self, stock_code: str) -> list[dict]:
        try:
            resp = requests.get(
                "https://m.stock.naver.com/api/json/news/stockNews.nhn",
                params={"code": stock_code},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                result = data.get("result", {})
                news_list = result.get("newsList", [])
                return [
                    {"title": n.get("articleTitle", ""), "url": "", "source": ""}
                    for n in news_list[:5]
                    if isinstance(n, dict) and n.get("articleTitle")
                ]
            return []
        except Exception:
            return []
