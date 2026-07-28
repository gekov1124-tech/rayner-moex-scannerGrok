"""
Example additional strategy (compatible with Rayner Teo).
Copy & modify. Must have trend filter + objective rules + risk.
"""
from strategies.base import Strategy, Setup
from strategies.registry import register
from utils.indicators import sma, roc, atr
from typing import List
import pandas as pd

@register("ExampleROC_Momentum")
class ExampleROC_Momentum(Strategy):
    """Buy strong names above SMA200 with positive ROC. Simple momentum."""
    def __init__(self, params=None):
        default = {"sma_period": 200, "roc_period": 60, "min_roc": 5.0, "risk_pct": 0.01}
        super().__init__("ExampleROC_Momentum", {**default, **(params or {})})

    def generate_setups(self, ticker: str, df: pd.DataFrame, equity: float = 100_000) -> List[Setup]:
        p = self.params
        if len(df) < p["sma_period"] + 20:
            return []
        df = df.copy()
        df["SMA200"] = sma(df["Close"], p["sma_period"])
        df["ROC"] = roc(df["Close"], p["roc_period"])
        df["ATR"] = atr(df)
        last = df.iloc[-1]
        if (last["Close"] > last["SMA200"] and last["ROC"] > p["min_roc"]
                and not pd.isna(last["ATR"])):
            entry = float(last["Close"])
            stop = entry - 2.5 * float(last["ATR"])
            risk_amount = equity * p["risk_pct"]
            shares = max(1, int(risk_amount / (entry - stop))) if entry > stop else 0
            return [Setup(
                ticker=ticker, strategy=self.name, direction="long",
                entry=round(entry, 2), stop=round(stop, 2),
                exit_rule="Трейл по ATR или закрытие ниже SMA200",
                atr=round(float(last["ATR"]), 2), score=float(last["ROC"]),
                reason=f"Цена выше SMA200, ROC({p['roc_period']})={last['ROC']:.1f}% выше {p['min_roc']} — импульс вверх",
                suggested_shares=shares, risk_amount=round(risk_amount, 2),
                capital_pct=p["risk_pct"],
            )]
        return []
