"""
Data fetcher for Moscow Exchange (MOEX).
Shares (TQBR) + Futures (FORTS) via official ISS API.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set
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
    interval: int = 24,
    board: str = "TQBR",
    engine: str = "stock",
    market: str = "shares",
) -> pd.DataFrame:
    """
    Fetch OHLCV from MOEX ISS.
    interval: 1=1m, 10=10m, 60=1h, 24=1d, 7=1w, 31=1M
    engine/market: stock/shares or futures/forts
    """
    if engine == "futures":
        # FORTS path does not use board in the same way
        url = (
            f"{MOEX_ISS_BASE}/engines/futures/markets/forts/"
            f"securities/{ticker}/candles.json"
        )
    else:
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

        if len(data) < 500:
            break
        start += len(data)
        time.sleep(0.12)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
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


def _is_futures_ticker(ticker: str, futures_set: Optional[Set[str]] = None) -> bool:
    if futures_set and ticker in futures_set:
        return True
    try:
        from data.universe import classify_instrument
        return classify_instrument(ticker) == "futures"
    except Exception:
        import re
        return bool(re.match(r"^[A-Za-z]{1,5}[FGHJKMNQUVXZ]\d{1,2}$", ticker or ""))


def fetch_moex_ohlcv(
    tickers: List[str],
    lookback_days: int = 500,
    use_cache: bool = True,
    board: str = "TQBR",
    futures_tickers: Optional[Set[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Download daily OHLCV for MOEX shares and/or futures.
    """
    till = datetime.now().strftime("%Y-%m-%d")
    frm = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    cache_key = f"moex_ohlcv_{lookback_days}_{datetime.now().strftime('%Y%m%d')}.pkl"
    cache_file = CACHE_DIR / cache_key

    cached: Dict[str, pd.DataFrame] = {}
    if use_cache and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                cached = pickle.load(f)
        except Exception:
            cached = {}

    data: Dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers):
        if use_cache and t in cached and cached[t] is not None and len(cached[t]) > 50:
            data[t] = cached[t]
            continue

        is_fut = _is_futures_ticker(t, futures_tickers)
        if is_fut:
            df = _candles_from_iss(
                t, frm, till, interval=24, engine="futures", market="forts"
            )
            min_bars = 80  # front month may have shorter history
        else:
            df = _candles_from_iss(t, frm, till, interval=24, board=board)
            min_bars = 150

        if not df.empty and len(df) >= min_bars:
            data[t] = df
        elif not df.empty and is_fut and len(df) >= 40:
            # accept shorter futures history with warning
            print(f"  [moex] {t}: only {len(df)} bars (short front-month history)")
            data[t] = df

        if (i + 1) % 10 == 0:
            print(f"  [moex] loaded {i+1}/{len(tickers)}")
        time.sleep(0.12)

    if use_cache and data:
        try:
            cached.update(data)
            with open(cache_file, "wb") as f:
                pickle.dump(cached, f)
        except Exception:
            pass

    return data


def fetch_finam_ohlcv(
    tickers: List[str],
    lookback_days: int = 500,
) -> Dict[str, pd.DataFrame]:
    """Optional Finam export for shares only."""
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
        if _is_futures_ticker(t):
            continue
        try:
            res = exporter.lookup(code=t, market=Market.SHARES)
            if res is None or len(res) == 0:
                continue
            idx = res.index[0]
            df = exporter.download(
                idx,
                market=Market.SHARES,
                start_date=start,
                end_date=end,
                timeframe=Exporter.Timeframe.DAILY,
            )
            if df is not None and not df.empty:
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
    futures_tickers: Optional[Set[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Unified entry point for shares + futures.
    """
    source = (source or "moex").lower()
    fut_set = futures_tickers or {t for t in tickers if _is_futures_ticker(t)}
    if source == "finam":
        # Finam for shares, MOEX for futures
        shares = [t for t in tickers if t not in fut_set]
        data = fetch_finam_ohlcv(shares, lookback_days) if shares else {}
        if fut_set:
            fut_data = fetch_moex_ohlcv(
                list(fut_set),
                lookback_days=lookback_days,
                use_cache=use_cache,
                futures_tickers=fut_set,
            )
            data.update(fut_data)
        if data:
            # fill missing shares from MOEX
            missing = [t for t in shares if t not in data]
            if missing:
                data.update(
                    fetch_moex_ohlcv(
                        missing, lookback_days=lookback_days, use_cache=use_cache
                    )
                )
            return data
        print("[fetcher] Finam failed/empty → fallback to MOEX ISS")
    return fetch_moex_ohlcv(
        tickers,
        lookback_days=lookback_days,
        use_cache=use_cache,
        futures_tickers=fut_set,
    )


def fetch_weekly(
    tickers: list,
    years: float = 5.0,
    board: str = "TQBR",
) -> Dict[str, pd.DataFrame]:
    """Fetch weekly candles for higher-timeframe analysis."""
    till = datetime.now().strftime("%Y-%m-%d")
    frm = (datetime.now() - timedelta(days=int(years * 365))).strftime("%Y-%m-%d")
    out: Dict[str, pd.DataFrame] = {}
    for i, t in enumerate(tickers, 1):
        is_fut = _is_futures_ticker(t)
        if is_fut:
            df = _candles_from_iss(
                t, frm, till, interval=7, engine="futures", market="forts"
            )
        else:
            df = _candles_from_iss(t, frm, till, interval=7, board=board)
        if df is not None and len(df) >= 30:
            out[t] = df
        if i % 10 == 0:
            print(f"  [moex-w] loaded {i}/{len(tickers)}")
            time.sleep(0.3)
    return out


def _resample_h4(hourly: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1H bars into 4-hour bars."""
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
    futures_tickers: Optional[Set[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    H4 candles for shares and futures (1H → resample 4H).
    """
    till = datetime.now().strftime("%Y-%m-%d")
    frm = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    cache_key = f"moex_h4_{lookback_days}_{datetime.now().strftime('%Y%m%d')}.pkl"
    cache_file = CACHE_DIR / cache_key

    cached: Dict[str, pd.DataFrame] = {}
    if use_cache and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                cached = pickle.load(f)
        except Exception:
            cached = {}

    out: Dict[str, pd.DataFrame] = {}
    fut_set = futures_tickers or {t for t in tickers if _is_futures_ticker(t)}

    for i, t in enumerate(tickers, 1):
        if use_cache and t in cached and cached[t] is not None and len(cached[t]) >= 20:
            out[t] = cached[t]
            continue

        is_fut = t in fut_set or _is_futures_ticker(t)
        if is_fut:
            hourly = _candles_from_iss(
                t, frm, till, interval=60, engine="futures", market="forts"
            )
        else:
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
            cached.update(out)
            with open(cache_file, "wb") as f:
                pickle.dump(cached, f)
        except Exception:
            pass

    return out
