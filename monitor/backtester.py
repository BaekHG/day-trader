"""python3 backtester.py --code 005930 --days 20"""

import argparse
import logging
import os
import sys
from datetime import datetime

import pytz
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from kis_client import KISClient

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

COMMISSION_PCT = 0.015
TAX_PCT = 0.18


class BacktestResult:
    def __init__(self):
        self.trades = []
        self.total_pnl = 0
        self.win_count = 0
        self.loss_count = 0
        self.max_drawdown_pct = 0.0
        self.total_invested = 0

    @property
    def total_trades(self):
        return self.win_count + self.loss_count

    @property
    def win_rate(self):
        return self.win_count / self.total_trades * 100 if self.total_trades else 0

    @property
    def avg_pnl_pct(self):
        if not self.trades:
            return 0
        return sum(t["pnl_pct"] for t in self.trades) / len(self.trades)

    @property
    def total_pnl_pct(self):
        return self.total_pnl / self.total_invested * 100 if self.total_invested else 0

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "백테스트 결과",
            "=" * 50,
            f"총 거래 수: {self.total_trades}",
            f"승: {self.win_count} / 패: {self.loss_count}",
            f"승률: {self.win_rate:.1f}%",
            f"총 손익: {self.total_pnl:,}원 ({self.total_pnl_pct:+.2f}%)",
            f"평균 수익률: {self.avg_pnl_pct:+.2f}%",
            f"최대 낙폭(MDD): {self.max_drawdown_pct:.2f}%",
        ]
        if self.trades:
            wins = [t["pnl_pct"] for t in self.trades if t["pnl_pct"] > 0]
            losses = [t["pnl_pct"] for t in self.trades if t["pnl_pct"] <= 0]
            if wins:
                lines.append(f"평균 수익 (승): +{sum(wins)/len(wins):.2f}%")
            if losses:
                lines.append(f"평균 손실 (패): {sum(losses)/len(losses):.2f}%")
        lines.append("=" * 50)
        return "\n".join(lines)


def _simulate_trailing_stop(candles: list[dict], entry_price: int, stop_loss_pct: float) -> dict:
    high = entry_price
    stop_price = int(entry_price * (1 - stop_loss_pct / 100))

    for i, c in enumerate(candles):
        c_high = int(str(c.get("stck_hgpr", c.get("high", 0))).replace(",", "") or 0)
        c_low = int(str(c.get("stck_lwpr", c.get("low", 0))).replace(",", "") or 0)
        c_close = int(str(c.get("stck_prpr", c.get("close", 0))).replace(",", "") or 0)

        if c_high <= 0 or c_low <= 0:
            continue

        if c_high > high:
            high = c_high

        high_pnl = (high - entry_price) / entry_price * 100
        for level_pnl, stop_pnl in config.TRAILING_STOP_LEVELS:
            if high_pnl >= level_pnl:
                trailing = int(entry_price * (1 + stop_pnl / 100))
                stop_price = max(stop_price, trailing)
                break

        if c_low <= stop_price:
            exit_price = stop_price
            exit_reason = "trailing" if stop_price > int(entry_price * (1 - stop_loss_pct / 100)) else "stop_loss"
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            cost_pct = COMMISSION_PCT * 2 + TAX_PCT
            net_pnl = pnl_pct - cost_pct
            return {
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "high_water_mark": high,
                "hold_bars": i + 1,
                "pnl_pct": round(net_pnl, 3),
            }

        if i >= 5 and abs((c_close - entry_price) / entry_price * 100) < 0.5:
            pnl_pct = (c_close - entry_price) / entry_price * 100
            cost_pct = COMMISSION_PCT * 2 + TAX_PCT
            return {
                "exit_price": c_close,
                "exit_reason": "time_exit",
                "high_water_mark": high,
                "hold_bars": i + 1,
                "pnl_pct": round(pnl_pct - cost_pct, 3),
            }

    last_close = int(str(candles[-1].get("stck_prpr", candles[-1].get("close", 0))).replace(",", "") or 0) if candles else entry_price
    pnl_pct = (last_close - entry_price) / entry_price * 100
    cost_pct = COMMISSION_PCT * 2 + TAX_PCT
    return {
        "exit_price": last_close,
        "exit_reason": "eod_close",
        "high_water_mark": high,
        "hold_bars": len(candles),
        "pnl_pct": round(pnl_pct - cost_pct, 3),
    }


