"""
Market Structure helpers inspired by Rayner Teo.
- Swing highs / lows
- Higher Highs + Higher Lows (uptrend structure)
- Lower Highs + Lower Lows (downtrend structure)
- Break of Structure (BOS)
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Dict
import numpy as np
import pandas as pd


def find_swing_points(
    high: pd.Series,
    low: pd.Series,
    left: int = 2,
    right: int = 2,
) -> Tuple[pd.Series, pd.Series]:
    """
    Simple fractal / pivot swing detection.
    Swing high: high[i] is max of window [i-left, i+right]
    Swing low:  low[i] is min of window [i-left, i+right]
    Returns boolean Series for swing highs and swing lows.
    """
    n = len(high)
    sh = pd.Series(False, index=high.index)
    sl = pd.Series(False, index=low.index)

    for i in range(left, n - right):
        window_h = high.iloc[i - left : i + right + 1]
        window_l = low.iloc[i - left : i + right + 1]
        if high.iloc[i] >= window_h.max():
            sh.iloc[i] = True
        if low.iloc[i] <= window_l.min():
            sl.iloc[i] = True
    return sh, sl


def get_recent_swings(
    df: pd.DataFrame,
    left: int = 2,
    right: int = 2,
    max_points: int = 8,
) -> Dict[str, List[Tuple[pd.Timestamp, float]]]:
    """
    Return lists of recent swing highs and swing lows as (timestamp, price).
    Most recent last.
    """
    sh_mask, sl_mask = find_swing_points(df["High"], df["Low"], left, right)
    highs = [
        (idx, float(df.loc[idx, "High"]))
        for idx in df.index[sh_mask]
    ][-max_points:]
    lows = [
        (idx, float(df.loc[idx, "Low"]))
        for idx in df.index[sl_mask]
    ][-max_points:]
    return {"highs": highs, "lows": lows}


def structure_bias(
    swings: Dict[str, List[Tuple]],
    min_swings: int = 2,
) -> str:
    """
    Determine structure bias from last swings.
    Returns: "up", "down", or "range"
    Rules (Rayner-style):
      up   = last 2+ swing highs rising AND last 2+ swing lows rising
      down = last 2+ swing highs falling AND last 2+ swing lows falling
    """
    highs = swings.get("highs") or []
    lows = swings.get("lows") or []
    if len(highs) < min_swings or len(lows) < min_swings:
        return "range"

    h_prices = [p for _, p in highs[-min_swings:]]
    l_prices = [p for _, p in lows[-min_swings:]]

    hh = all(h_prices[i] < h_prices[i + 1] for i in range(len(h_prices) - 1))
    hl = all(l_prices[i] < l_prices[i + 1] for i in range(len(l_prices) - 1))
    lh = all(h_prices[i] > h_prices[i + 1] for i in range(len(h_prices) - 1))
    ll = all(l_prices[i] > l_prices[i + 1] for i in range(len(l_prices) - 1))

    if hh and hl:
        return "up"
    if lh and ll:
        return "down"
    return "range"


def detect_bos(
    df: pd.DataFrame,
    direction: str = "long",
    left: int = 2,
    right: int = 2,
    lookback: int = 30,
) -> Optional[Dict]:
    """
    Detect recent Break of Structure on the given dataframe (usually Daily).

    Long BOS (Rayner):
      - Formed series of HH + HL
      - Then price breaks above the most recent swing high after a pullback

    Short BOS:
      - Formed series of LH + LL
      - Then price breaks below the most recent swing low

    Returns dict with keys: bos (bool), entry, stop, swing_high, swing_low, reason
    or None if no clear BOS.
    """
    if len(df) < lookback + 10:
        return None

    recent = df.iloc[-lookback:].copy()
    swings = get_recent_swings(recent, left=left, right=right, max_points=6)
    bias = structure_bias(swings, min_swings=2)

    highs = swings["highs"]
    lows = swings["lows"]
    if not highs or not lows:
        return None

    last_close = float(df["Close"].iloc[-1])
    last_high = float(df["High"].iloc[-1])
    last_low = float(df["Low"].iloc[-1])

    if direction == "long":
        # Need bullish structure developing or just broken higher
        if bias not in ("up", "range"):
            # still allow if we just broke a clear prior high
            pass

        # Most recent significant swing high
        swing_high_price = highs[-1][1]
        swing_low_price = lows[-1][1]

        # BOS long: close (or high) broke above prior swing high
        # and we have at least one higher low before that
        if last_close > swing_high_price or last_high > swing_high_price:
            # Confirm we had a pullback structure (at least 2 lows)
            if len(lows) >= 2:
                entry = max(last_close, swing_high_price)
                stop = swing_low_price * 0.995  # small buffer under structure low
                return {
                    "bos": True,
                    "direction": "long",
                    "entry": round(entry, 4),
                    "stop": round(stop, 4),
                    "swing_high": swing_high_price,
                    "swing_low": swing_low_price,
                    "bias": bias,
                    "reason": (
                        f"пробой максимума {swing_high_price:.2f}, "
                        f"структурный минимум {swing_low_price:.2f}, "
                        f"локальный уклон: {'рост' if bias=='up' else 'снижение' if bias=='down' else 'боковик'}"
                    ),
                }

    elif direction == "short":
        swing_high_price = highs[-1][1]
        swing_low_price = lows[-1][1]

        if last_close < swing_low_price or last_low < swing_low_price:
            if len(highs) >= 2:
                entry = min(last_close, swing_low_price)
                stop = swing_high_price * 1.005
                return {
                    "bos": True,
                    "direction": "short",
                    "entry": round(entry, 4),
                    "stop": round(stop, 4),
                    "swing_high": swing_high_price,
                    "swing_low": swing_low_price,
                    "bias": bias,
                    "reason": (
                        f"пробой минимума {swing_low_price:.2f}, "
                        f"структурный максимум {swing_high_price:.2f}, "
                        f"локальный уклон: {'рост' if bias=='up' else 'снижение' if bias=='down' else 'боковик'}"
                    ),
                }

    return None


def is_near_area_of_value(
    df: pd.DataFrame,
    kind: str = "support",
    lookback: int = 60,
    tolerance_pct: float = 0.03,
) -> bool:
    """
    Rough check: is current price near a recent swing low (support)
    or swing high (resistance)?
    """
    if len(df) < 20:
        return False
    recent = df.iloc[-lookback:]
    swings = get_recent_swings(recent, left=3, right=3, max_points=5)
    price = float(df["Close"].iloc[-1])

    if kind == "support":
        levels = [p for _, p in swings["lows"]]
        if not levels:
            # fallback: recent lowest low
            levels = [float(recent["Low"].min())]
        return any(abs(price - lvl) / lvl <= tolerance_pct for lvl in levels)

    if kind == "resistance":
        levels = [p for _, p in swings["highs"]]
        if not levels:
            levels = [float(recent["High"].max())]
        return any(abs(price - lvl) / lvl <= tolerance_pct for lvl in levels)

    return False


def weekly_trend_filter(weekly_df: pd.DataFrame) -> str:
    """
    Simple weekly bias used as higher-timeframe filter.
    Rayner often uses 200 SMA; on weekly we use SMA(40) ≈ 200 daily bars.
    Also checks structure bias.
    """
    if weekly_df is None or len(weekly_df) < 45:
        return "unknown"

    close = weekly_df["Close"]
    sma40 = close.rolling(40).mean()
    last = float(close.iloc[-1])
    last_sma = float(sma40.iloc[-1]) if not np.isnan(sma40.iloc[-1]) else last

    swings = get_recent_swings(weekly_df.iloc[-40:], left=1, right=1, max_points=4)
    bias = structure_bias(swings, min_swings=2)

    if last > last_sma and bias != "down":
        return "up"
    if last < last_sma and bias != "up":
        return "down"
    return "range"
