"""Console and file reporters for setups."""

from __future__ import annotations
from typing import List
from pathlib import Path
import pandas as pd
from strategies.base import Setup

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


def print_setups(setups: List[Setup], max_rows: int = 25) -> None:
    if not setups:
        print("\n=== No setups found after filters ===\n")
        return

    rows = []
    for s in setups[:max_rows]:
        rows.append(
            {
                "Ticker": s.ticker,
                "Strategy": s.strategy,
                "Dir": s.direction,
                "Entry": s.entry,
                "Stop": s.stop,
                "Shares": s.suggested_shares,
                "Risk $": round(s.risk_amount, 0),
                "Score": round(s.score, 1),
                "ML": round(getattr(s, "ml_prob", 0) or 0, 2),
                "News": round(s.news_score, 2),
                "Reason (short)": (s.reason[:55] + "...") if len(s.reason) > 55 else s.reason,
                "Цели": (getattr(s, "scale_plan", "") or "")[:50],
            }
        )

    df = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print(" RAYNER-INSPIRED MULTI-STRATEGY SCANNER — SETUPS FOUND")
    print("=" * 100)
    if HAS_TABULATE:
        print(tabulate(df, headers="keys", tablefmt="github", showindex=False))
    else:
        print(df.to_string(index=False))
    print("=" * 100)
    print(f"Total setups shown: {len(rows)} (of {len(setups)} after ranking/filter)")
    print("Exit rules & full reasons are in the CSV / Setup objects.")
    print("=" * 100 + "\n")


def save_csv(setups: List[Setup], path: str = "setups_today.csv") -> None:
    if not setups:
        return
    records = [s.to_dict() for s in setups]
    df = pd.DataFrame(records)
    out = Path(path)
    df.to_csv(out, index=False)
    print(f"[output] Saved {len(setups)} setups → {out.resolve()}")
