"""
Rayner Teo – False Break (ложный пробой).

Идея: цена прокалывает уровень поддержки/сопротивления,
затем быстро возвращается и закрывается обратно —
ловушка для breakout-трейдеров. Вход в сторону отторжения
от зоны ценности.
"""

from __future__ import annotations
from typing import List, Optional, Dict
import pandas as pd
import numpy as np

from strategies.base import Strategy, Setup, build_r_targets, format_targets_ru
from strategies.registry import register
from data.structure import get_recent_swings
from utils.indicators import sma, atr


@register("Rayner_FalseBreak")
class RaynerFalseBreak(Strategy):
    """
    False break at swing support (long) or resistance (short).
    Long only above SMA200 (Rayner trend filter).
    """

    def __init__(self, params: Optional[Dict] = None):
        default = {
            "sma_period": 200,
            "lookback": 40,
            "wick_pct": 0.004,      # min penetration beyond level
            "risk_pct": 0.01,
            "atr_period": 14,
            "allow_short": False,
        }
        super().__init__("Rayner_FalseBreak", {**default, **(params or {})})

    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        p = self.params
        if df is None or len(df) < p["sma_period"] + 30:
            return []

        df = df.copy()
        df["SMA200"] = sma(df["Close"], p["sma_period"])
        df["ATR"] = atr(df, p["atr_period"])
        last = df.iloc[-1]
        prev = df.iloc[-2]
        if pd.isna(last["SMA200"]) or pd.isna(last["ATR"]):
            return []

        swings = get_recent_swings(df.iloc[-p["lookback"]:], left=3, right=3, max_points=5)
        supports = [price for _, price in swings.get("lows", [])]
        resistances = [price for _, price in swings.get("highs", [])]
        if not supports:
            supports = [float(df["Low"].iloc[-p["lookback"]:].min())]

        atr_v = float(last["ATR"])
        setups: List[Setup] = []

        # ----- LONG false break of support (only in uptrend) -----
        if float(last["Close"]) > float(last["SMA200"]) and supports:
            lvl = min(supports, key=lambda x: abs(x - float(prev["Low"])))
            # prev candle wicked below support, closed back above
            penetrated = float(prev["Low"]) < lvl * (1 - p["wick_pct"])
            closed_back = float(prev["Close"]) > lvl
            bullish_now = float(last["Close"]) > float(last["Open"]) and float(last["Close"]) >= lvl
            if penetrated and closed_back and bullish_now:
                entry = float(last["Close"])
                stop = min(float(prev["Low"]), lvl) - 0.15 * atr_v
                risk = entry - stop
                if risk <= 0:
                    return setups
                risk_amount = equity * p["risk_pct"]
                shares = max(1, int(risk_amount / risk))
                targets = build_r_targets(entry, stop, "long", (1.0, 2.0, 3.0), (0.30, 0.30, 0.40))
                setups.append(
                    Setup(
                        ticker=ticker,
                        strategy=self.name,
                        direction="long",
                        entry=round(entry, 4),
                        stop=round(stop, 4),
                        exit_rule="Частичная фиксация 1R–3R; остаток трейл по структуре",
                        atr=round(atr_v, 4),
                        score=18.0,
                        reason=(
                            f"Ложный пробой поддержки ≈{lvl:.4f}: фитиль ниже уровня, "
                            f"закрытие обратно выше; тренд вверх (выше SMA200)."
                        ),
                        suggested_shares=shares,
                        risk_amount=round(risk_amount, 2),
                        targets=targets,
                        scale_plan=format_targets_ru(targets, "трейл по структуре"),
                    )
                )

        # ----- SHORT false break of resistance -----
        if p.get("allow_short") and float(last["Close"]) < float(last["SMA200"]) and resistances:
            lvl = min(resistances, key=lambda x: abs(x - float(prev["High"])))
            penetrated = float(prev["High"]) > lvl * (1 + p["wick_pct"])
            closed_back = float(prev["Close"]) < lvl
            bearish_now = float(last["Close"]) < float(last["Open"]) and float(last["Close"]) <= lvl
            if penetrated and closed_back and bearish_now:
                entry = float(last["Close"])
                stop = max(float(prev["High"]), lvl) + 0.15 * atr_v
                risk = stop - entry
                if risk <= 0:
                    return setups
                risk_amount = equity * p["risk_pct"]
                shares = max(1, int(risk_amount / risk))
                targets = build_r_targets(entry, stop, "short", (1.0, 2.0, 3.0), (0.30, 0.30, 0.40))
                setups.append(
                    Setup(
                        ticker=ticker,
                        strategy=self.name,
                        direction="short",
                        entry=round(entry, 4),
                        stop=round(stop, 4),
                        exit_rule="Частичная фиксация 1R–3R; остаток трейл по структуре",
                        atr=round(atr_v, 4),
                        score=18.0,
                        reason=(
                            f"Ложный пробой сопротивления ≈{lvl:.4f}: фитиль выше уровня, "
                            f"закрытие обратно ниже; тренд вниз (ниже SMA200)."
                        ),
                        suggested_shares=shares,
                        risk_amount=round(risk_amount, 2),
                        targets=targets,
                        scale_plan=format_targets_ru(targets, "трейл по структуре"),
                    )
                )

        return setups
