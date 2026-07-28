"""Build training set from paper journal and/or backtest CSV."""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from strategies.base import Setup
from ml.features import setup_to_features, vectorize, FEATURE_NAMES
from journal.store import JournalStore, JOURNAL_CSV

ROOT = Path(__file__).resolve().parent.parent
BACKTEST_CSV = ROOT / "output" / "backtest_trades.csv"


def _row_to_setup(row: dict) -> Setup:
    return Setup(
        ticker=str(row.get("ticker", "")),
        strategy=str(row.get("strategy", "")),
        direction=str(row.get("direction", "long")),
        entry=float(row.get("entry") or row.get("entry_price") or 0),
        stop=float(row.get("stop") or 0),
        exit_rule=str(row.get("exit_rule") or row.get("exit_reason") or ""),
        atr=0.0,
        score=float(row.get("score") or 0),
        reason=str(row.get("reason") or ""),
        suggested_shares=int(row.get("shares") or 1),
        risk_amount=float(row.get("risk_amount") or 0),
    )


def from_journal(min_closed: int = 1) -> Tuple[np.ndarray, np.ndarray]:
    store = JournalStore()
    closed = store.closed_trades()
    X, y = [], []
    for t in closed:
        s = Setup(
            ticker=t.ticker,
            strategy=t.strategy,
            direction=t.direction,
            entry=t.entry_price,
            stop=t.stop,
            exit_rule=t.exit_rule,
            score=t.score,
            reason=t.reason,
            suggested_shares=t.shares,
            risk_amount=t.risk_amount,
        )
        # without live df at train time — context zeros/defaults still ok for strategy identity
        feat = setup_to_features(s, None)
        X.append(vectorize(feat))
        y.append(1 if t.pnl > 0 else 0)
    if len(X) < min_closed:
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros((0,))
    return np.vstack(X), np.array(y, dtype=int)


def from_backtest_csv(path: Optional[Path] = None) -> Tuple[np.ndarray, np.ndarray]:
    path = path or BACKTEST_CSV
    if not path.exists():
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros((0,))
    df = pd.read_csv(path)
    X, y = [], []
    for _, row in df.iterrows():
        s = _row_to_setup(row.to_dict())
        feat = setup_to_features(s, None)
        X.append(vectorize(feat))
        pnl = float(row.get("pnl") or 0)
        y.append(1 if pnl > 0 else 0)
    if not X:
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros((0,))
    return np.vstack(X), np.array(y, dtype=int)


def build_dataset(
    use_journal: bool = True,
    use_backtest: bool = True,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    xs, ys = [], []
    meta = {"journal": 0, "backtest": 0}
    if use_journal:
        Xj, yj = from_journal()
        if len(yj):
            xs.append(Xj)
            ys.append(yj)
            meta["journal"] = len(yj)
    if use_backtest:
        Xb, yb = from_backtest_csv()
        if len(yb):
            xs.append(Xb)
            ys.append(yb)
            meta["backtest"] = len(yb)
    if not xs:
        return np.zeros((0, len(FEATURE_NAMES))), np.zeros((0,)), meta
    return np.vstack(xs), np.concatenate(ys), meta
