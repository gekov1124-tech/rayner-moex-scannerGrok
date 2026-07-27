"""
Data fetcher for Moscow Exchange (MOEX).
Primary: official MOEX ISS API (free, no key).
Optional: Finam export (finam-export) if installed.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timedelta
import pickle
import time
import requests
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

MOEX_ISS_BASE = "https://iss.moex.com/iss"


def _candles_from_iss(
    ticker: str,
    from_date: str,
    till_date: str,
    interval: int = 24,  # 24 = daily
    board: str = "TQBR",
) -> pd.DataFrame:
    """
    Fetch daily OHLCV from MOEX ISS.
    interval: 1=1m, 10=10m, 60=1h, 24=1d, 7=1w, 31=1M
    """
    url = (
        f"{MOEX_ISS_BASE}/engines/stock/markets/shares/boards/{board}/"
        f"securities/{ticker}/candles.json"
    )
    params = {
        "from": from_date,
        "till": till_date,
        "interval": interval,
        "iss.meta": "off",
    }
    all_rows = []
    start = 0
    while True:
        params["start"] = start
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            j = r.json()
        except Exception as e:
            print(f"[moex] Error {ticker}: {e}")
            break

        candles = j.get("candles", {})
        cols = candles.get("columns", [])
        data = candles.get("data", [])
        if not data:
            break

        for row in data:
            all_rows.append(dict(zip(cols, row)))

        if len(data) < 500:  # typical page size
            break
        start += len(data)
        time.sleep(0.15)  # be polite

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    # Standardize columns
    rename = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "begin": "Date",
        "end": "End",
        "value": "Value",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
    needed = ["Open", "High", "Low", "Close", "Volume"]
    for c in needed:
        if c not in df.columns:
            return pd.DataFrame()
    return df[needed].astype(float).dropna(how="all")


def fetch_moex_ohlcv(
    tickers: List[str],
    lookback_days: int = 500,
    use_cache: bool = True,
    board: str = "TQBR",
) -> Dict[str, pd.DataFrame]:
    """
    Download daily OHLCV for MOEX tickers via ISS.
    """
    till = datetime.now().strftime("%Y-%m-%d")
    frm = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    cache_key = f"moex_ohlcv_{lookback_days}_{datetime.now().strftime('%Y%m%d')}.pkl"
    cache_file = CACHE_DIR / cache_key

    if use_cache and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                cached = pickle.load(f)
            return {t: cached[t] for t in tickers if t in cached}
        except Exception:
            pass

    data: Dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers):
        df = _candles_from_iss(t, frm, till, interval=24, board=board)
        if not df.empty and len(df) > 150:
            data[t] = df
        if (i + 1) % 10 == 0:
            print(f"  [moex] loaded {i+1}/{len(tickers)}")
        time.sleep(0.12)

    if use_cache and data:
        try:
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


def fetch_finam_ohlcv(
    tickers: List[str],
    lookback_days: int = 500,
) -> Dict[str, pd.DataFrame]:
    """
    Optional Finam export (requires finam-export package).
    Falls back gracefully if not installed or fails.
    """
    try:
        from finam import Exporter, Market
    except ImportError:
        print("[finam] finam-export not installed, skip")
        return {}

    exporter = Exporter()
    data = {}
    end = datetime.now()
    start = end - timedelta(days=lookback_days)

    for t in tickers:
        try:
            # Lookup MOEX shares
            res = exporter.lookup(code=t, market=Market.SHARES)
            if res is None or len(res) == 0:
                continue
            # Take first match
            idx = res.index[0]
            df = exporter.download(
                idx,
                market=Market.SHARES,
                start_date=start,
                end_date=end,
                timeframe=Exporter.Timeframe.DAILY,
            )
            if df is not None and not df.empty:
                # Normalize columns from finam format
                colmap = {
                    "<OPEN>": "Open",
                    "<HIGH>": "High",
                    "<LOW>": "Low",
                    "<CLOSE>": "Close",
                    "<VOL>": "Volume",
                    "OPEN": "Open",
                    "HIGH": "High",
                    "LOW": "Low",
                    "CLOSE": "Close",
                    "VOL": "Volume",
                    "Volume": "Volume",
                }
                df = df.rename(columns={k: v for k, v in colmap.items() if k in df.columns})
                if "Open" in df.columns:
                    data[t] = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        except Exception as e:
            print(f"[finam] {t}: {e}")
            continue
    return data


def fetch_ohlcv(
    tickers: List[str],
    source: str = "moex",
    lookback_days: int = 500,
    use_cache: bool = True,
) -> Dict[str, pd.DataFrame]:
    """
    Unified entry point.
    source: "moex" (default, free ISS) or "finam"
    """
    source = (source or "moex").lower()
    if source == "finam":
        data = fetch_finam_ohlcv(tickers, lookback_days)
        if data:
            return data
        print("[fetcher] Finam failed/empty → fallback to MOEX ISS")
    return fetch_moex_ohlcv(tickers, lookback_days=lookback_days, use_cache=use_cache)

def fetch_weekly(
    tickers: list,
    years: float = 5.0,
    board: str = "TQBR",
) -> Dict[str, pd.DataFrame]:
    """Fetch weekly candles (interval=7) for higher-timeframe analysis."""
    till = datetime.now().strftime("%Y-%m-%d")
    frm = (datetime.now() - timedelta(days=int(years * 365))).strftime("%Y-%m-%d")
    out: Dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers, 1):
        df = _candles_from_iss(t, frm, till, interval=7, board=board)
        if df is not None and len(df) >= 30:
            out[t] = df
        if i % 10 == 0:
            print(f"  [moex-w] loaded {i}/{len(tickers)}")
            time.sleep(0.3)
    return out



def _resample_h4(hourly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1H bars into 4-hour bars (MOEX session-aware enough for structure)."""
    if hourly is None or hourly.empty:
        return pd.DataFrame()
    d = hourly.copy()
    if not isinstance(d.index, pd.DatetimeIndex):
        d.index = pd.to_datetime(d.index)
    ohlc = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    h4 = d.resample("4h").agg(ohlc).dropna(subset=["Close"])
    return h4


