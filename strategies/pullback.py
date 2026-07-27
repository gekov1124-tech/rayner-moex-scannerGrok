"""
EMA / MA Pullback strategy — simplified rules-based version of Rayner MAEE + pullback ideas.
Uptrend + pullback into value zone (EMA) + objective trigger.
"""

from __future__ import annotations
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from .base import Strategy, Setup
from .registry import register
from utils.indicators import sma, ema, atr, roc, distance_to_ma


@register("EMA_Pullback")
class EMA_Pullback(Strategy):
    """
    Simplified rules-based pullback to EMA zone in uptrend.
    Conditions:
      - Close > SMA(200)
      - Price within zone_pct of EMA20 or EMA50 (pullback into value)
      - Recent bullish price action (Close > Open and Close > prior Close)
      - Not already extended too far
    Stop: below recent swing / ATR multiple.
    Exit idea: close below EMA50 or trail.
    """

    def __init__(self, params: Optional[Dict] = None):
        default = {
            "sma_period": 200,
            "ema_fast": 20,
            "ema_slow": 50,
            "zone_pct": 0.025,  # within 2.5% of EMA
            "atr_stop_mult": 2.0,
            "risk_pct": 0.01,
            "min_roc": -5.0,  # avoid very weak names
        }
        super().__init__("EMA_Pullback", {**default, **(params or {})})

    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        p = self.params
        if len(df) < p["sma_period"] + 30:
            return []

        df = df.copy()
        df["SMA200"] = sma(df["Close"], p["sma_period"])
        df["EMA20"] = ema(df["Close"], p["ema_fast"])
        df["EMA50"] = ema(df["Close"], p["ema_slow"])
        df["ATR"] = atr(df, 14)
        df["ROC100"] = roc(df["Close"], 100)
        df["Dist20"] = distance_to_ma(df["Close"], df["EMA20"])
        df["Dist50"] = distance_to_ma(df["Close"], df["EMA50"])

        last = df.iloc[-1]
        prev = df.iloc[-2]

        if any(pd.isna(last[c]) for c in ["SMA200", "EMA20", "EMA50", "ATR"]):
            return []

        in_uptrend = last["Close"] > last["SMA200"]
        near_value = (
            abs(last["Dist20"]) <= p["zone_pct"] * 100
            or abs(last["Dist50"]) <= p["zone_pct"] * 100
        )
        # Simple bullish candle + higher close as trigger
        bullish_trigger = (
            last["Close"] > last["Open"]
            and last["Close"] > prev["Close"]
            and last["Low"] <= max(last["EMA20"], last["EMA50"]) * 1.01
        )
        not_weak = (not pd.isna(last["ROC100"])) and last["ROC100"] > p["min_roc"]

        if in_uptrend and near_value and bullish_trigger and not_weak:
            entry = float(last["Close"])
            stop = entry - p["atr_stop_mult"] * float(last["ATR"])
            risk_per_share = entry - stop
            if risk_per_share <= 0:
                return []
            risk_amount = equity * p["risk_pct"]
            size = max(1, int(risk_amount / risk_per_share))
            score = float(last["ROC100"]) if not pd.isna(last["ROC100"]) else 10.0

            return [
                Setup(
                    ticker=ticker,
                    strategy=self.name,
                    direction="long",
                    entry=round(entry, 2),
                    stop=round(stop, 2),
                    exit_rule="Close below EMA50 or trail with structure / ATR",
                    atr=round(float(last["ATR"]), 2),
                    score=score,
                    reason=(
                        f"Uptrend ( >SMA200 ), pullback near EMA20/50 zone, "
                        f"bullish candle trigger. Dist20={last['Dist20']:.1f}%"
                    ),
                    suggested_shares=size,
                    risk_amount=round(risk_amount, 2),
                    capital_pct=p["risk_pct"],
                )
            ]
        return []
