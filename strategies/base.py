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


def build_r_targets(
    entry: float,
    stop: float,
    direction: str = "long",
    multiples: tuple = (1.0, 2.0, 3.0),
    portions: tuple = (0.34, 0.33, 0.33),
) -> List[Dict[str, Any]]:
    """R-multiple take-profit levels for scale-out exits."""
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        return []
    out = []
    for m, portion in zip(multiples, portions):
        if direction == "long":
            price = float(entry) + m * risk
        else:
            price = float(entry) - m * risk
        out.append({
            "price": round(price, 4),
            "portion": float(portion),
            "label": f"{m:g}R",
            "r_multiple": float(m),
        })
    return out


def format_targets_ru(targets: List[Dict[str, Any]], exit_rule: str = "") -> str:
    """Human-readable Russian description of multi-stage exits."""
    if not targets:
        return exit_rule or "По правилу стратегии"
    parts = []
    for t in targets:
        pct = int(round(t.get("portion", 0) * 100))
        parts.append(f"{t.get('label', '?')}: {t['price']} (~{pct}% позиции)")
    text = "Частичная фиксация — " + "; ".join(parts)
    if exit_rule:
        text += f". Остаток: {exit_rule}"
    return text


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
    ml_score: float = 0.0  # model ranking score
    ml_prob: float = 0.0   # P(profitable) if model trained
    # Multi-stage targets: list of {price, portion (0-1), label}
    targets: List[Dict[str, Any]] = field(default_factory=list)
    # Human-readable scale-out plan in Russian
    scale_plan: str = ""

    def risk_per_share(self) -> float:
        if self.direction == "long":
            return max(0.0, self.entry - self.stop)
        return max(0.0, self.stop - self.entry)

    def r_multiple_price(self, r: float) -> float:
        """Price at +R reward for long, -R for short."""
        dist = self.risk_per_share() * r
        if self.direction == "long":
            return self.entry + dist
        return self.entry - dist

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def target_text(self) -> str:
        return format_targets_ru(self.targets, self.exit_rule)


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
