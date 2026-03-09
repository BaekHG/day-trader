from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from threading import Semaphore

import pytz

import config
from kis_client import KISClient
from naver_data import NaverFinanceService, NaverNewsService
from stock_scorer import score_stocks

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")


def _is_early_morning() -> bool:
    """장 초반 모드 활성 여부 (09:00 ~ 09:00+EARLY_MORNING_MINUTES)."""
    now = datetime.now(KST)
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    return now <= market_open + timedelta(minutes=config.EARLY_MORNING_MINUTES)


def _min_trading_value(price: int) -> int:
    for price_threshold, value_threshold in config.MIN_TRADING_VALUE_TIERS:
        if price >= price_threshold:
            return value_threshold
    return config.MIN_TRADING_VALUE_TIERS[-1][1]


class MarketDataCollector:
    def __init__(
        self,
        kis: KISClient,
        naver_fin: NaverFinanceService,
        naver_news: NaverNewsService,
    ):
        self.kis = kis
        self.naver_fin = naver_fin
        self.naver_news = naver_news
        self._kis_semaphore = Semaphore(3)
        self.last_scan_summary = ""

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

    def enrich_stocks(
        self,
        volume_ranking: list[dict],
        stock_news: dict,
        is_market_open: bool,
        phase: str = "morning",
    ) -> list[dict]:
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
        logger.warning(
            "하드 필터 통과 종목 0개 — 이번 사이클 매매 비추천 (빈 리스트 반환)"
        )
        return []

    def enrich_momentum_candidates(self, stock_news: dict) -> list[dict]:
        """모멘텀 후보를 소싱 → enrichment → 품질 검증 → 스코어링.
        결과와 별도로 self.last_scan_summary 에 스캔 요약 저장."""
        self.last_scan_summary = ""
        if not config.MOMENTUM_ENABLED:
            self.last_scan_summary = "모멘텀 비활성"
            return []

        now = datetime.now(KST)
        entry_start_h, entry_start_m = map(int, config.MOMENTUM_ENTRY_START.split(":"))
        entry_end_h, entry_end_m = map(int, config.MOMENTUM_ENTRY_END.split(":"))
        entry_start = now.replace(hour=entry_start_h, minute=entry_start_m, second=0)
        entry_end = now.replace(hour=entry_end_h, minute=entry_end_m, second=0)
        if not (entry_start <= now <= entry_end):
            logger.info(
                "모멘텀 진입 시간대 아님 (%s~%s)",
                config.MOMENTUM_ENTRY_START,
                config.MOMENTUM_ENTRY_END,
            )
            self.last_scan_summary = f"진입 시간대 아님 ({config.MOMENTUM_ENTRY_START}~{config.MOMENTUM_ENTRY_END})"
            return []

        raw = self._get_momentum_candidates()
        if not raw:
            logger.info("모멘텀 소싱 후보 0개")
            self.last_scan_summary = "등락률 조건 충족 종목 0개 (소싱 결과 없음)"
            return []

        enriched = self._enrich_batch(
            raw[: config.ENRICHMENT_POOL_SIZE], stock_news, True
        )

        validated = []
        rejected = []
        for s in enriched:
            name = s.get("hts_kor_isnm", "?")
            change = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")
            ok, reason = self._validate_momentum(s)
            if ok:
                s["is_momentum"] = True
                validated.append(s)
            else:
                rejected.append(f"  · {name} ({change:+.1f}%) — {reason}")
                logger.info("모멘텀 검증 탈락: %s — %s", name, reason)
        if not validated:
            logger.info("모멘텀 품질 검증 통과 0개")
            lines = [f"소싱 {len(enriched)}종목 → 검증 통과 0개"]
            lines.extend(rejected[:5])
            self.last_scan_summary = "\n".join(lines)
            return []

        logger.info("모멘텀 검증 통과: %d종목", len(validated))
        scored = self._score_momentum_candidates(validated)

        # 스캔 요약 생성
        summary_parts = [f"소싱 {len(enriched)}종목 → 검증 {len(validated)}개 통과"]
        for s in scored[:3]:
            sname = s.get("hts_kor_isnm", "?")
            spct = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")
            sscore = s.get("momentum_score", 0)
            summary_parts.append(f"  {sname} ({spct:+.1f}%, 스코어 {sscore:.1f})")
        if rejected:
            summary_parts.append(f"탈락 {len(rejected)}종목:")
            summary_parts.extend(rejected[:3])
        self.last_scan_summary = "\n".join(summary_parts)
        return scored

    def _enrich_batch(
        self, items: list[dict], stock_news: dict, is_market_open: bool
    ) -> list[dict]:
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
                recent.append(
                    {
                        "date": c.get("stck_bsop_date", ""),
                        "open": c.get("stck_oprc", ""),
                        "high": c.get("stck_hgpr", ""),
                        "low": c.get("stck_lwpr", ""),
                        "close": c.get("stck_clpr", ""),
                        "volume": c.get("acml_vol", ""),
                    }
                )
            result["recent_daily_candles"] = recent
            result["daily_candles_full"] = candles
            result["high_20d"] = high_20d

            current = int(str(item.get("stck_prpr", 0)).replace(",", "") or 0)
            if high_20d > 0 and current > 0:
                result["position_from_high"] = round(
                    (current - high_20d) / high_20d * 100, 1
                )
            else:
                result["position_from_high"] = 0

            if is_market_open:
                try:
                    with self._kis_semaphore:
                        minute = self.kis.get_minute_candles(code)
                    m5 = []
                    for mc in minute[:12]:
                        m5.append(
                            {
                                "time": mc.get("stck_cntg_hour", ""),
                                "open": mc.get("stck_oprc", ""),
                                "high": mc.get("stck_hgpr", ""),
                                "low": mc.get("stck_lwpr", ""),
                                "close": mc.get("stck_prpr", ""),
                                "volume": mc.get("cntg_vol", ""),
                            }
                        )
                    result["minute_candles_5m"] = m5
                except Exception:
                    result["minute_candles_5m"] = []
            else:
                result["minute_candles_5m"] = []

            name = item.get("hts_kor_isnm", "")
            result["news_headlines"] = stock_news.get(name, [])

            return result

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_enrich_one, item): i for i, item in enumerate(items)
            }
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
                rate_min=config.EARLY_MOMENTUM_RATE_MIN
                if _is_early_morning()
                else config.MOMENTUM_RATE_MIN,
                rate_max=config.MOMENTUM_RATE_MAX,
                price_min=config.MOMENTUM_MIN_PRICE,
                vol_min=config.MOMENTUM_MIN_VOLUME,
            )
            if ranking:
                for item in ranking:
                    if "stck_shrn_iscd" in item and "mksc_shrn_iscd" not in item:
                        item["mksc_shrn_iscd"] = item["stck_shrn_iscd"]
                logger.info(
                    "모멘텀 소싱: KIS 등락률 %.1f~%.1f%% (%d종목)",
                    config.MOMENTUM_RATE_MIN,
                    config.MOMENTUM_RATE_MAX,
                    len(ranking),
                )
                return ranking[:20]
        except Exception as e:
            logger.warning("모멘텀 소싱 실패: %s", e)
        return []

    def _validate_momentum(self, stock: dict) -> tuple[bool, str]:
        name = stock.get("hts_kor_isnm", "?")
        change_pct = float(str(stock.get("prdy_ctrt", "0")).replace(",", "") or "0")

        import main as _main_mod  # noqa: F811 — lazy import (circular)

        bs = getattr(_main_mod, "_boost_state", {})
        boosted = bs.get("active", False)
        change_max = (
            config.BOOST_HARD_FILTER_CHANGE_MAX
            if boosted
            else config.HARD_FILTER_MAX_CHANGE
        )
        if change_pct >= change_max:
            logger.info(
                "모멘텀 제외 [급등 하드필터 %.1f%% ≥ %.1f%%]: %s",
                change_pct,
                change_max,
                name,
            )
            return False, f"급등 하드필터 ({change_pct:.1f}% ≥ {change_max:.1f}%)"

        daily = stock.get("recent_daily_candles", [])
        if len(daily) >= 2:
            prev_close = int(str(daily[1].get("close", 0)).replace(",", "") or 0)
            prev_open = int(str(daily[1].get("open", 0)).replace(",", "") or 0)
            if prev_close > 0 and prev_open > 0:
                prev_change = (prev_close - prev_open) / prev_open * 100
                if prev_change > config.MOMENTUM_PREV_DAY_MAX_CHANGE:
                    logger.info(
                        "모멘텀 제외 [전일 연속급등 %.1f%%]: %s", prev_change, name
                    )
                    return False, f"전일 연속급등 {prev_change:.1f}%"

        current = int(str(stock.get("stck_prpr", 0)).replace(",", "") or 0)
        today_open = int(str(stock.get("stck_oprc", 0)).replace(",", "") or 0)
        if today_open > 0 and current < today_open:
            logger.info(
                "모멘텀 제외 [시가 하회 — 갭 실패]: %s (현재 %s < 시가 %s)",
                name,
                f"{current:,}",
                f"{today_open:,}",
            )
            return False, f"시가 하회 ({current:,} < 시가 {today_open:,})"

        today_high = int(str(stock.get("stck_hgpr", 0)).replace(",", "") or 0)
        if today_high > 0 and current > 0:
            high_ratio = current / today_high
            if high_ratio < config.MOMENTUM_MIN_HIGH_RATIO:
                logger.info(
                    "모멘텀 제외 [고점 대비 %.1f%% — 이미 꺾임]: %s",
                    (1 - high_ratio) * 100,
                    name,
                )
                return False, f"고점 대비 {(1 - high_ratio) * 100:.1f}% 하락"

        m_candles = stock.get("minute_candles_5m", [])
        if len(m_candles) >= 2:
            vol_recent = int(str(m_candles[0].get("volume", 0)).replace(",", "") or 0)
            vol_prev = int(str(m_candles[1].get("volume", 0)).replace(",", "") or 0)
            if (
                vol_prev > 0
                and vol_recent < vol_prev * config.MOMENTUM_VOL_SUSTAIN_RATIO
            ):
                logger.info(
                    "모멘텀 제외 [거래량 급감 %s→%s]: %s",
                    f"{vol_prev:,}",
                    f"{vol_recent:,}",
                    name,
                )
                return False, f"거래량 급감 ({vol_prev:,}→{vol_recent:,})"

            low_recent = int(str(m_candles[0].get("low", 0)).replace(",", "") or 0)
            low_prev = int(str(m_candles[1].get("low", 0)).replace(",", "") or 0)
            if low_prev > 0 and low_recent > 0 and low_recent < low_prev * 0.995:
                logger.info("모멘텀 제외 [저점 하락 — lower lows]: %s", name)
                return False, "저점 하락 (lower lows)"

        raw_tv = str(stock.get("acml_tr_pbmn", "0")).replace(",", "")
        trading_value = int(raw_tv) if raw_tv.isdigit() else 0
        if trading_value == 0:
            acml_vol = int(str(stock.get("acml_vol", 0)).replace(",", "") or 0)
            trading_value = acml_vol * current
        min_tv = _min_trading_value(current)
        if 0 < trading_value < min_tv:
            logger.info(
                "모멘텀 제외 [거래대금 %s 미만]: %s (%s)",
                f"{min_tv / 1e8:.0f}억",
                name,
                f"{trading_value:,}",
            )
            return False, f"거래대금 {min_tv / 1e8:.0f}억 미만"

        logger.info(
            "모멘텀 검증 통과: %s (%.1f%%, 고점비 %.1f%%)",
            name,
            change_pct,
            (current / today_high * 100) if today_high > 0 else 0,
        )
        return True, ""

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
        now = datetime.now(KST)
        market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
        minutes_elapsed = max((now - market_open).total_seconds() / 60, 1)

        # 시간대별 예상 거래량 비율 (U-curve: 초반25% / 중반50% / 마감25%)
        if minutes_elapsed <= 30:
            expected_pct = 0.25 * (minutes_elapsed / 30)
        elif minutes_elapsed <= 360:
            expected_pct = 0.25 + 0.50 * ((minutes_elapsed - 30) / 330)
        else:
            expected_pct = 0.75 + 0.25 * (min(minutes_elapsed - 360, 30) / 30)

        for s in candidates:
            change = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")

            # === 등락률 점수 (부드러운 곡선) ===
            early = _is_early_morning()
            if change < 3.0:
                change_score = 0.0
            elif early and change < 5.0:
                # 장 초반: 3~5% 부분점수 (0.3~0.7)
                change_score = 0.3 + 0.4 * (change - 3.0) / 2.0
            elif change < 5.0:
                change_score = 0.0
            elif change < config.MOMENTUM_OPTIMAL_CHANGE_MIN:
                change_score = 0.5 + 0.5 * (change - 5.0) / (
                    config.MOMENTUM_OPTIMAL_CHANGE_MIN - 5.0
                )
            elif change <= config.MOMENTUM_OPTIMAL_CHANGE_MAX:
                change_score = 1.0
            elif change <= 22.0:
                change_score = 1.0 - 0.5 * (
                    change - config.MOMENTUM_OPTIMAL_CHANGE_MAX
                ) / (22.0 - config.MOMENTUM_OPTIMAL_CHANGE_MAX)
            elif change <= 29.5:
                change_score = 0.5 - 0.2 * (change - 22.0) / 7.5
            else:
                change_score = 0.0  # 상한가 고정

            # === 시간보정 거래량 점수 (ln 스케일) ===
            acml_vol = int(str(s.get("acml_vol", 0)).replace(",", "") or 0)
            daily = s.get("recent_daily_candles", [])
            prev_vol = 1
            if len(daily) >= 2:
                prev_vol = max(
                    int(str(daily[1].get("volume", 0)).replace(",", "") or 0), 1
                )
            elif daily:
                prev_vol = max(
                    int(str(daily[0].get("volume", 0)).replace(",", "") or 0), 1
                )

            expected_vol = prev_vol * max(expected_pct, 0.01)
            raw_vol_ratio = acml_vol / max(expected_vol, 1)
            vol_score = min(math.log(max(raw_vol_ratio, 1)) + 1, 5)  # ln, 1.0~5.0

            # === 거래량 하드 게이트 ===
            vol_gate = (
                config.EARLY_MOMENTUM_VOL_GATE
                if _is_early_morning()
                else config.MOMENTUM_VOL_GATE
            )
            if vol_score < vol_gate:
                s["momentum_score"] = 0
                s["score"] = 0
                s["trend_bonus"] = 0
                s["score_detail"] = {
                    "total": 0,
                    "breakdown": f"거래량 부족 (vol_score {vol_score:.2f} < {vol_gate})",
                }
                continue

            # === 고점유지 비율 ===
            current = int(str(s.get("stck_prpr", 0)).replace(",", "") or 0)
            today_high = int(str(s.get("stck_hgpr", 0)).replace(",", "") or 0)
            hold_ratio = current / today_high if today_high > 0 else 0.9

            # === 추세 보너스 ===
            daily_full = s.get("daily_candles_full", [])
            trend_bonus = self._calc_trend_bonus(daily_full)

            # === 최종 스코어 ===
            base_score = vol_score * change_score * hold_ratio * 20
            momentum_score = round(base_score * trend_bonus, 1)

            # === 불장 모드: 테마 보너스/패널티 ===
            theme_multiplier = 1.0
            theme_label = ""
            try:
                import main as _main_mod

                bs = getattr(_main_mod, "_boost_state", {})
                if bs.get("active"):
                    name = s.get("hts_kor_isnm", "")
                    news = s.get("news_headlines", [])
                    text_blob = (
                        name
                        + " "
                        + " ".join(
                            n.get("title", "") if isinstance(n, dict) else str(n)
                            for n in news[:5]
                        )
                    )
                    for theme in bs.get("boost_themes", []):
                        if theme and theme in text_blob:
                            theme_multiplier = config.BOOST_THEME_SCORE_BONUS
                            theme_label = f"수혜({theme})×{theme_multiplier}"
                            break
                    if theme_multiplier == 1.0:
                        for theme in bs.get("hurt_themes", []):
                            if theme and theme in text_blob:
                                theme_multiplier = config.BOOST_THEME_SCORE_PENALTY
                                theme_label = f"피해({theme})×{theme_multiplier}"
                                break
            except Exception:
                pass
            momentum_score = round(momentum_score * theme_multiplier, 1)

            s["momentum_score"] = momentum_score
            s["score"] = int(momentum_score)
            s["trend_bonus"] = trend_bonus
            s["_vol_ratio"] = round(raw_vol_ratio, 1)
            s["_high_ratio"] = round(hold_ratio, 4)
            s["_theme_label"] = theme_label
            s["score_detail"] = {
                "total": int(momentum_score),
                "breakdown": (
                    f"모멘텀 {momentum_score} = "
                    f"거래량 {vol_score:.2f} (보정{raw_vol_ratio:.1f}x) × 등락률 {change_score:.2f} "
                    f"× 고점유지 {hold_ratio:.2f} × 20 × 추세 {trend_bonus}"
                    + (f" × {theme_label}" if theme_label else "")
                ),
            }

        candidates.sort(key=lambda x: x.get("momentum_score", 0), reverse=True)
        for s in candidates[:3]:
            logger.info(
                "모멘텀 스코어: %s — %s",
                s.get("hts_kor_isnm", "?"),
                s.get("score_detail", {}).get("breakdown", ""),
            )
        return candidates

    def check_momentum_entry(self, code: str) -> tuple[bool, str]:
        try:
            with self._kis_semaphore:
                candles = self.kis.get_minute_candles(code)
        except Exception:
            candles = []

        # ── 공통 게이트: 장중 전체 고점 대비 체크 (캔들/fallback 무관) ──
        try:
            with self._kis_semaphore:
                price_info = self.kis.get_current_price(code)
        except Exception:
            price_info = {}
        intraday_high = price_info.get("high", 0)
        intraday_cur = price_info.get("price", 0)
        if intraday_high > 0 and intraday_cur > 0:
            intraday_ratio = intraday_cur / intraday_high
            if intraday_ratio < config.MOMENTUM_MIN_HIGH_RATIO:
                logger.info(
                    "모멘텀 진입 거부 [장중 고점 대비 %.1f%% < %.0f%%]: %s",
                    intraday_ratio * 100,
                    config.MOMENTUM_MIN_HIGH_RATIO * 100,
                    code,
                )
                return (
                    False,
                    f"장중 고점 대비 {intraday_ratio * 100:.1f}% ({config.MOMENTUM_MIN_HIGH_RATIO * 100:.0f}% 미만)",
                )

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

            drop_pct = (prev2_high - curr_high) / prev2_high if prev2_high > 0 else 0
            if (
                prev2_high > 0
                and curr_high < prev_high < prev2_high
                and drop_pct >= 0.003
            ):
                logger.info(
                    "모멘텀 감속 감지: %s (고점 하락 %s→%s→%s, -%.2f%%) — 진입 거부",
                    code,
                    f"{prev2_high:,}",
                    f"{prev_high:,}",
                    f"{curr_high:,}",
                    drop_pct * 100,
                )
                return (
                    False,
                    f"감속 감지 (고점 {prev2_high:,}→{prev_high:,}→{curr_high:,}, -{drop_pct * 100:.1f}%)",
                )

            is_pullback = prev_close <= prev_open
            breakout = curr_close > prev_high
            vol_confirm = curr_vol > prev_vol

            if is_pullback and breakout and vol_confirm:
                logger.info("모멘텀 풀백 진입 확인: %s (풀백→돌파, 거래량 확인)", code)
                return True, "풀백→돌파 + 거래량 확인"

            current = int(str(candles[0].get("stck_prpr", 0)).replace(",", "") or 0)
            today_high = max(
                int(str(c.get("stck_hgpr", 0)).replace(",", "") or 0)
                for c in candles[:6]
            )
            if today_high > 0 and current > 0:
                near_high = current >= today_high * (
                    config.MOMENTUM_MIN_HIGH_RATIO + 0.02
                )
                vol_strong = curr_vol > prev_vol * 0.8
                if near_high and vol_strong:
                    logger.info(
                        "모멘텀 고점 근접 진입: %s (고점 %.1f%%↑, 거래량 유지)",
                        code,
                        current / today_high * 100,
                    )
                    return (
                        True,
                        f"고점 {current / today_high * 100:.1f}%↑ + 거래량 유지",
                    )

            return False, "캔들 패턴 미충족 (풀백돌파✗, 고점근접✗)"

        # ── Fallback: 5분봉 없을 때 현재가 기반 진입 판단 ──
        logger.info(
            "모멘텀 5분봉 부족 (%d개) — 현재가 기반 fallback 진입 판단: %s",
            len(candles),
            code,
        )
        try:
            with self._kis_semaphore:
                price_data = self.kis.get_current_price(code)
        except Exception:
            return False, "현재가 조회 실패"

        current = price_data.get("price", 0)
        today_high = price_data.get("high", 0)
        today_open = price_data.get("open", 0)
        volume = price_data.get("volume", 0)

        if current <= 0 or today_high <= 0:
            return False, "가격 데이터 없음"

        # 조건 1: 고점 대비 config 기준 이상 유지 (fallback이므로 config값 그대로)
        high_ratio = current / today_high
        if high_ratio < config.MOMENTUM_MIN_HIGH_RATIO:
            logger.info(
                "모멘텀 fallback 거부: %s 고점 대비 %.1f%% (%.0f%% 미만)",
                code,
                high_ratio * 100,
                config.MOMENTUM_MIN_HIGH_RATIO * 100,
            )
            return (
                False,
                f"고점 대비 {high_ratio * 100:.1f}% ({config.MOMENTUM_MIN_HIGH_RATIO * 100:.0f}% 미만)",
            )

        # 조건 2: 시가 대비 양봉 (시가 이상)
        early = _is_early_morning()
        tolerance = config.EARLY_FALLBACK_OPEN_TOLERANCE if early else 0.0
        if today_open > 0 and current < today_open * (1 - tolerance):
            if early:
                logger.info(
                    "모멘텀 fallback 거부: %s 시가 하회 (%s < %s × %.1f%%)",
                    code,
                    f"{current:,}",
                    f"{today_open:,}",
                    (1 - tolerance) * 100,
                )
            else:
                logger.info(
                    "모멘텀 fallback 거부: %s 시가 하회 (%s < %s)",
                    code,
                    f"{current:,}",
                    f"{today_open:,}",
                )
            return False, f"시가 하회 ({current:,} < {today_open:,})"

        # 조건 3: 최소 거래량 확인
        if volume < config.MOMENTUM_MIN_VOLUME:
            logger.info(
                "모멘텀 fallback 거부: %s 거래량 부족 (%s < %s)",
                code,
                f"{volume:,}",
                f"{config.MOMENTUM_MIN_VOLUME:,}",
            )
            return False, f"거래량 부족 ({volume:,} < {config.MOMENTUM_MIN_VOLUME:,})"

        logger.info(
            "모멘텀 fallback 진입 확인: %s (고점 %.1f%%, 시가↑, 거래량 %s)",
            code,
            high_ratio * 100,
            f"{volume:,}",
        )
        return True, f"fallback 통과 (고점 {high_ratio * 100:.1f}%, 거래량 {volume:,})"

    @staticmethod
    def _apply_hard_filters(
        stocks: list[dict], is_market_open: bool, phase: str = "morning"
    ) -> list[dict]:
        passed = []
        if phase == "afternoon":
            change_min = config.AFTERNOON_HARD_FILTER_CHANGE_MIN
            change_max = config.AFTERNOON_HARD_FILTER_CHANGE_MAX
        else:
            change_min = 0.5
            change_max = config.MORNING_HARD_FILTER_CHANGE_MAX

        try:
            import main as _main_mod

            if getattr(_main_mod, "_boost_state", {}).get("active"):
                prev_max = change_max
                change_max = config.BOOST_HARD_FILTER_CHANGE_MAX
                logger.info(
                    "불장 모드 하드필터 확대: change_max %.1f%% → %.1f%%",
                    prev_max,
                    change_max,
                )
        except Exception:
            pass

        for s in stocks:
            name = s.get("hts_kor_isnm", "?")
            change_pct = float(str(s.get("prdy_ctrt", "0")).replace(",", "") or "0")

            if change_pct >= config.HARD_FILTER_MAX_CHANGE:
                logger.info(
                    "필터 제외 [+%.0f%%↑ 급등]: %s (%.1f%%)",
                    config.HARD_FILTER_MAX_CHANGE,
                    name,
                    change_pct,
                )
                continue

            if is_market_open and not (change_min <= change_pct <= change_max):
                logger.info(
                    "필터 제외 [등락률 %.1f~%.1f%% 미충족]: %s (%.1f%%)",
                    change_min,
                    change_max,
                    name,
                    change_pct,
                )
                continue

            raw_tv = str(s.get("acml_tr_pbmn", "0")).replace(",", "")
            trading_value = int(raw_tv) if raw_tv.isdigit() else 0
            price = int(str(s.get("stck_prpr", "0")).replace(",", "") or "0")
            min_tv = _min_trading_value(price)
            if trading_value > 0 and trading_value < min_tv:
                logger.info(
                    "필터 제외 [거래대금 %s 미만]: %s (%s)",
                    f"{min_tv / 1e8:.0f}억",
                    name,
                    f"{trading_value:,}",
                )
                continue

            pos_from_high = s.get("position_from_high", -999)
            if isinstance(pos_from_high, (int, float)) and pos_from_high < -10.0:
                logger.info(
                    "필터 제외 [고점 대비 -10%% 초과 하락]: %s (%.1f%%)",
                    name,
                    pos_from_high,
                )
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
                            logger.info(
                                "필터 제외 [5분봉 거래량 급감]: %s (최근 %s → %s)",
                                name,
                                f"{vols[0]:,}",
                                f"{vols[-1]:,}",
                            )
                            continue

            passed.append(s)
        return passed

    def _get_dual_sourced_candidates(self, phase: str = "morning") -> list[dict]:
        if phase == "afternoon":
            rate_min = config.AFTERNOON_HARD_FILTER_CHANGE_MIN
            rate_max = config.AFTERNOON_HARD_FILTER_CHANGE_MAX
        else:
            rate_min = 0.5
            rate_max = config.MORNING_HARD_FILTER_CHANGE_MAX

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
            len(source_a),
            len(source_b),
            len(source_c),
            len(merged),
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
                # 기본 필터: 1000원 이상, 거래량 5만 이상, 급등 상한 미만
                if (
                    price >= config.DUAL_SOURCING_MIN_PRICE
                    and vol >= 50000
                    and change < config.HARD_FILTER_MAX_CHANGE
                ):
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
                logger.info(
                    "등락률 범위 순위 소스: KIS (%d종목, %.1f~%.1f%%)",
                    len(ranking),
                    rate_min,
                    rate_max,
                )
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
        for item in volume_ranking[: config.ENRICHMENT_POOL_SIZE]:
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

    def fetch_crash_inverse_candidates(self) -> list[dict]:
        candidates = []
        for code, name, etf_type in config.CRASH_INVERSE_ETFS:
            try:
                url = f"{config.KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
                params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code}
                resp = self.kis._get(
                    url, headers=self.kis._headers("FHKST01010100"), params=params
                )
                d = resp.json().get("output", {})

                price = int(d.get("stck_prpr", 0))
                change_pct = float(d.get("prdy_ctrt", 0))
                volume = int(d.get("acml_vol", 0))
                tr_pbmn = int(d.get("acml_tr_pbmn", 0))
                today_high = int(d.get("stck_hgpr", 0))
                today_open = int(d.get("stck_oprc", 0))

                if change_pct < config.CRASH_MIN_CHANGE_PCT:
                    logger.info(
                        "크래시 제외 [등락률 %.1f%% < %.1f%%]: %s",
                        change_pct,
                        config.CRASH_MIN_CHANGE_PCT,
                        name,
                    )
                    continue

                high_ratio = price / today_high if today_high > 0 else 0
                open_ratio = price / today_open if today_open > 0 else 0

                score = change_pct * 3
                if high_ratio >= 0.97:
                    score += 15
                if open_ratio >= 1.0:
                    score += 10
                if tr_pbmn >= 100_000_000_000:
                    score += 10

                candidates.append(
                    {
                        "mksc_shrn_iscd": code,
                        "hts_kor_isnm": name,
                        "stck_prpr": str(price),
                        "prdy_ctrt": str(change_pct),
                        "acml_vol": str(volume),
                        "acml_tr_pbmn": str(tr_pbmn),
                        "stck_hgpr": str(today_high),
                        "stck_oprc": str(today_open),
                        "stck_lwpr": d.get("stck_lwpr", "0"),
                        "momentum_score": score,
                        "is_crash_inverse": True,
                        "etf_type": etf_type,
                    }
                )
                logger.info(
                    "크래시 후보: %s | %s원 (%+.1f%%) | 스코어 %.1f | 거래대금 %s억",
                    name,
                    f"{price:,}",
                    change_pct,
                    score,
                    f"{tr_pbmn / 1e8:.0f}",
                )
            except Exception as e:
                logger.warning("크래시 ETF 조회 실패 %s: %s", name, e)

        candidates.sort(key=lambda x: x["momentum_score"], reverse=True)
        return candidates

    @staticmethod
    def _safe(fn, default):
        try:
            return fn()
        except Exception as e:
            logger.warning("API 호출 실패: %s", e)
            return default


