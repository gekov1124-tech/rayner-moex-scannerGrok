"""
Mean-reversion strategies fully aligned with Rayner Teo + compatible quant systems.
- Only long in established uptrends (Close > SMA200)
- Extreme pullbacks (BB or RSI)
- Objective exits (RSI recovery or time stop)
"""

from __future__ import annotations
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

from .base import Strategy, Setup
from .registry import register
from utils.indicators import sma, rsi, bollinger_bands, atr, roc


@register("RaynerBB_MeanRev")
class RaynerBBMeanRev(Strategy):
    """
    Rayner Teo Bollinger Band Mean Reversion (from his 2025 system videos).
    Rules:
      1. Close > SMA(200)
      2. Close < Lower Bollinger (20, 2.5)
      3. Entry: limit ~3% below previous close
      4. Exit: 2-period RSI > 50 OR time-stop 10 trading days
      5. Position: fixed capital % (default 15%), max ~5 concurrent
      6. Prefer higher ROC for ranking
    """

    def __init__(self, params: Optional[Dict] = None):
        default = {
            "sma_period": 200,
            "bb_period": 20,
            "bb_std": 2.5,
            "limit_pct": 0.03,
            "rsi_exit_period": 2,
            "rsi_exit_level": 50,
            "time_stop": 10,
            "capital_pct": 0.15,
            "atr_stop_mult": 2.5,  # soft protective stop
        }
        super().__init__("RaynerBB_MeanRev", {**default, **(params or {})})

    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        p = self.params
        if len(df) < p["sma_period"] + 30:
            return []

        df = df.copy()
        df["SMA200"] = sma(df["Close"], p["sma_period"])
        upper, mid, lower = bollinger_bands(df, p["bb_period"], p["bb_std"])
        df["BB_lower"] = lower
        df["RSI2"] = rsi(df["Close"], p["rsi_exit_period"])
        df["ATR"] = atr(df, 14)
        df["ROC100"] = roc(df["Close"], 100)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        if (
            pd.isna(last["SMA200"])
            or pd.isna(last["BB_lower"])
            or pd.isna(last["ATR"])
        ):
            return []

        if last["Close"] > last["SMA200"] and last["Close"] < last["BB_lower"]:
            entry = float(prev["Close"] * (1.0 - p["limit_pct"]))
            stop = entry - p["atr_stop_mult"] * float(last["ATR"])
            size = max(1, int((equity * p["capital_pct"]) / entry)) if entry > 0 else 0
            score = float(last["ROC100"]) if not pd.isna(last["ROC100"]) else 0.0

            return [
                Setup(
                    ticker=ticker,
                    strategy=self.name,
                    direction="long",
                    entry=round(entry, 2),
                    stop=round(stop, 2),
                    exit_rule=f"RSI2 > {p['rsi_exit_level']} OR {p['time_stop']} trading days",
                    atr=round(float(last["ATR"]), 2),
                    score=score,
                    reason=(
                        f"Above SMA200, Close {last['Close']:.2f} < BB_lower {last['BB_lower']:.2f}. "
                        f"Limit buy ~{p['limit_pct']*100:.0f}% below prev close."
                    ),
                    suggested_shares=size,
                    risk_amount=round(equity * p["capital_pct"], 2),
                    capital_pct=p["capital_pct"],
                )
            ]
        return []


@register("ConnorsRSI2")
class ConnorsRSI2(Strategy):
    """
    Larry Connors classic RSI(2) mean-reversion — highly compatible with Rayner.
    Rules:
      1. Close > SMA(200)
      2. RSI(2) < 10 (or 5 for stricter)
      3. Entry at close / next open
      4. Exit when RSI(2) > 65 or Close > SMA(5)
      5. Protective ATR stop for risk management alignment
    """

    def __init__(self, params: Optional[Dict] = None):
        default = {
            "sma_period": 200,
            "rsi_period": 2,
            "rsi_entry": 10,
            "rsi_exit": 65,
            "capital_pct": 0.12,
            "atr_stop_mult": 2.5,
        }
        super().__init__("ConnorsRSI2", {**default, **(params or {})})

    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        p = self.params
        if len(df) < p["sma_period"] + 20:
            return []

        df = df.copy()
        df["SMA200"] = sma(df["Close"], p["sma_period"])
        df["RSI2"] = rsi(df["Close"], p["rsi_period"])
        df["SMA5"] = sma(df["Close"], 5)
        df["ATR"] = atr(df, 14)
        df["ROC100"] = roc(df["Close"], 100)

        last = df.iloc[-1]

        if pd.isna(last["SMA200"]) or pd.isna(last["RSI2"]) or pd.isna(last["ATR"]):
            return []

        if last["Close"] > last["SMA200"] and last["RSI2"] < p["rsi_entry"]:
            entry = float(last["Close"])
            stop = entry - p["atr_stop_mult"] * float(last["ATR"])
            size = max(1, int((equity * p["capital_pct"]) / entry)) if entry > 0 else 0
            score = float(last["ROC100"]) if not pd.isna(last["ROC100"]) else 0.0

            return [
                Setup(
                    ticker=ticker,
                    strategy=self.name,
                    direction="long",
                    entry=round(entry, 2),
                    stop=round(stop, 2),
                    exit_rule=f"RSI2 > {p['rsi_exit']} OR Close > SMA5",
                    atr=round(float(last["ATR"]), 2),
                    score=score,
                    reason=f"RSI(2)={last['RSI2']:.1f} < {p['rsi_entry']}, above SMA200 (Connors + Rayner trend filter)",
                    suggested_shares=size,
                    risk_amount=round(equity * p["capital_pct"], 2),
                    capital_pct=p["capital_pct"],
                )
            ]
        return []
