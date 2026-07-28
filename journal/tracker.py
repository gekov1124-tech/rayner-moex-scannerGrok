"""Update open paper trades from latest market data; apply stop / exit rules."""

from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from journal.store import JournalStore, PaperTrade
from monitor.session import now_msk
from backtest.engine import _check_exit
from utils.indicators import atr


def _bars_held(entry_date: str, df: pd.DataFrame) -> int:
    try:
        ed = pd.Timestamp(entry_date)
        if not isinstance(df.index, pd.DatetimeIndex):
            return 0
        after = df.index[df.index.date >= ed.date()] if hasattr(df.index[0], "day") else df.index[df.index >= ed]
        return max(0, len(after) - 1)
    except Exception:
        return 0


def update_open_trades(
    store: JournalStore,
    data: Dict[str, pd.DataFrame],
) -> List[PaperTrade]:
    """
    Mark-to-market open trades; close on stop or rule exit.
    Returns list of trades closed this pass.
    """
    closed: List[PaperTrade] = []
    today = now_msk().strftime("%Y-%m-%d")

    for trade in list(store.open_trades()):
        df = data.get(trade.ticker)
        if df is None or df.empty:
            continue
        row = df.iloc[-1]
        price = float(row["Close"])
        trade.mtm_price = price
        if trade.direction == "long":
            trade.mtm_pnl = (price - trade.entry_price) * trade.shares
        else:
            trade.mtm_pnl = (trade.entry_price - price) * trade.shares

        bars = _bars_held(trade.entry_date, df)
        # trailing for trend breakout
        stop = trade.stop
        if trade.strategy == "TrendBreakout_200High" and trade.direction == "long":
            try:
                a = float(atr(df, 14).iloc[-1])
                if a == a:  # not NaN
                    trail = float(row["High"]) - 6.0 * a
                    stop = max(stop, trail)
                    trade.stop = stop
            except Exception:
                pass

        ex = _check_exit(
            trade.strategy,
            trade.direction,
            trade.entry_price,
            stop,
            bars,
            row,
            df,
        )
        if ex:
            exit_price, reason = ex
            closed_t = store.close_trade(
                trade.id,
                exit_price=exit_price,
                exit_date=today,
                exit_reason=reason,
                bars_held=bars,
            )
            if closed_t:
                closed.append(closed_t)
        else:
            # persist MTM
            store.save()

    return closed
