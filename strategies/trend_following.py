"""
Trend-following / breakout strategies aligned with Rayner Teo.
- Rayner 200-day high breakout (his own system)
- Classic Turtle / Donchian breakouts (he improved Turtle concepts)
Philosophy: participate in trends, buy high / sell higher, ATR risk control.
"""

from __future__ import annotations
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from .base import Strategy, Setup
from .registry import register
from utils.indicators import sma, atr, highest_close, lowest_close, donchian, roc


@register("TrendBreakout_200High")
class TrendBreakout_200High(Strategy):
    """
    Rayner Teo simple Trend Following:
      Long when Close makes a new 200-day high close.
      Trail / stop = 6 * ATR.
      Inverse for short (optional, here long-only for long bias).
    """

    def __init__(self, params: Optional[Dict] = None):
        default = {
            "lookback": 200,
            "atr_period": 14,
            "atr_mult": 6.0,
            "risk_pct": 0.01,  # 1% risk of equity
        }
        super().__init__("TrendBreakout_200High", {**default, **(params or {})})

    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        p = self.params
        if len(df) < p["lookback"] + 20:
            return []

        df = df.copy()
        df["HH"] = highest_close(df, p["lookback"])
        df["ATR"] = atr(df, p["atr_period"])
        df["ROC100"] = roc(df["Close"], 100)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        if pd.isna(last["HH"]) or pd.isna(last["ATR"]):
            return []

        # New 200-day high close
        if last["Close"] >= last["HH"] and prev["Close"] < prev["HH"]:
            entry = float(last["Close"])
            stop = entry - p["atr_mult"] * float(last["ATR"])
            risk_per_share = entry - stop
            if risk_per_share <= 0:
                return []
            risk_amount = equity * p["risk_pct"]
            size = max(1, int(risk_amount / risk_per_share))
            score = float(last["ROC100"]) if not pd.isna(last["ROC100"]) else 50.0

            return [
                Setup(
                    ticker=ticker,
                    strategy=self.name,
                    direction="long",
                    entry=round(entry, 2),
                    stop=round(stop, 2),
                    exit_rule=f"Trailing stop {p['atr_mult']}*ATR (or structure)",
                    atr=round(float(last["ATR"]), 2),
                    score=score + 20,  # bonus for pure breakout
                    reason=f"New {p['lookback']}-day high close at {entry:.2f}. Trend participation (Rayner TF).",
                    suggested_shares=size,
                    risk_amount=round(risk_amount, 2),
                    capital_pct=p["risk_pct"],
                )
            ]
        return []


@register("Donchian20")
class Donchian20(Strategy):
    """
    Classic Turtle / Donchian System 1 style (Rayner-compatible).
    Long on break of 20-day high, exit on break of 10-day low.
    Position sized by ATR (N) for fixed risk.
    """

    def __init__(self, params: Optional[Dict] = None):
        default = {
            "entry_period": 20,
            "exit_period": 10,
            "atr_period": 20,
            "risk_pct": 0.01,
            "atr_stop_mult": 2.0,  # initial stop approx 2N
        }
        super().__init__("Donchian20", {**default, **(params or {})})

    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        p = self.params
        if len(df) < max(p["entry_period"], p["exit_period"]) + 30:
            return []

        df = df.copy()
        high20, low20 = donchian(df, p["entry_period"])
        high10, low10 = donchian(df, p["exit_period"])
        df["DonchianHigh"] = high20
        df["DonchianLowExit"] = low10
        df["ATR"] = atr(df, p["atr_period"])
        df["ROC100"] = roc(df["Close"], 100)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        if pd.isna(last["DonchianHigh"]) or pd.isna(last["ATR"]):
            return []

        # Breakout: close above prior 20-day high
        if last["Close"] > prev["DonchianHigh"] and prev["Close"] <= prev["DonchianHigh"]:
            entry = float(last["Close"])
            stop = entry - p["atr_stop_mult"] * float(last["ATR"])
            risk_per_share = entry - stop
            if risk_per_share <= 0:
                return []
            risk_amount = equity * p["risk_pct"]
            size = max(1, int(risk_amount / risk_per_share))
            score = float(last["ROC100"]) if not pd.isna(last["ROC100"]) else 30.0

            return [
                Setup(
                    ticker=ticker,
                    strategy=self.name,
                    direction="long",
                    entry=round(entry, 2),
                    stop=round(stop, 2),
                    exit_rule=f"Close < {p['exit_period']}-day low (Donchian exit)",
                    atr=round(float(last["ATR"]), 2),
                    score=score + 15,
                    reason=f"Donchian {p['entry_period']}-day high breakout. Turtle-style trend entry.",
                    suggested_shares=size,
                    risk_amount=round(risk_amount, 2),
                    capital_pct=p["risk_pct"],
                )
            ]
        return []
