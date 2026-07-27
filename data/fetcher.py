"""OHLCV data fetcher with simple disk cache. Primary source: yfinance."""

from __future__ import annotations
from typing import Dict, List
from pathlib import Path
from datetime import datetime
import pickle
import yfinance as yf
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure standard OHLCV column names."""
    colmap = {c: c.title() for c in df.columns if isinstance(c, str)}
    df = df.rename(columns=colmap)
    # yfinance sometimes uses 'Adj Close'
    if "Adj Close" in df.columns and "Close" not in df.columns:
        df["Close"] = df["Adj Close"]
    needed = ["Open", "High", "Low", "Close", "Volume"]
    for col in needed:
        if col not in df.columns:
            raise ValueError(f"Missing column {col}")
    return df[needed].dropna(how="all")


def fetch_ohlcv(
    tickers: List[str],
    period: str = "2y",
    interval: str = "1d",
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Download daily OHLCV for a list of tickers.
    Returns dict[ticker] = DataFrame with Open/High/Low/Close/Volume.
    """
    if not tickers:
        return {}

    cache_key = f"ohlcv_{period}_{interval}_{datetime.now().strftime('%Y%m%d')}.pkl"
    cache_file = CACHE_DIR / cache_key

    if use_cache and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                cached = pickle.load(f)
            # Return only requested tickers that exist in cache
            return {t: cached[t] for t in tickers if t in cached}
        except Exception:
            pass

    data: Dict[str, pd.DataFrame] = {}

    # Prefer batch download
    try:
        raw = yf.download(
            tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True,
        )
        if len(tickers) == 1:
            t = tickers[0]
            sub = _normalize_columns(raw)
            if len(sub) > 200:
                data[t] = sub
        else:
            for t in tickers:
                try:
                    if t in raw.columns.get_level_values(0):
                        sub = raw[t].copy()
                        sub = _normalize_columns(sub)
                        if len(sub) > 200:
                            data[t] = sub
                except Exception:
                    continue
    except Exception as e:
        print(f"[fetcher] Batch download issue: {e}. Falling back to sequential.")

    # Sequential fallback for missing
    missing = [t for t in tickers if t not in data]
    for t in missing:
        try:
            hist = yf.Ticker(t).history(
                period=period, interval=interval, auto_adjust=True
            )
            if hist is not None and not hist.empty:
                hist = _normalize_columns(hist)
                if len(hist) > 200:
                    data[t] = hist
        except Exception:
            continue

    if use_cache and data:
        try:
            # Merge with existing cache if present
            existing = {}
            if cache_file.exists():
                with open(cache_file, "rb") as f:
                    existing = pickle.load(f)
            existing.update(data)
            with open(cache_file, "wb") as f:
                pickle.dump(existing, f)
        except Exception:
            pass

    return data
