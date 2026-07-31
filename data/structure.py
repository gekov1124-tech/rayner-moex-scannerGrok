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
    lookback: int = 80,
    tolerance_pct: float = 0.03,
) -> bool:
    """
    Near Area of Value using quality-ranked levels (touches, flip, rounds).
    Falls back to raw swings if compute fails.
    """
    if df is None or len(df) < 20:
        return False
    price = float(df["Close"].iloc[-1])
    try:
        aov = compute_area_of_value(df, lookback=lookback, tolerance_pct=min(tolerance_pct, 0.02))
        if kind == "support":
            levels = list(aov.get("support_levels") or [])
            if aov.get("zone_low") and aov.get("zone_high"):
                # zone itself counts as support-ish if price inside/near
                if aov["zone_low"] <= price <= aov["zone_high"] * 1.01:
                    return True
                levels.append(aov["zone_low"])
                levels.append(aov["zone_high"])
        else:
            levels = list(aov.get("resistance_levels") or [])
            if aov.get("zone_low") and aov.get("zone_high"):
                if aov["zone_low"] * 0.99 <= price <= aov["zone_high"]:
                    return True
                levels.append(aov["zone_low"])
                levels.append(aov["zone_high"])
        if levels:
            return any(abs(price - float(lvl)) / max(float(lvl), 1e-9) <= tolerance_pct for lvl in levels)
    except Exception:
        pass
    # fallback raw swings
    recent = df.iloc[-lookback:]
    swings = get_recent_swings(recent, left=3, right=3, max_points=5)
    if kind == "support":
        levels = [p for _, p in swings["lows"]] or [float(recent["Low"].min())]
    else:
        levels = [p for _, p in swings["highs"]] or [float(recent["High"].max())]
    return any(abs(price - lvl) / max(lvl, 1e-9) <= tolerance_pct for lvl in levels)


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



def _cluster_levels(prices: list, tol_pct: float = 0.012) -> list:
    """Merge nearby prices into clusters; return [{price, touches, strength}]."""
    if not prices:
        return []
    prices = sorted(float(p) for p in prices)
    clusters = []
    cur = [prices[0]]
    for p in prices[1:]:
        ref = sum(cur) / len(cur)
        if abs(p - ref) / max(ref, 1e-9) <= tol_pct:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    out = []
    for c in clusters:
        mid = sum(c) / len(c)
        touches = len(c)
        out.append({"price": round(mid, 4), "touches": touches, "strength": touches})
    return out


def _count_touches(df: pd.DataFrame, level: float, tol_pct: float = 0.01) -> int:
    """How many bars wicked/closed near the level."""
    if df is None or len(df) < 5 or level <= 0:
        return 0
    hi = df["High"].astype(float)
    lo = df["Low"].astype(float)
    band = level * tol_pct
    near = ((hi >= level - band) & (lo <= level + band))
    return int(near.sum())


def _round_numbers_near(price: float, n: int = 4) -> list:
    """Psychological round levels near current price."""
    if price <= 0:
        return []
    # step scales with price magnitude
    if price >= 5000:
        step = 500
    elif price >= 1000:
        step = 100
    elif price >= 200:
        step = 50
    elif price >= 50:
        step = 10
    elif price >= 10:
        step = 5
    else:
        step = 1
    base = round(price / step) * step
    cands = []
    for k in range(-3, 4):
        lv = base + k * step
        if lv > 0 and abs(lv - price) / price <= 0.12:
            cands.append(round(float(lv), 4))
    # also half-steps for major
    half = step / 2
    if half >= 1:
        base_h = round(price / half) * half
        for k in range(-2, 3):
            lv = base_h + k * half
            if lv > 0 and abs(lv - price) / price <= 0.10:
                cands.append(round(float(lv), 4))
    return sorted(set(cands))


