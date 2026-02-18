import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pytz

import config
from kis_client import KISClient
from naver_data import NaverFinanceService, NaverNewsService

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")


class MarketDataCollector:
    def __init__(self, kis: KISClient, naver_fin: NaverFinanceService, naver_news: NaverNewsService):
        self.kis = kis
        self.naver_fin = naver_fin
        self.naver_news = naver_news

    def is_market_open(self) -> bool:
        now = datetime.now(KST)
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return start <= now <= end

    def fetch_market_data(self) -> dict:
        is_open = self.is_market_open()

        volume_ranking = self._get_volume_ranking()
        up_ranking = self._get_up_ranking()
        down_ranking = self._get_down_ranking()

        kospi_index = self._safe(self.kis.get_kospi_index, {})
        kosdaq_index = self._safe(self.kis.get_kosdaq_index, {})
        exchange_rate = self._safe(self.kis.get_exchange_rate, {})

        stock_news = self._collect_news(volume_ranking)

        return {
            "volume_ranking": volume_ranking,
            "up_ranking": up_ranking,
            "down_ranking": down_ranking,
            "kospi_index": kospi_index,
            "kosdaq_index": kosdaq_index,
            "exchange_rate": exchange_rate,
            "stock_news": stock_news,
            "is_market_open": is_open,
        }

    def enrich_stocks(self, volume_ranking: list[dict], stock_news: dict, is_market_open: bool) -> list[dict]:
        top10 = volume_ranking[:10]
        enriched = []

        def _enrich_one(item: dict) -> dict:
            code = item.get("mksc_shrn_iscd", "")
            result = dict(item)

            try:
                foreign = self.kis.get_foreign_institution(code)
            except Exception:
                foreign = []
            result["foreign_institution"] = foreign

            try:
                candles = self.kis.get_daily_candles(code)
            except Exception:
                candles = []

            recent = []
            high_20d = 0
            for c in candles[:20]:
                h = int(c.get("stck_hgpr", 0) or 0)
                if h > high_20d:
                    high_20d = h
            for c in candles[:5]:
                recent.append({
                    "date": c.get("stck_bsop_date", ""),
                    "open": c.get("stck_oprc", ""),
                    "high": c.get("stck_hgpr", ""),
                    "low": c.get("stck_lwpr", ""),
                    "close": c.get("stck_clpr", ""),
                    "volume": c.get("acml_vol", ""),
                })
            result["recent_daily_candles"] = recent
            result["high_20d"] = high_20d

            current = int(str(item.get("stck_prpr", 0)).replace(",", "") or 0)
            if high_20d > 0 and current > 0:
                result["position_from_high"] = round((current - high_20d) / high_20d * 100, 1)
            else:
                result["position_from_high"] = 0

            if is_market_open:
                try:
                    minute = self.kis.get_minute_candles(code)
                    m5 = []
                    for mc in minute[:12]:
                        m5.append({
                            "time": mc.get("stck_cntg_hour", ""),
                            "open": mc.get("stck_oprc", ""),
                            "high": mc.get("stck_hgpr", ""),
                            "low": mc.get("stck_lwpr", ""),
                            "close": mc.get("stck_prpr", ""),
                            "volume": mc.get("cntg_vol", ""),
                        })
                    result["minute_candles_5m"] = m5
                except Exception:
                    result["minute_candles_5m"] = []
            else:
                result["minute_candles_5m"] = []

            name = item.get("hts_kor_isnm", "")
            result["news_headlines"] = stock_news.get(name, [])

            return result

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_enrich_one, item): i for i, item in enumerate(top10)}
            results = [None] * len(top10)
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("enrichment 실패 [%d]: %s", idx, e)
                    results[idx] = top10[idx]

        return [r for r in results if r is not None]

    def _get_volume_ranking(self) -> list[dict]:
        try:
            ranking = self.kis.get_volume_ranking()
            if ranking:
                return ranking
        except Exception as e:
            logger.warning("KIS 거래량 순위 실패: %s", e)
        logger.info("네이버 거래량 순위 fallback")
        return self.naver_fin.get_volume_ranking(count=20)

    def _get_up_ranking(self) -> list[dict]:
        try:
            ranking = self.kis.get_fluctuation_ranking(is_up=True)
            if ranking:
                return ranking
        except Exception as e:
            logger.warning("KIS 상승 순위 실패: %s", e)
        return self.naver_fin.get_up_ranking()

    def _get_down_ranking(self) -> list[dict]:
        try:
            ranking = self.kis.get_fluctuation_ranking(is_up=False)
            if ranking:
                return ranking
        except Exception as e:
            logger.warning("KIS 하락 순위 실패: %s", e)
        return self.naver_fin.get_down_ranking()

    def _collect_news(self, volume_ranking: list[dict]) -> dict:
        news = {}
        targets = []
        for item in volume_ranking[:10]:
            name = item.get("hts_kor_isnm", "")
            code = item.get("mksc_shrn_iscd", "")
            if name and code:
                targets.append((name, code))

        if not targets:
            for code in config.NAVER_FALLBACK_STOCKS:
                name = config.NAVER_FALLBACK_NAMES.get(code, "")
                if name:
                    targets.append((name, code))

        for name, code in targets:
            try:
                headlines = self.naver_news.get_stock_news(code)
                if headlines:
                    news[name] = headlines
            except Exception:
                pass
        return news

    @staticmethod
    def _safe(fn, default):
        try:
            return fn()
        except Exception as e:
            logger.warning("API 호출 실패: %s", e)
            return default
