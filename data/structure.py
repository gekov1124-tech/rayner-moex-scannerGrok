"""
Market Structure helpers inspired by Rayner Teo.
- Swing highs / lows
- Higher Highs + Higher Lows (uptrend structure)
- Lower Highs + Lower Lows (downtrend structure)
- Break of Structure (BOS)
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any
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


def compute_area_of_value(
    df: pd.DataFrame,
    lookback: int = 80,
    tolerance_pct: float = 0.015,
) -> Dict[str, Any]:
    """
    Rayner-style Area of Value for charting.
    Returns support/resistance swing levels, MA zone, and a primary band.
    """
    from utils.indicators import sma, ema

    empty = {
        "support_levels": [],
        "resistance_levels": [],
        "ema20": None,
        "ema50": None,
        "sma200": None,
        "zone_low": None,
        "zone_high": None,
        "zone_label": "",
        "levels": [],  # for chart lines: {price, title, color, style}
    }
    if df is None or len(df) < 30:
        return empty

    recent = df.iloc[-lookback:] if len(df) >= lookback else df
    price = float(df["Close"].iloc[-1])
    swings = get_recent_swings(recent, left=3, right=3, max_points=6)

    supports = sorted({round(float(p), 4) for _, p in swings.get("lows", [])}, reverse=True)
    resistances = sorted({round(float(p), 4) for _, p in swings.get("highs", [])})

    # Keep levels near price (±12%)
    def near(levels, pct=0.12):
        out = []
        for lv in levels:
            if price > 0 and abs(lv - price) / price <= pct:
                out.append(lv)
        return out[:4]

    supports = near(supports)
    resistances = near(resistances)

    e20 = e50 = s200 = None
    try:
        e20 = float(ema(df["Close"], 20).iloc[-1])
        e50 = float(ema(df["Close"], 50).iloc[-1])
        if len(df) >= 200:
            s200 = float(sma(df["Close"], 200).iloc[-1])
        elif len(df) >= 50:
            s200 = float(sma(df["Close"], min(200, len(df) - 1)).iloc[-1])
    except Exception:
        pass

    # Primary zone: nearest support cluster or EMA band
    zone_low = zone_high = None
    zone_label = ""
    if supports:
        # band around nearest support below or near price
        below = [s for s in supports if s <= price * 1.01]
        ref = below[0] if below else supports[0]
        zone_low = round(ref * (1 - tolerance_pct), 4)
        zone_high = round(ref * (1 + tolerance_pct), 4)
        zone_label = f"Поддержка (свинг) ≈ {ref}"
    elif e20 is not None and e50 is not None:
        zone_low = round(min(e20, e50), 4)
        zone_high = round(max(e20, e50), 4)
        zone_label = "Зона EMA20–EMA50"
    elif e50 is not None:
        zone_low = round(e50 * (1 - tolerance_pct), 4)
        zone_high = round(e50 * (1 + tolerance_pct), 4)
        zone_label = f"EMA50 ≈ {round(e50, 4)}"

    # If price is closer to resistance, prefer resistance zone (for shorts / context)
    if resistances:
        above = [r for r in resistances if r >= price * 0.99]
        if above:
            ref_r = above[0]
            # only override if clearly nearer to resistance than support
            dist_r = abs(ref_r - price)
            dist_s = abs((supports[0] if supports else ref_r) - price) if supports else dist_r * 2
            if dist_r < dist_s * 0.85:
                zone_low = round(ref_r * (1 - tolerance_pct), 4)
                zone_high = round(ref_r * (1 + tolerance_pct), 4)
                zone_label = f"Сопротивление (свинг) ≈ {ref_r}"

    levels = []
    if zone_low is not None and zone_high is not None:
        levels.append({"price": zone_low, "title": "AoV↓", "color": "#22c55e", "style": 2})
        levels.append({"price": zone_high, "title": "AoV↑", "color": "#22c55e", "style": 2})
    for s in supports[:3]:
        levels.append({"price": s, "title": "Support", "color": "#4ade80", "style": 0})
    for r in resistances[:3]:
        levels.append({"price": r, "title": "Resist", "color": "#f87171", "style": 0})
    if e20 is not None:
        levels.append({"price": round(e20, 4), "title": "EMA20", "color": "#60a5fa", "style": 1})
    if e50 is not None:
        levels.append({"price": round(e50, 4), "title": "EMA50", "color": "#a78bfa", "style": 1})
    if s200 is not None:
        levels.append({"price": round(s200, 4), "title": "SMA200", "color": "#fbbf24", "style": 0})

    return {
        "support_levels": supports,
        "resistance_levels": resistances,
        "ema20": round(e20, 4) if e20 is not None else None,
        "ema50": round(e50, 4) if e50 is not None else None,
        "sma200": round(s200, 4) if s200 is not None else None,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "zone_label": zone_label,
        "levels": levels,
        "last_price": round(price, 4),
    }
