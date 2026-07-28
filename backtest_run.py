#!/usr/bin/env python3
"""
Historical backtest CLI for Rayner × MOEX strategies.

Examples:
  python backtest_run.py --universe sample --strategy RaynerBB_MeanRev
  python backtest_run.py --universe sample --all
  python backtest_run.py --tickers SBER GAZP SiU6 --strategy EMA_Pullback
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from data.universe import get_universe, classify_instrument
from data.moex_fetcher import fetch_ohlcv
from strategies.registry import get_strategies, list_registered
from backtest.engine import backtest_portfolio, backtest_symbol


def main():
    p = argparse.ArgumentParser(description="Backtest Rayner MOEX strategies")
    p.add_argument("--universe", default="sample", help="sample|blue|futures|mixed")
    p.add_argument("--tickers", nargs="*", default=None)
    p.add_argument("--strategy", default=None, help="One strategy name")
    p.add_argument("--all", action="store_true", help="All registered strategies")
    p.add_argument("--equity", type=float, default=1_000_000)
    p.add_argument("--risk", type=float, default=0.01)
    p.add_argument("--lookback", type=int, default=700)
    p.add_argument("--source", default="moex")
    args = p.parse_args()

    if args.tickers:
        tickers = args.tickers
    else:
        tickers = get_universe(args.universe)

    print("=" * 72)
    print(" BACKTEST · Rayner × MOEX (educational)")
    print("=" * 72)
    print(f"Tickers: {len(tickers)} · lookback={args.lookback}d · equity={args.equity:,.0f}")

    fut = {t for t in tickers if classify_instrument(t) == "futures"}
    data = fetch_ohlcv(
        tickers,
        source=args.source,
        lookback_days=args.lookback,
        use_cache=True,
        futures_tickers=fut,
    )
    print(f"Data loaded: {len(data)} symbols\n")

    if args.all or not args.strategy:
        names = list_registered()
        if args.strategy:
            names = [args.strategy]
        elif not args.all:
            names = ["RaynerBB_MeanRev", "ConnorsRSI2", "EMA_Pullback", "TrendBreakout_200High", "Donchian20"]
    else:
        names = [args.strategy]

    strategies = get_strategies(enabled=names, load_plugins_flag=True)
    if not strategies:
        print("No strategies found:", names)
        return

    rows = []
    all_trades_path = ROOT / "output" / "backtest_trades.csv"
    all_trades_path.parent.mkdir(exist_ok=True)
    trade_rows = []

    for strat in strategies:
        # Skip BOS MTF in pure daily backtest unless H4 available (slow) — still run daily fallback
        print(f"→ {strat.name} ...")
        result = backtest_portfolio(
            data, strat, equity=args.equity, risk_pct=args.risk
        )
        m = result.metrics
        rows.append(
            {
                "Strategy": strat.name,
                "Trades": m.get("trades", 0),
                "Win%": m.get("win_rate", 0),
                "Avg%": m.get("avg_pnl_pct", 0),
                "Total%": m.get("total_return_pct", 0),
                "PF": m.get("profit_factor", 0),
                "MaxDD%": m.get("max_drawdown_pct", 0),
                "AvgBars": m.get("avg_bars", 0),
            }
        )
        for t in result.trades:
            if t.exit_date:
                trade_rows.append(
                    {
                        "strategy": t.strategy,
                        "ticker": t.ticker,
                        "direction": t.direction,
                        "entry_date": t.entry_date,
                        "entry": t.entry_price,
                        "exit_date": t.exit_date,
                        "exit": t.exit_price,
                        "stop": t.stop,
                        "shares": t.shares,
                        "pnl": round(t.pnl, 2),
                        "pnl_pct": round(t.pnl_pct * 100, 2),
                        "bars": t.bars_held,
                        "exit_reason": t.exit_reason,
                    }
                )
        print(
            f"   trades={m.get('trades')} win={m.get('win_rate')}% "
            f"ret={m.get('total_return_pct')}% PF={m.get('profit_factor')} "
            f"DD={m.get('max_drawdown_pct')}%"
        )

    print("\n" + "=" * 72)
    print(" SUMMARY")
    print("=" * 72)
    try:
        from tabulate import tabulate
        print(tabulate(rows, headers="keys", tablefmt="github"))
    except ImportError:
        for r in rows:
            print(r)

    if trade_rows:
        import pandas as pd
        pd.DataFrame(trade_rows).to_csv(all_trades_path, index=False)
        print(f"\nСделки сохранены: {all_trades_path}")

    print("\nДисклеймер: без проскальзывания/комиссий брокерской модели. Только обучение.")


if __name__ == "__main__":
    main()