# ═══════════════════════════════════════════════════════════════════════════════
# 비대칭 R:R 분석 모듈 — VWAP / 호가 / 수급 / 거래량 / 진입 품질 판정
# ═══════════════════════════════════════════════════════════════════════════════


def calculate_vwap(candles_5m: list[dict]) -> dict:
    """5분봉으로 장중 VWAP + 현재 deviation 계산.

    Returns:
        {"vwap": float, "deviation_pct": float, "above_vwap": bool}
    """
    cum_tp_vol = 0.0
    cum_vol = 0

    # candles_5m은 최신순 → 역순으로 순회해야 시간순
    for c in reversed(candles_5m):
        high = int(str(c.get("high", 0)).replace(",", "") or 0)
        low = int(str(c.get("low", 0)).replace(",", "") or 0)
        close = int(str(c.get("close", 0)).replace(",", "") or 0)
        volume = int(str(c.get("volume", 0)).replace(",", "") or 0)
        if high <= 0 or low <= 0 or close <= 0 or volume <= 0:
            continue
        typical_price = (high + low + close) / 3
        cum_tp_vol += typical_price * volume
        cum_vol += volume

    if cum_vol <= 0:
        return {"vwap": 0.0, "deviation_pct": 0.0, "above_vwap": False}

    vwap = cum_tp_vol / cum_vol

    # 현재가 = 가장 최신 캔들의 close
    latest_close = 0
    if candles_5m:
        latest_close = int(str(candles_5m[0].get("close", 0)).replace(",", "") or 0)

    deviation_pct = 0.0
    above_vwap = False
    if latest_close > 0 and vwap > 0:
        deviation_pct = (latest_close - vwap) / vwap * 100
        above_vwap = latest_close >= vwap

    return {
        "vwap": round(vwap, 1),
        "deviation_pct": round(deviation_pct, 2),
        "above_vwap": above_vwap,
    }


