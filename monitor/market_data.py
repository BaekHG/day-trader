from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Semaphore

import pytz

import config
from kis_client import KISClient
from naver_data import NaverFinanceService, NaverNewsService
from stock_scorer import score_stocks

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")


def _min_trading_value(price: int) -> int:
    for price_threshold, value_threshold in config.MIN_TRADING_VALUE_TIERS:
        if price >= price_threshold:
            return value_threshold
    return config.MIN_TRADING_VALUE_TIERS[-1][1]


class MarketDataCollector:
    def __init__(self, kis: KISClient, naver_fin: NaverFinanceService, naver_news: NaverNewsService):
        self.kis = kis
        self.naver_fin = naver_fin
        self.naver_news = naver_news
        self._kis_semaphore = Semaphore(3)

    def is_market_open(self) -> bool:
        now = datetime.now(KST)
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return start <= now <= end

    def fetch_market_data(self, phase: str = "morning") -> dict:
        is_open = self.is_market_open()

        if config.DUAL_SOURCING_ENABLED and is_open:
            volume_ranking = self._get_dual_sourced_candidates(phase)
        else:
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

    def enrich_stocks(self, volume_ranking: list[dict], stock_news: dict, is_market_open: bool, phase: str = "morning") -> list[dict]:
        pool_size = config.ENRICHMENT_POOL_SIZE
        top10 = volume_ranking[:pool_size]

        enriched = self._enrich_batch(top10, stock_news, is_market_open)

        filtered = self._apply_hard_filters(enriched, is_market_open, phase)
        if filtered:
            logger.info("하드 필터 통과: %d/%d 종목", len(filtered), len(enriched))
            scored = score_stocks(filtered, is_market_open)
            for s in scored[:3]:
                detail = s.get("score_detail", {})
                logger.info(
                    "스코어: %s — %s",
                    s.get("hts_kor_isnm", "?"),
                    detail.get("breakdown", f"총점 {s.get('score', 0)}"),
                )
            return scored
        logger.warning("하드 필터 통과 종목 0개 — 이번 사이클 매매 비추천 (빈 리스트 반환)")
        return []

    def enrich_momentum_candidates(self, stock_news: dict) -> list[dict]:
        """모멘텀 후보를 소싱 → enrichment → 품질 검증 → 스코어링."""
        if not config.MOMENTUM_ENABLED:
            return []

        now = datetime.now(KST)
        entry_start_h, entry_start_m = map(int, config.MOMENTUM_ENTRY_START.split(":"))
        entry_end_h, entry_end_m = map(int, config.MOMENTUM_ENTRY_END.split(":"))
        entry_start = now.replace(hour=entry_start_h, minute=entry_start_m, second=0)
        entry_end = now.replace(hour=entry_end_h, minute=entry_end_m, second=0)
        if not (entry_start <= now <= entry_end):
            logger.info("모멘텀 진입 시간대 아님 (%s~%s)", config.MOMENTUM_ENTRY_START, config.MOMENTUM_ENTRY_END)
            return []

        raw = self._get_momentum_candidates()
        if not raw:
            logger.info("모멘텀 소싱 후보 0개")
            return []

        enriched = self._enrich_batch(raw[:config.ENRICHMENT_POOL_SIZE], stock_news, True)

        validated = []
        for s in enriched:
            name = s.get("hts_kor_isnm", "?")
            if self._validate_momentum(s):
                s["is_momentum"] = True
                validated.append(s)
            else:
                logger.info("모멘텀 검증 탈락: %s", name)

        if not validated:
            logger.info("모멘텀 품질 검증 통과 0개")
            return []

        logger.info("모멘텀 검증 통과: %d종목", len(validated))
        scored = self._score_momentum_candidates(validated)
        return scored

    def _enrich_batch(self, items: list[dict], stock_news: dict, is_market_open: bool) -> list[dict]:
        def _enrich_one(item: dict) -> dict:
            code = item.get("mksc_shrn_iscd", "")
            result = dict(item)

            try:
                with self._kis_semaphore:
                    foreign = self.kis.get_foreign_institution(code)
            except Exception:
                foreign = []
            result["foreign_institution"] = foreign

            try:
                with self._kis_semaphore:
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
            result["daily_candles_full"] = candles
            result["high_20d"] = high_20d

            current = int(str(item.get("stck_prpr", 0)).replace(",", "") or 0)
            if high_20d > 0 and current > 0:
                result["position_from_high"] = round((current - high_20d) / high_20d * 100, 1)
            else:
                result["position_from_high"] = 0

            if is_market_open:
                try:
                    with self._kis_semaphore:
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
            futures = {executor.submit(_enrich_one, item): i for i, item in enumerate(items)}
            results: list = [None] * len(items)
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("enrichment 실패 [%d]: %s", idx, e)
                    results[idx] = items[idx]

        return [r for r in results if r is not None]

    def _get_momentum_candidates(self) -> list[dict]:
        try:
            ranking = self.kis.get_fluctuation_ranking_filtered(
                rate_min=config.MOMENTUM_RATE_MIN,
                rate_max=config.MOMENTUM_RATE_MAX,
                price_min=config.MOMENTUM_MIN_PRICE,
                vol_min=config.MOMENTUM_MIN_VOLUME,
            )
            if ranking:
                for item in ranking:
                    if "stck_shrn_iscd" in item and "mksc_shrn_iscd" not in item:
                        item["mksc_shrn_iscd"] = item["stck_shrn_iscd"]
                logger.info("모멘텀 소싱: KIS 등락률 %.1f~%.1f%% (%d종목)",
                            config.MOMENTUM_RATE_MIN, config.MOMENTUM_RATE_MAX, len(ranking))
                return ranking[:20]
        except Exception as e:
            logger.warning("모멘텀 소싱 실패: %s", e)
        return []

    def _validate_momentum(self, stock: dict) -> bool:
        name = stock.get("hts_kor_isnm", "?")
        change_pct = float(str(stock.get("prdy_ctrt", "0")).replace(",", "") or "0")

        daily = stock.get("recent_daily_candles", [])
        if len(daily) >= 2:
            prev_close = int(str(daily[1].get("close", 0)).replace(",", "") or 0)
            prev_open = int(str(daily[1].get("open", 0)).replace(",", "") or 0)
            if prev_close > 0 and prev_open > 0:
                prev_change = (prev_close - prev_open) / prev_open * 100
                if prev_change > config.MOMENTUM_PREV_DAY_MAX_CHANGE:
                    logger.info("모멘텀 제외 [전일 연속급등 %.1f%%]: %s", prev_change, name)
                    return False

        current = int(str(stock.get("stck_prpr", 0)).replace(",", "") or 0)
        today_open = int(str(stock.get("stck_oprc", 0)).replace(",", "") or 0)
        if today_open > 0 and current < today_open:
            logger.info("모멘텀 제외 [시가 하회 — 갭 실패]: %s (현재 %s < 시가 %s)",
                        name, f"{current:,}", f"{today_open:,}")
            return False

        today_high = int(str(stock.get("stck_hgpr", 0)).replace(",", "") or 0)
        if today_high > 0 and current > 0:
            high_ratio = current / today_high
            if high_ratio < config.MOMENTUM_MIN_HIGH_RATIO:
                logger.info("모멘텀 제외 [고점 대비 %.1f%% — 이미 꺾임]: %s",
                            (1 - high_ratio) * 100, name)
                return False

        m_candles = stock.get("minute_candles_5m", [])
        if len(m_candles) >= 2:
            vol_recent = int(str(m_candles[0].get("volume", 0)).replace(",", "") or 0)
            vol_prev = int(str(m_candles[1].get("volume", 0)).replace(",", "") or 0)
            if vol_prev > 0 and vol_recent < vol_prev * config.MOMENTUM_VOL_SUSTAIN_RATIO:
                logger.info("모멘텀 제외 [거래량 급감 %s→%s]: %s",
                            f"{vol_prev:,}", f"{vol_recent:,}", name)
                return False

            low_recent = int(str(m_candles[0].get("low", 0)).replace(",", "") or 0)
            low_prev = int(str(m_candles[1].get("low", 0)).replace(",", "") or 0)
            if low_prev > 0 and low_recent > 0 and low_recent < low_prev * 0.995:
                logger.info("모멘텀 제외 [저점 하락 — lower lows]: %s", name)
                return False

        raw_tv = str(stock.get("acml_tr_pbmn", "0")).replace(",", "")
        trading_value = int(raw_tv) if raw_tv.isdigit() else 0
        if trading_value == 0:
            acml_vol = int(str(stock.get("acml_vol", 0)).replace(",", "") or 0)
            trading_value = acml_vol * current
        min_tv = _min_trading_value(current)
        if 0 < trading_value < min_tv:
            logger.info("모멘텀 제외 [거래대금 %s 미만]: %s (%s)",
                        f"{min_tv / 1e8:.0f}억", name, f"{trading_value:,}")
            return False

        logger.info("모멘텀 검증 통과: %s (%.1f%%, 고점비 %.1f%%)",
                    name, change_pct,
                    (current / today_high * 100) if today_high > 0 else 0)
        return True

    @staticmethod
    def _calc_trend_bonus(daily: list[dict]) -> float:
        if len(daily) < 61:
            return 1.0

        closes = []
        for d in daily:
            c = int(str(d.get("stck_clpr", 0)).replace(",", "") or 0)
            if c > 0:
                closes.append(c)
        closes.reverse()
        if len(closes) < 61:
            return 1.0

        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60

        ema12, ema26 = closes[0], closes[0]
        for p in closes[1:]:
            ema12 = p * (2 / 13) + ema12 * (11 / 13)
            ema26 = p * (2 / 27) + ema26 * (25 / 27)
        macd_now = ema12 - ema26

        ema12_prev, ema26_prev = closes[0], closes[0]
        for p in closes[1:-1]:
            ema12_prev = p * (2 / 13) + ema12_prev * (11 / 13)
            ema26_prev = p * (2 / 27) + ema26_prev * (25 / 27)
        macd_prev = ema12_prev - ema26_prev

        bonus = 1.0
        if ma5 > ma20 > ma60:
            bonus += 0.15
        elif ma5 > ma20:
            bonus += 0.05

        if macd_now > 0 and macd_prev <= 0:
            bonus += 0.15
        elif macd_now > macd_prev:
            bonus += 0.05

        if ma5 < ma20 < ma60:
            bonus -= 0.3

        return round(max(bonus, 0.5), 2)

    def _score_momentum_candidates(self, candidates: list[dict]) -> list[dict]:
        for s in candidates:
            change = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")

            if config.MOMENTUM_OPTIMAL_CHANGE_MIN <= change <= config.MOMENTUM_OPTIMAL_CHANGE_MAX:
                change_score = 1.0
            elif 5.0 <= change < config.MOMENTUM_OPTIMAL_CHANGE_MIN:
                change_score = 0.7
            elif config.MOMENTUM_OPTIMAL_CHANGE_MAX < change <= 22.0:
                change_score = 0.6
            else:
                change_score = 0.3

            acml_vol = int(str(s.get("acml_vol", 0)).replace(",", "") or 0)
            daily = s.get("recent_daily_candles", [])
            avg_vol = 1
            if len(daily) >= 2:
                prev_vol = int(str(daily[1].get("volume", 0)).replace(",", "") or 0)
                avg_vol = max(prev_vol, 1)
            elif daily:
                prev_vol = int(str(daily[0].get("volume", 0)).replace(",", "") or 0)
                avg_vol = max(prev_vol, 1)
            vol_ratio = min(acml_vol / avg_vol, 15)

            current = int(str(s.get("stck_prpr", 0)).replace(",", "") or 0)
            today_high = int(str(s.get("stck_hgpr", 0)).replace(",", "") or 0)
            hold_ratio = current / today_high if today_high > 0 else 0.9

            daily_full = s.get("daily_candles_full", [])
            trend_bonus = self._calc_trend_bonus(daily_full)

            base_score = vol_ratio * change_score * hold_ratio * 10
            momentum_score = round(base_score * trend_bonus, 1)
            s["momentum_score"] = momentum_score
            s["score"] = int(momentum_score)
            s["trend_bonus"] = trend_bonus
            s["score_detail"] = {
                "total": int(momentum_score),
                "breakdown": (
                    f"모멘텀 {momentum_score} = "
                    f"거래량비 {vol_ratio:.1f}x × 등락률 {change_score} × 고점유지 {hold_ratio:.2f} × 10"
                    f" × 추세 {trend_bonus}"
                ),
            }

        candidates.sort(key=lambda x: x.get("momentum_score", 0), reverse=True)
        for s in candidates[:3]:
            logger.info("모멘텀 스코어: %s — %s",
                        s.get("hts_kor_isnm", "?"),
                        s.get("score_detail", {}).get("breakdown", ""))
        return candidates

    def check_momentum_entry(self, code: str) -> bool:
        try:
            with self._kis_semaphore:
                candles = self.kis.get_minute_candles(code)
        except Exception:
            candles = []

        if len(candles) >= 3:
            prev2 = candles[2]
            prev = candles[1]
            curr = candles[0]

            prev_open = int(str(prev.get("stck_oprc", 0)).replace(",", "") or 0)
            prev_close = int(str(prev.get("stck_prpr", 0)).replace(",", "") or 0)
            prev_high = int(str(prev.get("stck_hgpr", 0)).replace(",", "") or 0)
            prev2_high = int(str(prev2.get("stck_hgpr", 0)).replace(",", "") or 0)
            curr_close = int(str(curr.get("stck_prpr", 0)).replace(",", "") or 0)
            curr_high = int(str(curr.get("stck_hgpr", 0)).replace(",", "") or 0)
            curr_vol = int(str(curr.get("cntg_vol", 0)).replace(",", "") or 0)
            prev_vol = int(str(prev.get("cntg_vol", 0)).replace(",", "") or 0)

            if prev2_high > 0 and curr_high < prev_high < prev2_high:
                logger.info("모멘텀 감속 감지: %s (고점 하락 %s→%s→%s) — 진입 거부",
                            code, f"{prev2_high:,}", f"{prev_high:,}", f"{curr_high:,}")
                return False

            is_pullback = prev_close <= prev_open
            breakout = curr_close > prev_high
            vol_confirm = curr_vol > prev_vol

            if is_pullback and breakout and vol_confirm:
                logger.info("모멘텀 풀백 진입 확인: %s (풀백→돌파, 거래량 확인)", code)
                return True

            current = int(str(candles[0].get("stck_prpr", 0)).replace(",", "") or 0)
            today_high = max(
                int(str(c.get("stck_hgpr", 0)).replace(",", "") or 0) for c in candles[:6]
            )
            if today_high > 0 and current > 0:
                near_high = current >= today_high * 0.98
                vol_strong = curr_vol > prev_vol * 0.8
                if near_high and vol_strong:
                    logger.info("모멘텀 고점 근접 진입: %s (고점 98%%↑, 거래량 유지)", code)
                    return True

            return False

        # ── Fallback: 5분봉 없을 때 현재가 기반 진입 판단 ──
        logger.info("모멘텀 5분봉 부족 (%d개) — 현재가 기반 fallback 진입 판단: %s", len(candles), code)
        try:
            with self._kis_semaphore:
                price_data = self.kis.get_current_price(code)
        except Exception:
            return False

        current = price_data.get("price", 0)
        today_high = price_data.get("high", 0)
        today_open = price_data.get("open", 0)
        volume = price_data.get("volume", 0)

        if current <= 0 or today_high <= 0:
            return False

        # 조건 1: 고점 대비 97% 이상 유지 (5분봉 없으므로 기준 약간 강화)
        high_ratio = current / today_high
        if high_ratio < 0.97:
            logger.info("모멘텀 fallback 거부: %s 고점 대비 %.1f%% (97%% 미만)", code, high_ratio * 100)
            return False

        # 조건 2: 시가 대비 양봉 (시가 이상)
        if today_open > 0 and current < today_open:
            logger.info("모멘텀 fallback 거부: %s 시가 하회 (%s < %s)", code, f"{current:,}", f"{today_open:,}")
            return False

        # 조건 3: 최소 거래량 확인
        if volume < config.MOMENTUM_MIN_VOLUME:
            logger.info("모멘텀 fallback 거부: %s 거래량 부족 (%s < %s)",
                        code, f"{volume:,}", f"{config.MOMENTUM_MIN_VOLUME:,}")
            return False

        logger.info("모멘텀 fallback 진입 확인: %s (고점 %.1f%%, 시가↑, 거래량 %s)", code, high_ratio * 100, f"{volume:,}")
        return True

    @staticmethod
    def _apply_hard_filters(stocks: list[dict], is_market_open: bool, phase: str = "morning") -> list[dict]:
        passed = []
        if phase == "afternoon":
            change_min = config.AFTERNOON_HARD_FILTER_CHANGE_MIN
            change_max = config.AFTERNOON_HARD_FILTER_CHANGE_MAX
        else:
            change_min = 0.5
            change_max = 6.0

        for s in stocks:
            name = s.get("hts_kor_isnm", "?")
            change_pct = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")

            if change_pct >= 10.0:
                logger.info("필터 제외 [+10%%↑ 급등]: %s (%.1f%%)", name, change_pct)
                continue

            if is_market_open and not (change_min <= change_pct <= change_max):
                logger.info("필터 제외 [등락률 %.1f~%.1f%% 미충족]: %s (%.1f%%)",
                            change_min, change_max, name, change_pct)
                continue

            raw_tv = str(s.get("acml_tr_pbmn", "0")).replace(",", "")
            trading_value = int(raw_tv) if raw_tv.isdigit() else 0
            price = int(str(s.get("stck_prpr", "0")).replace(",", "") or "0")
            min_tv = _min_trading_value(price)
            if trading_value > 0 and trading_value < min_tv:
                logger.info("필터 제외 [거래대금 %s 미만]: %s (%s)",
                            f"{min_tv / 1e8:.0f}억", name, f"{trading_value:,}")
                continue

            pos_from_high = s.get("position_from_high", -999)
            if isinstance(pos_from_high, (int, float)) and pos_from_high < -10.0:
                logger.info("필터 제외 [고점 대비 -10%% 초과 하락]: %s (%.1f%%)", name, pos_from_high)
                continue

            # 5분봉 거래량 감소 추세 필터 (장중만)
            if is_market_open:
                m_candles = s.get("minute_candles_5m", [])
                if len(m_candles) >= 2:
                    vols = []
                    for mc in m_candles[:4]:
                        v = int(str(mc.get("volume", "0")).replace(",", "") or "0")
                        vols.append(v)
                    if len(vols) >= 2 and vols[0] > 0:
                        # 최근 봉 거래량이 첫 봉의 30% 미만이면 모멘텀 소멸
                        if vols[0] < vols[-1] * 0.3:
                            logger.info("필터 제외 [5분봉 거래량 급감]: %s (최근 %s → %s)", name, f"{vols[0]:,}", f"{vols[-1]:,}")
                            continue

            passed.append(s)
        return passed

    def _get_dual_sourced_candidates(self, phase: str = "morning") -> list[dict]:
        if phase == "afternoon":
            rate_min = config.AFTERNOON_HARD_FILTER_CHANGE_MIN
            rate_max = config.AFTERNOON_HARD_FILTER_CHANGE_MAX
        else:
            rate_min = 0.5
            rate_max = 6.0

        source_a = self._get_volume_ranking_with_cap_filter()
        source_b = self._get_change_rate_ranking(rate_min, rate_max)
        source_c = self._get_breakout_candidates()

        seen_codes = set()
        merged = []
        for item in source_a + source_b + source_c:
            if "stck_shrn_iscd" in item and "mksc_shrn_iscd" not in item:
                item["mksc_shrn_iscd"] = item["stck_shrn_iscd"]
            code = item.get("mksc_shrn_iscd", "")
            if code and code not in seen_codes:
                seen_codes.add(code)
                merged.append(item)

        merged.sort(
            key=lambda x: int(str(x.get("acml_tr_pbmn", "0")).replace(",", "") or "0"),
            reverse=True,
        )

        logger.info(
            "3중 소싱 결과: 거래량 %d + 등락률 %d + 돌파 %d → 합산 %d종목 (중복제거)",
            len(source_a), len(source_b), len(source_c), len(merged),
        )
        return merged

    def _get_breakout_candidates(self) -> list[dict]:
        """상승 상위 종목에서 돌파 후보 추출 — 아이티켐 같은 초기 상승 종목 포착."""
        try:
            ranking = self.kis.get_fluctuation_ranking(is_up=True)
            if not ranking:
                return []
            filtered = []
            for item in ranking[:30]:
                price = int(str(item.get("stck_prpr", "0")).replace(",", "") or "0")
                vol = int(str(item.get("acml_vol", "0")).replace(",", "") or "0")
                change = float(str(item.get("prdy_ctrt", "0")).replace(",", "") or "0")
                # 기본 필터: 1000원 이상, 거래량 5만 이상, +10% 미만 (상한가 제외)
                if price >= config.DUAL_SOURCING_MIN_PRICE and vol >= 50000 and change < 10.0:
                    filtered.append(item)
            logger.info("돌파 후보 소스: KIS 상승순위 (%d종목)", len(filtered))
            return filtered[:20]
        except Exception as e:
            logger.warning("KIS 상승순위 조회 실패: %s", e)
        return []

    def _get_volume_ranking_with_cap_filter(self) -> list[dict]:
        raw = self._get_volume_ranking()
        if not config.DUAL_SOURCING_MIN_MARKET_CAP:
            return raw

        filtered = []
        for item in raw:
            cap_str = str(item.get("stck_avls_hamt", "0")).replace(",", "")
            market_cap = int(cap_str) if cap_str.isdigit() else 0

            if market_cap == 0:
                tr_pbmn = str(item.get("acml_tr_pbmn", "0")).replace(",", "")
                trading_value = int(tr_pbmn) if tr_pbmn.isdigit() else 0
                price = int(str(item.get("stck_prpr", "0")).replace(",", "") or "0")
                if trading_value >= _min_trading_value(price):
                    filtered.append(item)
                    continue
                logger.info(
                    "시총 필터 제외 (시총 없음, 거래대금 부족): %s",
                    item.get("hts_kor_isnm", "?"),
                )
                continue

            if market_cap >= config.DUAL_SOURCING_MIN_MARKET_CAP:
                filtered.append(item)
            else:
                logger.info(
                    "시총 필터 제외: %s (시총 %s < %s)",
                    item.get("hts_kor_isnm", "?"),
                    f"{market_cap:,}",
                    f"{config.DUAL_SOURCING_MIN_MARKET_CAP:,}",
                )
        return filtered

    def _get_change_rate_ranking(self, rate_min: float, rate_max: float) -> list[dict]:
        try:
            ranking = self.kis.get_fluctuation_ranking_filtered(
                rate_min=rate_min,
                rate_max=rate_max,
                price_min=config.DUAL_SOURCING_MIN_PRICE,
                vol_min=config.DUAL_SOURCING_MIN_VOLUME,
            )
            if ranking:
                logger.info("등락률 범위 순위 소스: KIS (%d종목, %.1f~%.1f%%)", len(ranking), rate_min, rate_max)
                return ranking[:20]
        except Exception as e:
            logger.warning("KIS 등락률 범위 순위 실패: %s", e)
        return []

    def _get_volume_ranking(self) -> list[dict]:
        try:
            ranking = self.kis.get_volume_ranking()
            if ranking:
                logger.info("거래량 순위 소스: KIS (%d종목)", len(ranking))
                return ranking
        except Exception as e:
            logger.warning("KIS 거래량 순위 실패: %s", e)

        logger.info("네이버 거래량 순위 fallback")
        ranking = self.naver_fin.get_volume_ranking(count=20)
        if ranking:
            logger.info("거래량 순위 소스: 네이버 거래량 (%d종목)", len(ranking))
            return ranking

        logger.info("네이버 시가총액 순위 fallback (장전)")
        result = self.naver_fin.get_market_cap_ranking(count=20)
        logger.info("거래량 순위 소스: 네이버 시총 (%d종목)", len(result))
        return result

    def _get_up_ranking(self) -> list[dict]:
        try:
            ranking = self.kis.get_fluctuation_ranking(is_up=True)
            if ranking:
                return ranking
        except Exception as e:
            logger.warning("KIS 상승 순위 실패: %s", e)
        ranking = self.naver_fin.get_up_ranking()
        return ranking if ranking else []

    def _get_down_ranking(self) -> list[dict]:
        try:
            ranking = self.kis.get_fluctuation_ranking(is_up=False)
            if ranking:
                return ranking
        except Exception as e:
            logger.warning("KIS 하락 순위 실패: %s", e)
        ranking = self.naver_fin.get_down_ranking()
        return ranking if ranking else []

    def _collect_news(self, volume_ranking: list[dict]) -> dict:
        news = {}
        targets = []
        for item in volume_ranking[:config.ENRICHMENT_POOL_SIZE]:
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
