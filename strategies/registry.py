"""
Strategy registry + plugin loader.
Any additional strategy must:
  - subclass Strategy
  - implement generate_setups(...)
  - be rules-based, preferably with trend filter (SMA200 / structure)
  - include risk sizing
  to stay compatible with Rayner Teo philosophy.
"""

from __future__ import annotations
from typing import Dict, Type, List, Optional
import importlib
import pkgutil
import sys
from pathlib import Path

from .base import Strategy

STRATEGY_REGISTRY: Dict[str, Type[Strategy]] = {}


def register(name: Optional[str] = None):
    """Decorator to register a Strategy subclass."""
    def decorator(cls: Type[Strategy]):
        key = name or cls.__name__
        STRATEGY_REGISTRY[key] = cls
        return cls
    return decorator


def _discover_module(modname: str):
    try:
        importlib.import_module(modname)
    except Exception as e:
        print(f"[registry] Failed to import {modname}: {e}")


def load_builtin_strategies():
    """Import all strategy modules so @register decorators run."""
    import strategies.mean_reversion  # noqa
    import strategies.trend_following  # noqa
    import strategies.pullback  # noqa
    import strategies.bos_mtf  # noqa
    import strategies.false_break  # noqa


def load_plugins(plugins_dir: Optional[str] = None):
    """
    Load additional strategies from plugins/ folder.
    Each .py file can contain one or more @register Strategy classes.
    """
    root = Path(__file__).resolve().parent.parent
    pdir = Path(plugins_dir) if plugins_dir else root / "plugins"
    if not pdir.exists():
        pdir.mkdir(exist_ok=True)
        # write example
        example = pdir / "example_strategy.py"
        if not example.exists():
            example.write_text(
                '''"""
Example additional strategy (compatible with Rayner Teo).
Copy & modify. Must have trend filter + objective rules + risk.
"""
from strategies.base import Strategy, Setup
from strategies.registry import register
from utils.indicators import sma, roc, atr
from typing import List
import pandas as pd

@register("ExampleROC_Momentum")
class ExampleROC_Momentum(Strategy):
    """Buy strong names above SMA200 with positive ROC. Simple momentum."""
    def __init__(self, params=None):
        default = {"sma_period": 200, "roc_period": 60, "min_roc": 5.0, "risk_pct": 0.01}
        super().__init__("ExampleROC_Momentum", {**default, **(params or {})})

    def generate_setups(self, ticker: str, df: pd.DataFrame, equity: float = 100_000) -> List[Setup]:
        p = self.params
        if len(df) < p["sma_period"] + 20:
            return []
        df = df.copy()
        df["SMA200"] = sma(df["Close"], p["sma_period"])
        df["ROC"] = roc(df["Close"], p["roc_period"])
        df["ATR"] = atr(df)
        last = df.iloc[-1]
        if (last["Close"] > last["SMA200"] and last["ROC"] > p["min_roc"]
                and not pd.isna(last["ATR"])):
            entry = float(last["Close"])
            stop = entry - 2.5 * float(last["ATR"])
            risk_amount = equity * p["risk_pct"]
            shares = max(1, int(risk_amount / (entry - stop))) if entry > stop else 0
            return [Setup(
                ticker=ticker, strategy=self.name, direction="long",
                entry=round(entry, 2), stop=round(stop, 2),
                exit_rule="Трейл по ATR или закрытие ниже SMA200",
                atr=round(float(last["ATR"]), 2), score=float(last["ROC"]),
                reason=f"Цена выше SMA200, ROC({p['roc_period']})={last['ROC']:.1f}% выше {p['min_roc']} — импульс вверх",
                suggested_shares=shares, risk_amount=round(risk_amount, 2),
                capital_pct=p["risk_pct"],
            )]
        return []
'''
            )
        # Add plugins to path
        if str(pdir) not in sys.path:
            sys.path.insert(0, str(pdir.parent))
        for py in pdir.glob("*.py"):
            if py.name.startswith("_"):
                continue
            modname = f"plugins.{py.stem}"
            try:
                importlib.import_module(modname)
            except Exception as e:
                # try direct
                try:
                    spec = importlib.util.spec_from_file_location(py.stem, py)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[py.stem] = mod
                        spec.loader.exec_module(mod)
                except Exception as e2:
                    print(f"[registry] plugin {py.name}: {e2}")


def get_strategies(
    enabled: Optional[List[str]] = None,
    load_plugins_flag: bool = True,
    plugins_dir: Optional[str] = None,
) -> List[Strategy]:
    """
    Return list of strategy instances.
    enabled: list of names (registry keys). None = all registered.
    """
    load_builtin_strategies()
    if load_plugins_flag:
        load_plugins(plugins_dir)

    if not STRATEGY_REGISTRY:
        print("[registry] WARNING: no strategies registered")
        return []

    if enabled is None:
        return [cls() for cls in STRATEGY_REGISTRY.values()]

    result = []
    for name in enabled:
        if name in STRATEGY_REGISTRY:
            result.append(STRATEGY_REGISTRY[name]())
        else:
            print(f"[registry] Strategy '{name}' not found. Available: {list(STRATEGY_REGISTRY.keys())}")
    return result


def list_registered() -> List[str]:
    load_builtin_strategies()
    load_plugins()
    return list(STRATEGY_REGISTRY.keys())