def calculate_orderbook_imbalance(orderbook: dict) -> dict:
    """호가 10단계 매수/매도 불균형 계산.

    Top 5 levels만 사용. ratio = bid_vol / ask_vol.

    Returns:
        {"ratio": float, "bid_wall": bool, "ask_wall": bool,
         "signal": "buy"|"avoid"|"neutral"}
    """
    if not orderbook:
        return {"ratio": 1.0, "bid_wall": False, "ask_wall": False, "signal": "neutral"}

    bid_volumes = orderbook.get("bid_volumes", [])
    ask_volumes = orderbook.get("ask_volumes", [])

    # Top 5 levels
    top_bid = sum(bid_volumes[:5]) if bid_volumes else 0
    top_ask = sum(ask_volumes[:5]) if ask_volumes else 0

    ratio = top_bid / max(top_ask, 1)

    # Wall 감지: 평균 대비 ORDERBOOK_WALL_THRESHOLD 배 이상
    avg_bid = top_bid / 5 if top_bid > 0 else 1
    avg_ask = top_ask / 5 if top_ask > 0 else 1
    bid_wall = any(v >= avg_bid * config.ORDERBOOK_WALL_THRESHOLD for v in bid_volumes[:5])
    ask_wall = any(v >= avg_ask * config.ORDERBOOK_WALL_THRESHOLD for v in ask_volumes[:5])

    # Signal 판정
    if ratio >= config.ORDERBOOK_MIN_BID_ASK_RATIO:
        signal = "buy"
    elif ratio < 0.7 or ask_wall:
        signal = "avoid"
    else:
        signal = "neutral"

    return {
        "ratio": round(ratio, 2),
        "bid_wall": bid_wall,
        "ask_wall": ask_wall,
        "signal": signal,
    }


