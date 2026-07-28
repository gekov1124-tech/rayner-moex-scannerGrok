"""Feature engineering for Setup + OHLCV context."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from strategies.base import Setup
from utils.indicators import sma, ema, rsi, atr, roc, distance_to_ma

STRATEGY_IDS = {
    "RaynerBB_MeanRev": 0,
    "ConnorsRSI2": 1,
    "EMA_Pullback": 2,
    "TrendBreakout_200High": 3,
    "Donchian20": 4,
    "Rayner_BOS_MTF": 5,
}

FEATURE_NAMES = [
    "strategy_id",
    "direction_long",
    "entry",
    "stop_dist_pct",
    "atr_pct",
    "rule_score",
    "news_score",
    "rsi2",
    "rsi14",
    "dist_sma200",
    "dist_ema20",
    "roc20",
    "roc60",
    "vol_ratio",
    "range_pct",
]


def _safe(v, default=0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def context_features(df: Optional[pd.DataFrame]) -> Dict[str, float]:
    out = {
        "rsi2": 50.0,
        "rsi14": 50.0,
        "dist_sma200": 0.0,
        "dist_ema20": 0.0,
        "roc20": 0.0,
        "roc60": 0.0,
        "vol_ratio": 1.0,
        "range_pct": 0.0,
        "atr_pct": 0.0,
    }
    if df is None or len(df) < 60:
        return out
    try:
        c = df["Close"]
        last = float(c.iloc[-1])
        out["rsi2"] = _safe(rsi(c, 2).iloc[-1], 50)
        out["rsi14"] = _safe(rsi(c, 14).iloc[-1], 50)
        s200 = sma(c, min(200, len(c) - 1))
        e20 = ema(c, 20)
        out["dist_sma200"] = _safe(distance_to_ma(c, s200).iloc[-1], 0)
        out["dist_ema20"] = _safe(distance_to_ma(c, e20).iloc[-1], 0)
        out["roc20"] = _safe(roc(c, 20).iloc[-1], 0)
        out["roc60"] = _safe(roc(c, 60).iloc[-1], 0)
        a = atr(df, 14).iloc[-1]
        out["atr_pct"] = _safe(100.0 * float(a) / last if last else 0, 0)
        vol = df["Volume"]
        vma = vol.rolling(20).mean().iloc[-1]
        out["vol_ratio"] = _safe(float(vol.iloc[-1]) / float(vma) if vma else 1.0, 1.0)
        out["range_pct"] = _safe(
            100.0 * (float(df["High"].iloc[-1]) - float(df["Low"].iloc[-1])) / last if last else 0,
            0,
        )
    except Exception:
        pass
    return out


def setup_to_features(
    setup: Setup,
    df: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    ctx = context_features(df)
    entry = _safe(setup.entry, 1.0) or 1.0
    stop = _safe(setup.stop, entry)
    stop_dist = abs(entry - stop) / entry * 100.0
    atr_pct = _safe(setup.atr, 0) / entry * 100.0 if entry else ctx["atr_pct"]
    if atr_pct == 0:
        atr_pct = ctx["atr_pct"]
    return {
        "strategy_id": float(STRATEGY_IDS.get(setup.strategy, 9)),
        "direction_long": 1.0 if setup.direction == "long" else 0.0,
        "entry": entry,
        "stop_dist_pct": stop_dist,
        "atr_pct": atr_pct,
        "rule_score": _safe(setup.score, 0),
        "news_score": _safe(setup.news_score, 0),
        "rsi2": ctx["rsi2"],
        "rsi14": ctx["rsi14"],
        "dist_sma200": ctx["dist_sma200"],
        "dist_ema20": ctx["dist_ema20"],
        "roc20": ctx["roc20"],
        "roc60": ctx["roc60"],
        "vol_ratio": ctx["vol_ratio"],
        "range_pct": ctx["range_pct"],
    }


def vectorize(feat: Dict[str, float]) -> np.ndarray:
    return np.array([feat[n] for n in FEATURE_NAMES], dtype=float)


def features_matrix(
    setups: List[Setup],
    data: Optional[Dict[str, pd.DataFrame]] = None,
) -> np.ndarray:
    rows = []
    for s in setups:
        df = (data or {}).get(s.ticker)
        rows.append(vectorize(setup_to_features(s, df)))
    if not rows:
        return np.zeros((0, len(FEATURE_NAMES)))
    return np.vstack(rows)
