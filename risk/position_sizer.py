"""Position sizing helpers aligned with Rayner risk philosophy."""

from __future__ import annotations
from typing import Tuple


def atr_based_size(
    equity: float,
    risk_pct: float,
    entry: float,
    atr: float,
    atr_mult: float = 2.0,
) -> Tuple[int, float]:
    """
    Classic volatility / ATR sizing: risk a fixed % of equity.
    Returns (shares, stop_price).
    """
    stop_dist = atr * atr_mult
    if stop_dist <= 0 or entry <= 0:
        return 0, 0.0
    risk_amount = equity * risk_pct
    shares = int(risk_amount / stop_dist)
    stop_price = entry - stop_dist
    return max(0, shares), stop_price


def capital_pct_size(equity: float, pct: float, entry: float) -> int:
    """
    Rayner-style mean-reversion allocation: fixed % of capital per position.
    """
    if entry <= 0:
        return 0
    return max(0, int((equity * pct) / entry))