def analyze_institutional_flow(foreign_data: list[dict]) -> dict:
    """기관/외국인 수급 분석 (당일 + 3일 추세).

    foreign_data = kis.get_foreign_institution(code) 결과.
    Fields: frgn_ntby_qty (외국인순매수), orgn_ntby_qty (기관순매수).

    Returns:
        {"foreign_buying": bool, "institution_buying": bool, "both_buying": bool,
         "consecutive_days": int, "flow_score": float}
    """
    if not foreign_data:
        return {
            "foreign_buying": False,
            "institution_buying": False,
            "both_buying": False,
            "consecutive_days": 0,
            "flow_score": 0.0,
        }

    # 최신(당일) 데이터
    today = foreign_data[0] if foreign_data else {}
    frgn_qty = int(str(today.get("frgn_ntby_qty", 0)).replace(",", "") or 0)
    orgn_qty = int(str(today.get("orgn_ntby_qty", 0)).replace(",", "") or 0)

    foreign_buying = frgn_qty > 0
    institution_buying = orgn_qty > 0
    both_buying = foreign_buying and institution_buying

    # 연속 순매수일 계산 (최대 5일)
    consecutive_days = 0
    for d in foreign_data[:5]:
        f_qty = int(str(d.get("frgn_ntby_qty", 0)).replace(",", "") or 0)
        o_qty = int(str(d.get("orgn_ntby_qty", 0)).replace(",", "") or 0)
        if f_qty > 0 or o_qty > 0:
            consecutive_days += 1
        else:
            break

    # flow_score: 0.0 ~ 1.0
    score = 0.0
    if foreign_buying:
        score += 0.3
    if institution_buying:
        score += 0.3
    if both_buying:
        score += 0.2
    if consecutive_days >= 3:
        score += 0.2
    elif consecutive_days >= 2:
        score += 0.1

    return {
        "foreign_buying": foreign_buying,
        "institution_buying": institution_buying,
        "both_buying": both_buying,
        "consecutive_days": consecutive_days,
        "flow_score": round(min(score, 1.0), 2),
    }


