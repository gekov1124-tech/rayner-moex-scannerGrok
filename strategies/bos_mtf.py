"""
Rayner Teo – Break of Structure (Multi-Timeframe)

Classic rules (video "Break of Structure Trading Strategy" + Multiple Timeframe Secrets):

  HTF (Daily):
    - Market structure / trend (SMA200, swing bias)
    - Area of value (support / resistance)

  LTF (H4):
    - Wait for Break of Structure in direction of HTF
    - Long: HH+HL forming, then break above recent swing high
    - Short: LH+LL forming, then break below recent swing low
    - Tighter stop under/above H4 structure

Fallback: if H4 data is missing, BOS is evaluated on Daily
(with Weekly as HTF) so the scanner still works.
"""

from __future__ import annotations
from typing import List, Optional, Dict
import pandas as pd
import numpy as np

from strategies.base import Strategy, Setup, build_r_targets, format_targets_ru
from strategies.registry import register
from data.structure import (
    detect_bos,
    weekly_trend_filter,
    is_near_area_of_value,
    get_recent_swings,
    structure_bias,
)


def _resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) < 20:
        return pd.DataFrame()
    d = df.copy()
    if not isinstance(d.index, pd.DatetimeIndex):
        d.index = pd.to_datetime(d.index)
    ohlc = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return d.resample("W-FRI").agg(ohlc).dropna(subset=["Close"])


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if not np.isnan(atr) else float(high.iloc[-1] - low.iloc[-1])


def _daily_trend(df: pd.DataFrame) -> str:
    """Simple Daily HTF bias: above/below SMA200 + structure."""
    if df is None or len(df) < 210:
        return "unknown"
    close = df["Close"]
    sma = close.rolling(200).mean()
    last = float(close.iloc[-1])
    last_sma = float(sma.iloc[-1]) if not np.isnan(sma.iloc[-1]) else last
    swings = get_recent_swings(df.iloc[-60:], left=2, right=2, max_points=4)
    bias = structure_bias(swings, min_swings=2)
    if last > last_sma and bias != "down":
        return "up"
    if last < last_sma and bias != "up":
        return "down"
    return "range"


