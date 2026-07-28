#!/usr/bin/env python3
"""
Simple parameter grid search for one strategy (educational).
Avoid over-fitting: prefer stable params across tickers, not max Total%.

Example:
  python optimize_run.py --strategy ConnorsRSI2 --tickers SBER GAZP LKOH
  python optimize_run.py --strategy RaynerBB_MeanRev --universe sample
"""

from __future__ import annotations
import argparse
import itertools
import sys
from pathlib import Path
from typing import Dict, List, Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from data.universe import get_universe, classify_instrument
from data.moex_fetcher import fetch_ohlcv
from strategies.registry import STRATEGY_REGISTRY, get_strategies
from backtest.engine import backtest_portfolio

# Parameter grids (small — robust, not curve-fit)
GRIDS: Dict[str, Dict[str, List[Any]]] = {
    "ConnorsRSI2": {
        "rsi_entry": [5, 10, 15],
        "rsi_exit": [50, 65, 70],
        "atr_stop_mult": [2.0, 2.5, 3.0],
    },
    "RaynerBB_MeanRev": {
        "bb_std": [2.0, 2.5, 3.0],
        "limit_pct": [0.02, 0.03, 0.04],
        "time_stop": [7, 10, 15],
        "atr_stop_mult": [2.0, 2.5, 3.0],
    },
    "EMA_Pullback": {
        "zone_pct": [0.015, 0.025, 0.04],
        "atr_stop_mult": [1.5, 2.0, 2.5],
        "ema_fast": [10, 20],
        "ema_slow": [50],
    },
    "TrendBreakout_200High": {
        "lookback": [100, 150, 200],
        "atr_mult": [4.0, 6.0, 8.0],
    },
    "Donchian20": {
        "entry_period": [15, 20, 30],
        "exit_period": [10],
        "atr_stop_mult": [1.5, 2.0, 2.5],
    },
}


def grid_combinations(grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    keys = list(grid.keys())
    vals = [grid[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]


def main():
    ap = argparse.ArgumentParser(description="Grid-search strategy params")
    ap.add_argument("--strategy", required=True, choices=list(GRIDS.keys()))
    ap.add_argument("--universe", default="sample")
    ap.add_argument("--tickers", nargs="*", default=None)
    ap.add_argument("--lookback", type=int, default=700)
    ap.add_argument("--equity", type=float, default=1_000_000)
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    tickers = args.tickers or get_universe(args.universe)
    print("=" * 72)
    print(f" OPTIMIZE · {args.strategy}")
    print("=" * 72)
    print(f"Tickers: {tickers}")

    fut = {t for t in tickers if classify_instrument(t) == "futures"}
    data = fetch_ohlcv(
        tickers, source="moex", lookback_days=args.lookback, use_cache=True, futures_tickers=fut
    )
    print(f"Data: {len(data)} symbols\n")

    # Ensure strategy class is imported
    get_strategies(enabled=[args.strategy], load_plugins_flag=True)
    cls = STRATEGY_REGISTRY.get(args.strategy)
    if not cls:
        print("Strategy not found")
        return

    combos = grid_combinations(GRIDS[args.strategy])
    print(f"Combinations: {len(combos)}\n")

    results = []
    for i, params in enumerate(combos, 1):
        strat = cls(params=params)
        res = backtest_portfolio(data, strat, equity=args.equity, risk_pct=0.01)
        m = res.metrics
        score = 0.0
        # Robust score: PF * sqrt(trades) - penalty for DD (not pure return)
        trades = m.get("trades", 0)
        pf = m.get("profit_factor", 0) or 0
        dd = m.get("max_drawdown_pct", 0) or 0
        ret = m.get("total_return_pct", 0) or 0
        if trades >= 5:
            score = pf * (trades ** 0.5) - dd * 0.15 + ret * 0.05
        results.append({**params, **m, "score": round(score, 2)})
        if i % 5 == 0 or i == len(combos):
            print(f"  [{i}/{len(combos)}] best so far score={max(r['score'] for r in results):.2f}")

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[: args.top]

    print("\n" + "=" * 72)
    print(f" TOP {len(top)} (by robust score, not max return)")
    print("=" * 72)
    try:
        from tabulate import tabulate
        # compact columns
        show = []
        for r in top:
            row = {k: r[k] for k in r if k not in ("equity_curve",)}
            show.append(row)
        # limit keys for display
        keys_pref = [k for k in show[0].keys() if k not in ("total_pnl",)]
        print(tabulate([{k: s.get(k) for k in keys_pref} for s in show], headers="keys", tablefmt="github"))
    except Exception:
        for r in top:
            print(r)

    best = top[0]
    print("\n→ Лучший набор для config.yaml → strategy_params:")
    print(f"  {args.strategy}:")
    for k in GRIDS[args.strategy].keys():
        print(f"    {k}: {best[k]}")

    out = ROOT / "output" / f"optimize_{args.strategy}.csv"
    out.parent.mkdir(exist_ok=True)
    import pandas as pd
    pd.DataFrame(results).to_csv(out, index=False)
    print(f"\nВсе комбинации: {out}")
    print("Дисклеймер: оптимизация на той же истории = риск переобучения.")


if __name__ == "__main__":
    main()