def _apply_sr_flip(
    supports: list,
    resistances: list,
    price: float,
) -> tuple:
    """
    Role reversal: broken resistance becomes support, broken support becomes resistance.
    supports/resistances are lists of dicts with price/touches/strength.
    """
    flipped_sup = []
    flipped_res = []
    # Resistance clearly broken (price well above) → support
    for r in resistances:
        if price > r["price"] * 1.008:
            flipped_sup.append({
                **r,
                "price": r["price"],
                "strength": r.get("strength", 1) + 1,  # flip bonus
                "flipped": True,
                "role": "support",
            })
        else:
            flipped_res.append({**r, "role": "resistance", "flipped": False})
    # Support clearly broken (price well below) → resistance
    for s in supports:
        if price < s["price"] * 0.992:
            flipped_res.append({
                **s,
                "price": s["price"],
                "strength": s.get("strength", 1) + 1,
                "flipped": True,
                "role": "resistance",
            })
        else:
            flipped_sup.append({**s, "role": "support", "flipped": False})
    # de-dupe by price proximity
    def dedupe(items):
        items = sorted(items, key=lambda x: -x.get("strength", 1))
        out = []
        for it in items:
            if any(abs(it["price"] - o["price"]) / max(o["price"], 1e-9) < 0.008 for o in out):
                # keep stronger
                continue
            out.append(it)
        return out
    return dedupe(flipped_sup), dedupe(flipped_res)


