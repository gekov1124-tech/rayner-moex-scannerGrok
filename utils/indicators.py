"""
Pure pandas/numpy technical indicators.
Aligned with Rayner Teo systems and compatible quant rules (Connors, Turtle, etc.).
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(df["Close"], period)
    std = df["Close"].rolling(window=period, min_periods=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower


def donchian(df: pd.DataFrame, period: int = 20) -> tuple[pd.Series, pd.Series]:
    high = df["High"].rolling(window=period, min_periods=period).max()
    low = df["Low"].rolling(window=period, min_periods=period).min()
    return high, low


def roc(series: pd.Series, period: int = 100) -> pd.Series:
    return (series / series.shift(period) - 1.0) * 100.0


def highest_close(df: pd.DataFrame, period: int = 200) -> pd.Series:
    return df["Close"].rolling(window=period, min_periods=period).max()


def lowest_close(df: pd.DataFrame, period: int = 200) -> pd.Series:
    return df["Close"].rolling(window=period, min_periods=period).min()


def distance_to_ma(close: pd.Series, ma: pd.Series) -> pd.Series:
    """Percentage distance from MA. Positive = above."""
    return (close - ma) / ma * 100.0