def is_real_buying(candles_5m: list[dict]) -> tuple[bool, str]:
    """실제 매수세 vs dead cat bounce 판별.

    Oracle 기준:
    - volume_ratio > 1.5
    - buying_ratio > 0.6 (close-low / high-low)
    - 연속 green candle + rising volume

    Returns: (is_real, reason)
    """
    if len(candles_5m) < 2:
        return False, "캔들 데이터 부족"

    # 최근 2~3개 캔들 분석 (최신순)
    recent = candles_5m[:3]

    green_count = 0
    total_buying_ratio = 0.0
    prev_vol = 0

    for i, c in enumerate(recent):
        high = int(str(c.get("high", 0)).replace(",", "") or 0)
        low = int(str(c.get("low", 0)).replace(",", "") or 0)
        close = int(str(c.get("close", 0)).replace(",", "") or 0)
        opn = int(str(c.get("open", 0)).replace(",", "") or 0)
        volume = int(str(c.get("volume", 0)).replace(",", "") or 0)

        if high <= low:
            continue

        # Buying ratio: close-low / high-low
        buying_ratio = (close - low) / (high - low)
        total_buying_ratio += buying_ratio

        if close >= opn:
            green_count += 1

        prev_vol = volume

    avg_buying_ratio = total_buying_ratio / len(recent) if recent else 0

    # 직전 캔들 대비 거래량 비율
    curr_vol = int(str(candles_5m[0].get("volume", 0)).replace(",", "") or 0)
    prev_candle_vol = int(str(candles_5m[1].get("volume", 0)).replace(",", "") or 0) if len(candles_5m) >= 2 else 1
    volume_ratio = curr_vol / max(prev_candle_vol, 1)

    # 종합 판정
    reasons = []
    is_real = True

    if volume_ratio < 1.5:
        is_real = False
        reasons.append(f"거래량 부족 ({volume_ratio:.1f}x < 1.5x)")

    if avg_buying_ratio < 0.6:
        is_real = False
        reasons.append(f"매수세 약함 (buying_ratio {avg_buying_ratio:.2f} < 0.6)")

    if green_count < 2:
        is_real = False
        reasons.append(f"양봉 부족 ({green_count}/{len(recent)})")

    if is_real:
        return True, f"실매수세 확인 (vol {volume_ratio:.1f}x, buy_ratio {avg_buying_ratio:.2f}, 양봉 {green_count}/{len(recent)})"
    return False, ", ".join(reasons)