@register("Rayner_BOS_MTF")
class RaynerBOS_MTF(Strategy):
    """
    Multi-timeframe Break of Structure (Rayner Teo).
    Preferred: Daily HTF + H4 LTF.
    Fallback: Weekly HTF + Daily LTF.
    """

    def __init__(self, params: Optional[Dict] = None):
        super().__init__("Rayner_BOS_MTF", params)
        self.require_htf_up = self.params.get("require_htf_up", True)
        self.near_support_tol = self.params.get("near_support_tol", 0.04)
        self.risk_pct = self.params.get("risk_pct", 0.01)
        self.allow_short = self.params.get("allow_short", False)
        # Optional external H4 store injected by scanner: {ticker: h4_df}
        self.h4_data: Dict[str, pd.DataFrame] = self.params.get("h4_data") or {}

    def set_h4_data(self, h4_data: Dict[str, pd.DataFrame]):
        self.h4_data = h4_data or {}

    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        if df is None or len(df) < 120:
            return []

        h4 = self.h4_data.get(ticker)
        use_h4 = h4 is not None and len(h4) >= 30

        # ----- Higher timeframe bias -----
        if use_h4:
            # Classic Rayner pair: Daily = HTF, H4 = entry
            htf_bias = _daily_trend(df)
            htf_label = "daily"
            ltf_df = h4
            ltf_label = "H4"
        else:
            # Fallback: Weekly = HTF, Daily = entry
            weekly = _resample_weekly(df)
            htf_bias = weekly_trend_filter(weekly) if len(weekly) >= 40 else "unknown"
            htf_label = "weekly"
            ltf_df = df
            ltf_label = "daily"

        near_val = is_near_area_of_value(
            df, kind="support", tolerance_pct=self.near_support_tol
        )

        htf_ok = (
            (not self.require_htf_up)
            or htf_bias in ("up", "range", "unknown")
            or (htf_bias == "down" and near_val)
        )

        setups: List[Setup] = []

        # ----- LONG -----
        if htf_ok:
            bos = detect_bos(ltf_df, direction="long", left=2, right=2, lookback=50)
            if bos and bos.get("bos"):
                score = 12.0 if use_h4 else 10.0
                if htf_bias == "up":
                    score += 5
                elif htf_bias == "range":
                    score += 2
                if near_val:
                    score += 4
                if bos.get("bias") == "up":
                    score += 3
                if use_h4:
                    score += 2  # precision bonus for real H4

                entry = bos["entry"]
                stop = bos["stop"]
                # On H4 stops are tighter; ensure minimum distance
                risk_per_share = max(entry - stop, entry * 0.004)
                risk_amount = equity * self.risk_pct
                shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

                htf_ru = {"up": "восходящий", "down": "нисходящий", "range": "боковой"}.get(htf_bias, htf_bias)
                tf_ru = {"daily": "дневной", "weekly": "недельный", "H4": "H4", "1H": "H1"}.get(htf_label, htf_label)
                ltf_ru = {"H4": "H4", "daily": "дневной", "1H": "H1"}.get(ltf_label, ltf_label)
                zone = "цена у зоны поддержки" if near_val else "далеко от зоны поддержки"
                reason = (
                    f"Лонг по разрыву структуры (BOS): на старшем ТФ ({tf_ru}) тренд {htf_ru}; "
                    f"на младшем ТФ ({ltf_ru}) — {bos['reason']}; {zone}."
                )

                setups.append(
                    Setup(
                        ticker=ticker,
                        strategy=self.name,
                        direction="long",
                        entry=round(entry, 4),
                        stop=round(stop, 4),
                        exit_rule=(
                            "Трейл под растущими минимумами H4 / по структуре; или частичная фиксация на 2–3R"
                        ),
                        atr=_atr(df),
                        score=score,
                        reason=reason,
                        suggested_shares=shares,
                        risk_amount=round(risk_amount, 2),
                        targets=build_r_targets(entry, stop, "long", (1.0, 2.0, 3.0), (0.30, 0.30, 0.40)),
                        scale_plan=format_targets_ru(
                            build_r_targets(entry, stop, "long", (1.0, 2.0, 3.0), (0.30, 0.30, 0.40)),
                            "трейл под растущими минимумами H4",
                        ),
                    )
                )

        # ----- SHORT (optional) -----
        if self.allow_short and htf_bias in ("down", "range"):
            near_res = is_near_area_of_value(
                df, kind="resistance", tolerance_pct=self.near_support_tol
            )
            bos = detect_bos(ltf_df, direction="short", left=2, right=2, lookback=50)
            if bos and bos.get("bos"):
                score = 10.0 if use_h4 else 8.0
                if htf_bias == "down":
                    score += 5
                if near_res:
                    score += 4
                if use_h4:
                    score += 2

                entry = bos["entry"]
                stop = bos["stop"]
                risk_per_share = max(stop - entry, entry * 0.004)
                risk_amount = equity * self.risk_pct
                shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

                htf_ru = {"up": "восходящий", "down": "нисходящий", "range": "боковой"}.get(htf_bias, htf_bias)
                tf_ru = {"daily": "дневной", "weekly": "недельный", "H4": "H4", "1H": "H1"}.get(htf_label, htf_label)
                ltf_ru = {"H4": "H4", "daily": "дневной", "1H": "H1"}.get(ltf_label, ltf_label)
                zone = "цена у зоны сопротивления" if near_res else "далеко от зоны сопротивления"
                reason = (
                    f"Шорт по разрыву структуры (BOS): на старшем ТФ ({tf_ru}) тренд {htf_ru}; "
                    f"на младшем ТФ ({ltf_ru}) — {bos['reason']}; {zone}."
                )
                setups.append(
                    Setup(
                        ticker=ticker,
                        strategy=self.name,
                        direction="short",
                        entry=round(entry, 4),
                        stop=round(stop, 4),
                        exit_rule="Трейл над снижающимися максимумами H4 / по структуре",
                        atr=_atr(df),
                        score=score,
                        reason=reason,
                        suggested_shares=shares,
                        risk_amount=round(risk_amount, 2),
                        targets=build_r_targets(entry, stop, "short", (1.0, 2.0, 3.0), (0.30, 0.30, 0.40)),
                        scale_plan=format_targets_ru(
                            build_r_targets(entry, stop, "short", (1.0, 2.0, 3.0), (0.30, 0.30, 0.40)),
                            "трейл над снижающимися максимумами H4",
                        ),
                    )
                )

        return setups
