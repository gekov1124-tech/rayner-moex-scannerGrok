"""
Simple bar-by-bar backtester.
- Entries from strategy.generate_setups() on expanding history
- Exits: stop loss + rule-based (RSI, time, MA, Donchian, ATR trail)
Educational only — not production broker simulation (no slippage model beyond optional bps).
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
import numpy as np
import pandas as pd

from strategies.base import Strategy, Setup
from utils.indicators import sma, ema, rsi, atr, lowest_close


@dataclass
class Trade:
    ticker: str
    strategy: str
    direction: str
    entry_date: str
    entry_price: float
    exit_date: str = ""
    exit_price: float = 0.0
    stop: float = 0.0
    shares: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    bars_held: int = 0
    exit_reason: str = ""
    risk_amount: float = 0.0


@dataclass
class BacktestResult:
    strategy: str
    ticker: str = "PORTFOLIO"
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


def _metrics_from_trades(
    trades: List[Trade],
    initial_equity: float,
    equity_curve: List[float],
) -> Dict[str, Any]:
    closed = [t for t in trades if t.exit_date]
    if not closed:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_pnl_pct": 0.0,
            "total_pnl": 0.0,
            "total_return_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_bars": 0.0,
            "expectancy_pct": 0.0,
        }
    pnls = [t.pnl for t in closed]
    pcts = [t.pnl_pct for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0)

    # max DD from equity curve
    max_dd = 0.0
    if equity_curve:
        peak = equity_curve[0]
        for e in equity_curve:
            peak = max(peak, e)
            dd = (peak - e) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

    return {
        "trades": len(closed),
        "win_rate": round(100.0 * len(wins) / len(closed), 1),
        "avg_pnl_pct": round(float(np.mean(pcts)) * 100, 2),
        "total_pnl": round(sum(pnls), 0),
        "total_return_pct": round(100.0 * (equity_curve[-1] / initial_equity - 1), 2)
        if equity_curve
        else 0.0,
        "profit_factor": round(pf, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "avg_bars": round(float(np.mean([t.bars_held for t in closed])), 1),
        "expectancy_pct": round(float(np.mean(pcts)) * 100, 2),
    }


def _check_exit(
    strategy_name: str,
    direction: str,
    entry_price: float,
    stop: float,
    bars_held: int,
    row: pd.Series,
    df_hist: pd.DataFrame,
    trail_atr_mult: float = 6.0,
) -> Optional[tuple]:
    """
    Returns (exit_price, reason) or None.
    """
    high = float(row["High"])
    low = float(row["Low"])
    close = float(row["Close"])

    # 1) Stop
    if direction == "long" and low <= stop:
        return stop, "stop"
    if direction == "short" and high >= stop:
        return stop, "stop"

    name = strategy_name

    # Precompute helpers on history including current bar
    try:
        close_s = df_hist["Close"]
        rsi2 = rsi(close_s, 2)
        last_rsi = float(rsi2.iloc[-1]) if len(rsi2) else np.nan
        sma5 = sma(close_s, 5)
        ema50 = ema(close_s, 50)
        atr14 = atr(df_hist, 14)
        last_atr = float(atr14.iloc[-1]) if len(atr14) and not pd.isna(atr14.iloc[-1]) else None
    except Exception:
        last_rsi = np.nan
        sma5 = ema50 = None
        last_atr = None

    if name == "RaynerBB_MeanRev":
        if not pd.isna(last_rsi) and last_rsi > 50:
            return close, "RSI2>50"
        if bars_held >= 10:
            return close, "time_stop_10d"

    elif name == "ConnorsRSI2":
        if not pd.isna(last_rsi) and last_rsi > 65:
            return close, "RSI2>65"
        if sma5 is not None and not pd.isna(sma5.iloc[-1]) and close > float(sma5.iloc[-1]):
            return close, "Close>SMA5"

    elif name == "EMA_Pullback":
        if ema50 is not None and not pd.isna(ema50.iloc[-1]) and close < float(ema50.iloc[-1]):
            return close, "Close<EMA50"

    elif name == "TrendBreakout_200High":
        # Trailing stop from high water / ATR
        if last_atr and direction == "long":
            trail = high - trail_atr_mult * last_atr  # approximate: use bar high
            # better: trail from max close since entry — handled by updating stop outside
            pass
        # exit if close below trail stop (stop is updated by caller)
        if direction == "long" and close < stop:
            return stop, "trail_ATR"
        if direction == "short" and close > stop:
            return stop, "trail_ATR"

    elif name == "Donchian20":
        # Exit on close below 10-day low (classic turtle-ish)
        if len(df_hist) >= 11:
            ll = float(df_hist["Low"].iloc[-11:-1].min())
            if direction == "long" and close < ll:
                return close, "Donchian10_exit"

    elif name == "Rayner_BOS_MTF":
        # Structure stop already in stop; optional trail: close back inside prior bar range
        if direction == "long" and bars_held >= 1:
            if last_atr and close < entry_price - 3 * last_atr:
                return close, "structure_fail"
        if bars_held >= 20:
            return close, "time_stop_20d"

    return None


def backtest_symbol(
    ticker: str,
    df: pd.DataFrame,
    strategy: Strategy,
    equity: float = 1_000_000,
    risk_pct: float = 0.01,
    min_bars: int = 220,
    step: int = 1,
    one_position: bool = True,
) -> BacktestResult:
    """
    Walk forward day by day (or every `step` bars).
    """
    if df is None or len(df) < min_bars + 30:
        return BacktestResult(strategy=strategy.name, ticker=ticker, metrics={"trades": 0, "error": "not_enough_bars"})

    df = df.copy().sort_index()
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None
    entry_idx: Optional[int] = None
    pending = None
    pending_age = 0
    cash = equity
    equity_curve = []
    peak_price_since_entry = 0.0

    indices = list(range(min_bars, len(df), step))
    for i in indices:
        hist = df.iloc[: i + 1]
        row = hist.iloc[-1]
        date_str = str(hist.index[-1].date()) if hasattr(hist.index[-1], "date") else str(hist.index[-1])[:10]

        # Manage open position
        if open_trade is not None and entry_idx is not None:
            bars_held = i - entry_idx
            # Update trailing stop for trend breakout
            if open_trade.strategy == "TrendBreakout_200High" and open_trade.direction == "long":
                try:
                    a = float(atr(hist, 14).iloc[-1])
                    if not np.isnan(a):
                        peak_price_since_entry = max(peak_price_since_entry, float(row["High"]))
                        trail = peak_price_since_entry - 6.0 * a
                        open_trade.stop = max(open_trade.stop, trail)
                except Exception:
                    pass

            ex = _check_exit(
                open_trade.strategy,
                open_trade.direction,
                open_trade.entry_price,
                open_trade.stop,
                bars_held,
                row,
                hist,
            )
            if ex:
                exit_price, reason = ex
                open_trade.exit_date = date_str
                open_trade.exit_price = round(exit_price, 4)
                open_trade.bars_held = bars_held
                open_trade.exit_reason = reason
                if open_trade.direction == "long":
                    open_trade.pnl = (exit_price - open_trade.entry_price) * open_trade.shares
                    open_trade.pnl_pct = (exit_price / open_trade.entry_price - 1.0) if open_trade.entry_price else 0
                else:
                    open_trade.pnl = (open_trade.entry_price - exit_price) * open_trade.shares
                    open_trade.pnl_pct = (open_trade.entry_price / exit_price - 1.0) if exit_price else 0
                cash += open_trade.pnl
                trades.append(open_trade)
                open_trade = None
                entry_idx = None

        # Pending limit (BB mean-rev): try fill if low touches limit within 3 bars
        if open_trade is None and pending is not None:
            pending_age += 1
            lim, stp, sh, pending_strat, pending_dir = pending
            if float(row["Low"]) <= lim:
                entry_price = lim
                open_trade = Trade(
                    ticker=ticker,
                    strategy=pending_strat,
                    direction=pending_dir,
                    entry_date=date_str,
                    entry_price=entry_price,
                    stop=stp,
                    shares=sh,
                    risk_amount=round(cash * risk_pct, 2),
                )
                entry_idx = i
                peak_price_since_entry = entry_price
                pending = None
                pending_age = 0
            elif pending_age >= 3:
                pending = None
                pending_age = 0

        # New entry
        if open_trade is None or not one_position:
            if open_trade is not None:
                equity_curve.append(cash)
                continue
            try:
                setups = strategy.generate_setups(ticker, hist, equity=cash)
            except Exception:
                setups = []
            if setups and pending is None:
                s = setups[0]
                entry_price = float(s.entry)
                stop = float(s.stop)
                risk_per = abs(entry_price - stop) or entry_price * 0.01
                risk_amt = cash * risk_pct
                shares = max(1, int(risk_amt / risk_per))
                if entry_price * shares > cash * 0.95:
                    shares = max(1, int(cash * 0.95 / entry_price))
                # BB: place limit, fill when price reaches
                if s.strategy == "RaynerBB_MeanRev":
                    if float(row["Low"]) <= entry_price:
                        open_trade = Trade(
                            ticker=ticker, strategy=s.strategy, direction=s.direction,
                            entry_date=date_str, entry_price=entry_price, stop=stop,
                            shares=shares, risk_amount=round(risk_amt, 2),
                        )
                        entry_idx = i
                        peak_price_since_entry = entry_price
                    else:
                        pending = (entry_price, stop, shares, s.strategy, s.direction)
                        pending_age = 0
                else:
                    open_trade = Trade(
                        ticker=ticker, strategy=s.strategy, direction=s.direction,
                        entry_date=date_str, entry_price=entry_price, stop=stop,
                        shares=shares, risk_amount=round(risk_amt, 2),
                    )
                    entry_idx = i
                    peak_price_since_entry = entry_price

        # Mark equity
        mtm = cash
        if open_trade is not None:
            if open_trade.direction == "long":
                mtm = cash + (float(row["Close"]) - open_trade.entry_price) * open_trade.shares
            else:
                mtm = cash + (open_trade.entry_price - float(row["Close"])) * open_trade.shares
        equity_curve.append(mtm)

    # Close leftover at last close
    if open_trade is not None:
        last = df.iloc[-1]
        date_str = str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1])[:10]
        exit_price = float(last["Close"])
        open_trade.exit_date = date_str
        open_trade.exit_price = exit_price
        open_trade.bars_held = (len(df) - 1 - (entry_idx or 0))
        open_trade.exit_reason = "eod_force"
        if open_trade.direction == "long":
            open_trade.pnl = (exit_price - open_trade.entry_price) * open_trade.shares
            open_trade.pnl_pct = exit_price / open_trade.entry_price - 1.0
        else:
            open_trade.pnl = (open_trade.entry_price - exit_price) * open_trade.shares
            open_trade.pnl_pct = open_trade.entry_price / exit_price - 1.0
        cash += open_trade.pnl
        trades.append(open_trade)

    result = BacktestResult(
        strategy=strategy.name,
        ticker=ticker,
        trades=trades,
        equity_curve=equity_curve,
    )
    result.metrics = _metrics_from_trades(trades, equity, equity_curve)
    return result


def backtest_portfolio(
    data: Dict[str, pd.DataFrame],
    strategy: Strategy,
    equity: float = 1_000_000,
    risk_pct: float = 0.01,
    max_positions: int = 5,
) -> BacktestResult:
    """
    Run per-symbol backtests and aggregate metrics (independent capital slices).
    Not a true multi-asset portfolio engine — good for strategy comparison.
    """
    all_trades: List[Trade] = []
    # Equal risk budget per symbol for independent sims
    per_eq = equity
    for ticker, df in data.items():
        r = backtest_symbol(ticker, df, strategy, equity=per_eq, risk_pct=risk_pct)
        all_trades.extend(r.trades)

    # Synthetic equity: start equity + sum of chronological pnls
    trades_sorted = sorted(all_trades, key=lambda t: t.entry_date)
    curve = [equity]
    eq = equity
    for t in trades_sorted:
        if t.exit_date:
            eq += t.pnl
            curve.append(eq)

    result = BacktestResult(
        strategy=strategy.name,
        ticker="PORTFOLIO",
        trades=trades_sorted,
        equity_curve=curve,
    )
    result.metrics = _metrics_from_trades(trades_sorted, equity, curve)
    return result