def run_backtest(
    kis: KISClient,
    stock_code: str,
    days: int = 20,
    stop_loss_pct: float = 0,
    capital: int = 0,
) -> BacktestResult:
    stop_loss_pct = stop_loss_pct or config.MIN_STOP_LOSS_PCT
    capital = capital or config.TOTAL_CAPITAL
    position_size = int(capital * config.MAX_POSITION_PCT / 100)

    result = BacktestResult()
    result.total_invested = position_size * days

    daily_candles = kis.get_daily_candles(stock_code)
    if not daily_candles:
        logger.error("일봉 데이터 없음: %s", stock_code)
        return result

    target_days = daily_candles[:days]
    target_days.reverse()

    peak_equity = capital
    equity = capital

    for day_candle in target_days:
        date = day_candle.get("stck_bsop_date", "?")
        day_open = int(str(day_candle.get("stck_oprc", 0)).replace(",", "") or 0)
        day_close = int(str(day_candle.get("stck_clpr", 0)).replace(",", "") or 0)
        day_high = int(str(day_candle.get("stck_hgpr", 0)).replace(",", "") or 0)
        day_low = int(str(day_candle.get("stck_lwpr", 0)).replace(",", "") or 0)
        day_vol = int(str(day_candle.get("acml_vol", 0)).replace(",", "") or 0)

        if day_open <= 0:
            continue

        entry_price = day_open
        qty = position_size // entry_price
        if qty < 1:
            continue

        sim_candles = _generate_intraday_sim(day_open, day_high, day_low, day_close)

        trade = _simulate_trailing_stop(sim_candles, entry_price, stop_loss_pct)

        pnl_amt = int(qty * entry_price * trade["pnl_pct"] / 100)
        equity += pnl_amt
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity * 100 if peak_equity > 0 else 0
        if dd > result.max_drawdown_pct:
            result.max_drawdown_pct = dd

        trade_record = {
            "date": date,
            "stock_code": stock_code,
            "entry_price": entry_price,
            "exit_price": trade["exit_price"],
            "exit_reason": trade["exit_reason"],
            "pnl_pct": trade["pnl_pct"],
            "pnl_amt": pnl_amt,
            "hold_bars": trade["hold_bars"],
            "high_water_mark": trade["high_water_mark"],
        }
        result.trades.append(trade_record)
        result.total_pnl += pnl_amt

        if trade["pnl_pct"] > 0:
            result.win_count += 1
        else:
            result.loss_count += 1

    return result


def _generate_intraday_sim(day_open: int, day_high: int, day_low: int, day_close: int) -> list[dict]:

    candles = []
    prices = [day_open]

    if day_close >= day_open:
        prices.extend([
            int(day_open * 0.998),
            int((day_open + day_high) / 2),
            day_high,
            int((day_high + day_close) / 2),
            day_close,
        ])
    else:
        prices.extend([
            int((day_open + day_high) / 2),
            day_high,
            int((day_high + day_low) / 2),
            day_low,
            day_close,
        ])

    for i in range(len(prices) - 1):
        o = prices[i]
        c = prices[i + 1]
        h = max(o, c, int(max(o, c) * 1.002))
        l = min(o, c, int(min(o, c) * 0.998))
        h = min(h, day_high)
        l = max(l, day_low)
        candles.append({"high": h, "low": l, "close": c})

    return candles


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Day Trader 백테스터")
    parser.add_argument("--code", required=True, help="종목코드 (예: 005930)")
    parser.add_argument("--days", type=int, default=20, help="백테스트 일수")
    parser.add_argument("--stop-loss", type=float, default=None, help="손절 %% (기본: config 값)")
    parser.add_argument("--capital", type=int, default=None, help="자본금 (기본: config 값)")
    args = parser.parse_args()

    kis = KISClient()
    result = run_backtest(kis, args.code, args.days, args.stop_loss, args.capital)

    print(result.summary())
    print()
    for t in result.trades:
        emoji = "+" if t["pnl_pct"] > 0 else ""
        print(
            f"  {t['date']} | {t['entry_price']:>8,} → {t['exit_price']:>8,} | "
            f"{emoji}{t['pnl_pct']:.2f}% | {t['exit_reason']}"
        )


if __name__ == "__main__":
    main()
