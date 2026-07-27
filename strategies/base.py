"""
Base Strategy ABC and Setup dataclass.
All strategies must be rules-based, objective, and aligned with
Rayner Teo philosophy: trade with the trend, simple edges, risk first.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
import pandas as pd


@dataclass
class Setup:
    ticker: str
    strategy: str
    direction: str  # "long" or "short"
    entry: float
    stop: float
    exit_rule: str
    atr: float = 0.0
    score: float = 0.0  # higher = better (ROC / strength / confluence)
    reason: str = ""
    suggested_shares: int = 0
    risk_amount: float = 0.0
    news_score: float = 0.0
    news_summary: str = ""
    capital_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Strategy(ABC):
    def __init__(self, name: str, params: Optional[Dict] = None):
        self.name = name
        self.params = params or {}

    @abstractmethod
    def generate_setups(
        self, ticker: str, df: pd.DataFrame, equity: float = 100_000
    ) -> List[Setup]:
        """
        Analyze OHLCV DataFrame and return list of valid Setup objects
        (usually 0 or 1 for the latest bar).
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