def assess_entry_quality(
    code: str,
    kis: KISClient,
    candles_5m: list[dict],
    foreign_data: list[dict],
) -> dict:
    """진입 품질 종합 판정 — VWAP + 호가 + 수급 조합.

    Returns:
        {"quality": "premium"|"standard"|"weak",
         "vwap_ok": bool, "orderbook_ok": bool, "flow_ok": bool,
         "stop_loss_pct": float, "position_scale": float,
         "details": str,
         "vwap_data": dict, "orderbook_data": dict, "flow_data": dict}
    """
    details = []

    # 1) VWAP 분석
    vwap_ok = False
    vwap_data = {"vwap": 0.0, "deviation_pct": 0.0, "above_vwap": False}
    if config.VWAP_ENABLED and candles_5m:
        vwap_data = calculate_vwap(candles_5m)
        if vwap_data["above_vwap"] and vwap_data["deviation_pct"] <= config.VWAP_ENTRY_MAX_DEVIATION_PCT:
            vwap_ok = True
            details.append(f"VWAP✓ (deviation {vwap_data['deviation_pct']:+.1f}%)")
        elif not vwap_data["above_vwap"]:
            details.append("VWAP✗ (하회)")
        else:
            details.append(f"VWAP✗ (과열 +{vwap_data['deviation_pct']:.1f}%)")
    else:
        details.append("VWAP 비활성")

    # 2) 호가 분석
    orderbook_ok = False
    orderbook_data = {"ratio": 1.0, "bid_wall": False, "ask_wall": False, "signal": "neutral"}
    if config.ORDERBOOK_ENABLED:
        try:
            ob = kis.get_orderbook(code)
            orderbook_data = calculate_orderbook_imbalance(ob)
            if orderbook_data["signal"] == "buy":
                orderbook_ok = True
                details.append(f"호가✓ (bid/ask {orderbook_data['ratio']:.2f})")
            else:
                details.append(f"호가✗ ({orderbook_data['signal']}, {orderbook_data['ratio']:.2f})")
        except Exception as e:
            logger.warning("호가 조회 실패 %s: %s", code, e)
            details.append("호가 조회 실패")
    else:
        details.append("호가 비활성")

    # 3) 수급 분석
    flow_ok = False
    flow_data = analyze_institutional_flow(foreign_data)
    if config.FLOW_BONUS_ENABLED:
        if flow_data["both_buying"]:
            flow_ok = True
            details.append(f"수급✓ (외국인+기관 동시매수, {flow_data['consecutive_days']}일연속)")
        elif flow_data["foreign_buying"] or flow_data["institution_buying"]:
            flow_ok = True
            who = "외국인" if flow_data["foreign_buying"] else "기관"
            details.append(f"수급△ ({who} 순매수)")
        else:
            details.append("수급✗ (순매도)")
    else:
        details.append("수급 비활성")

    # 품질 등급 판정
    ok_count = sum([vwap_ok, orderbook_ok, flow_ok])
    if ok_count >= 3:
        quality = "premium"
    elif ok_count >= 2:
        quality = "standard"
    else:
        quality = "weak"

    # config에서 stop_loss_pct, position_scale 조회
    stop_loss_pct = config.TIGHT_STOP_LOSS_PCT  # default
    for signal_name, pct in config.TIGHT_STOP_BY_SIGNAL:
        if signal_name == quality:
            stop_loss_pct = pct
            break

    position_scale = config.ENTRY_QUALITY_POSITION_SCALE.get(quality, 0.7)

    return {
        "quality": quality,
        "vwap_ok": vwap_ok,
        "orderbook_ok": orderbook_ok,
        "flow_ok": flow_ok,
        "stop_loss_pct": stop_loss_pct,
        "position_scale": position_scale,
        "details": " | ".join(details),
        "vwap_data": vwap_data,
        "orderbook_data": orderbook_data,
        "flow_data": flow_data,
    }