def compute_area_of_value(
    df: pd.DataFrame,
    lookback: int = 100,
    tolerance_pct: float = 0.015,
) -> Dict[str, Any]:
    """
    Rayner-style Area of Value with quality scoring:
      - swing clusters + touch count
      - S/R role flip after breakout
      - round-number levels
      - clean chart: top-2 S/R + AoV band + SMA200 (+ EMA50)
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
        "levels": [],
        "level_details": [],
    }
    if df is None or len(df) < 30:
        return empty

    recent = df.iloc[-lookback:] if len(df) >= lookback else df
    price = float(df["Close"].iloc[-1])
    swings = get_recent_swings(recent, left=3, right=3, max_points=10)

    raw_lows = [p for _, p in swings.get("lows", [])]
    raw_highs = [p for _, p in swings.get("highs", [])]

    # Cluster nearby swings
    sup_clusters = _cluster_levels(raw_lows, tol_pct=0.012)
    res_clusters = _cluster_levels(raw_highs, tol_pct=0.012)

    # Enrich with actual touch counts on recent bars
    for c in sup_clusters:
        t = _count_touches(recent, c["price"], tol_pct=0.012)
        c["touches"] = max(c["touches"], t)
        c["strength"] = c["touches"]
    for c in res_clusters:
        t = _count_touches(recent, c["price"], tol_pct=0.012)
        c["touches"] = max(c["touches"], t)
        c["strength"] = c["touches"]

    # S/R flip
    supports, resistances = _apply_sr_flip(sup_clusters, res_clusters, price)

    # Round numbers as weak-but-real levels
    for rn in _round_numbers_near(price):
        t = _count_touches(recent, rn, tol_pct=0.008)
        strength = 1 + min(t, 3)
        if rn < price * 0.998:
            supports.append({
                "price": rn, "touches": t, "strength": strength,
                "role": "support", "flipped": False, "round": True,
            })
        elif rn > price * 1.002:
            resistances.append({
                "price": rn, "touches": t, "strength": strength,
                "role": "resistance", "flipped": False, "round": True,
            })

    # Keep levels near price, sort by strength
    def near_filter(items, pct=0.14):
        out = []
        for it in items:
            lv = it["price"]
            if price > 0 and abs(lv - price) / price <= pct:
                out.append(it)
        out.sort(key=lambda x: (-x.get("strength", 1), abs(x["price"] - price)))
        return out

    supports = near_filter(supports)[:5]
    resistances = near_filter(resistances)[:5]

    # MAs
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


    # Primary AoV: ONE zone nearest to price (Rayner: trade the area in play)
    zone_low = zone_high = None
    zone_label = ""
    best_sup = None
    for s in supports:
        if s["price"] <= price * 1.02:
            best_sup = s
            break
    best_res = None
    for r in resistances:
        if r["price"] >= price * 0.98:
            best_res = r
            break

    use_sup = False
    if best_sup and best_res:
        dist_s = abs(price - best_sup["price"])
        dist_r = abs(price - best_res["price"])
        # prefer the closer side; ties → support in uptrend-ish (price > ema50)
        if dist_s <= dist_r * 1.05:
            use_sup = True
        elif e50 is not None and price >= e50:
            use_sup = True
    elif best_sup:
        use_sup = True

    if use_sup and best_sup:
        ref = best_sup["price"]
        zone_low = round(ref * (1 - tolerance_pct), 4)
        zone_high = round(ref * (1 + tolerance_pct), 4)
        tag = "перевёрнутая S/R" if best_sup.get("flipped") else (
            "круглое число" if best_sup.get("round") else "свинг"
        )
        zone_label = f"Поддержка ({tag}) ≈ {ref} · касаний {best_sup.get('touches', 1)}"
    elif best_res:
        ref = best_res["price"]
        zone_low = round(ref * (1 - tolerance_pct), 4)
        zone_high = round(ref * (1 + tolerance_pct), 4)
        tag = "перевёрнутая S/R" if best_res.get("flipped") else (
            "круглое число" if best_res.get("round") else "свинг"
        )
        zone_label = f"Сопротивление ({tag}) ≈ {ref} · касаний {best_res.get('touches', 1)}"
    elif e20 is not None and e50 is not None:
        zone_low = round(min(e20, e50), 4)
        zone_high = round(max(e20, e50), 4)
        zone_label = "Зона EMA20–EMA50"
    elif e50 is not None:
        zone_low = round(e50 * (1 - tolerance_pct), 4)
        zone_high = round(e50 * (1 + tolerance_pct), 4)
        zone_label = f"EMA50 ≈ {round(e50, 4)}"

    # ---- Clean chart: ONE AoV band + top-1 S + top-1 R + SMA200 + EMA50 ----
    levels = []
    if zone_low is not None and zone_high is not None:
        levels.append({"price": zone_low, "title": "AoV низ", "color": "#22c55e", "style": 0, "key": True})
        levels.append({"price": zone_high, "title": "AoV верх", "color": "#22c55e", "style": 0, "key": True})
        levels.append({
            "price": round((zone_low + zone_high) / 2, 4),
            "title": "Зона ценности",
            "color": "rgba(34,197,94,0.4)",
            "style": 0,
            "key": True,
        })

    # top-1 support not overlapping AoV
    for s in supports[:2]:
        if zone_low and abs(s["price"] - (zone_low + zone_high) / 2) / max(s["price"], 1e-9) < 0.012:
            continue  # same as AoV
        title = "Support★" if s.get("strength", 1) >= 3 else "Support"
        if s.get("flipped"):
            title = "Support(flip)"
        if s.get("round"):
            title = "Support(круг)"
        levels.append({
            "price": s["price"], "title": title, "color": "#4ade80",
            "style": 0, "key": True, "strength": s.get("strength", 1),
        })
        break  # only top-1 extra support

    for r in resistances[:2]:
        if zone_high and abs(r["price"] - (zone_low + zone_high) / 2) / max(r["price"], 1e-9) < 0.012:
            continue
        title = "Resist★" if r.get("strength", 1) >= 3 else "Resist"
        if r.get("flipped"):
            title = "Resist(flip)"
        if r.get("round"):
            title = "Resist(круг)"
        levels.append({
            "price": r["price"], "title": title, "color": "#f87171",
            "style": 0, "key": True, "strength": r.get("strength", 1),
        })
        break  # only top-1 extra resist

    if s200 is not None:
        levels.append({"price": round(s200, 4), "title": "SMA200", "color": "#fbbf24", "style": 0, "key": True})
    if e50 is not None:
        levels.append({"price": round(e50, 4), "title": "EMA50", "color": "#a78bfa", "style": 1, "key": True})


    return {
        "support_levels": [s["price"] for s in supports[:3]],
        "resistance_levels": [r["price"] for r in resistances[:3]],
        "ema20": round(e20, 4) if e20 is not None else None,
        "ema50": round(e50, 4) if e50 is not None else None,
        "sma200": round(s200, 4) if s200 is not None else None,
        "zone_low": zone_low,
        "zone_high": zone_high,
        "zone_label": zone_label,
        "levels": levels,
        "level_details": {
            "supports": supports[:3],
            "resistances": resistances[:3],
        },
        "last_price": round(price, 4),
    }