def fetch_h4(
    tickers: List[str],
    lookback_days: int = 90,
    use_cache: bool = True,
    board: str = "TQBR",
) -> Dict[str, pd.DataFrame]:
    """
    Fetch H4 candles for Rayner-style lower timeframe (Break of Structure).
    MOEX ISS has no native 4H → download 1H (interval=60) and resample to 4H.
    """
    till = datetime.now().strftime("%Y-%m-%d")
    frm = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    cache_key = f"moex_h4_{lookback_days}_{datetime.now().strftime('%Y%m%d')}.pkl"
    cache_file = CACHE_DIR / cache_key

    if use_cache and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                cached = pickle.load(f)
            hit = {t: cached[t] for t in tickers if t in cached}
            if len(hit) == len(tickers):
                return hit
        except Exception:
            pass

    out: Dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers, 1):
        hourly = _candles_from_iss(t, frm, till, interval=60, board=board)
        if hourly is not None and not hourly.empty and len(hourly) >= 40:
            h4 = _resample_h4(hourly)
            if len(h4) >= 20:
                out[t] = h4
        if i % 5 == 0:
            print(f"  [moex-h4] loaded {i}/{len(tickers)}")
            time.sleep(0.25)
        else:
            time.sleep(0.12)

    if use_cache and out:
        try:
            existing = {}
            if cache_file.exists():
                with open(cache_file, "rb") as f:
                    existing = pickle.load(f)
            existing.update(out)
            with open(cache_file, "wb") as f:
                pickle.dump(existing, f)
        except Exception:
            pass

    return out
