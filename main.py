#!/usr/bin/env python3
"""
Rayner Teo Inspired Multi-Strategy Scanner — MOEX (Московская биржа)
Данные: MOEX ISS (бесплатно) + опционально Finam.
Деплой: GitHub → Railway (Cron + Web).
Плагины: папка plugins/ для дополнительных стратегий.

Образовательный инструмент. НЕ является финансовой рекомендацией.
"""

from __future__ import annotations
import argparse
import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import yaml
from data.universe import get_universe
from data.moex_fetcher import fetch_ohlcv, fetch_h4
from data.news_aggregator import aggregate_news
from filters.news_filter import apply_news_filter
from strategies.registry import get_strategies, list_registered, STRATEGY_REGISTRY
from strategies.base import Setup
from output.reporter import print_setups, save_csv
from notify.telegram_alerts import send_setups_alert, is_telegram_configured


def ensure_aov(setups, data):
    """Attach Rayner Area of Value levels from OHLCV to each setup."""
    from data.structure import compute_area_of_value
    for s in setups:
        df = (data or {}).get(s.ticker)
        if df is None or getattr(df, "empty", True):
            continue
        try:
            aov = compute_area_of_value(df)
        except Exception:
            continue
        s.value_zone_low = float(aov.get("zone_low") or 0)
        s.value_zone_high = float(aov.get("zone_high") or 0)
        s.value_zone_label = aov.get("zone_label") or ""
        s.aov_levels = aov.get("levels") or []
    return setups

def ensure_targets(setups):
    """Fill multi-stage R targets if strategy did not set them."""
    from strategies.base import build_r_targets, format_targets_ru
    for s in setups:
        if s.targets:
            if not s.scale_plan:
                s.scale_plan = format_targets_ru(s.targets, s.exit_rule)
            continue
        # Strategy-specific default scale-out
        name = s.strategy or ""
        if name in ("RaynerBB_MeanRev", "ConnorsRSI2"):
            # mean-reversion: take profit faster
            mults, parts = (1.0, 1.5, 2.0), (0.40, 0.35, 0.25)
            rest = "по правилу RSI / времени"
        elif name in ("TrendBreakout_200High", "Donchian20"):
            mults, parts = (1.5, 2.5, 4.0), (0.25, 0.25, 0.50)
            rest = "трейлинг по ATR / структуре"
        elif name == "EMA_Pullback":
            mults, parts = (1.0, 2.0, 3.0), (0.33, 0.33, 0.34)
            rest = "трейл под EMA50 / структурой"
        elif "BOS" in name:
            mults, parts = (1.0, 2.0, 3.0), (0.30, 0.30, 0.40)
            rest = "трейл по H4-структуре"
        else:
            mults, parts = (1.0, 2.0, 3.0), (0.34, 0.33, 0.33)
            rest = s.exit_rule or "по правилу стратегии"
        s.targets = build_r_targets(s.entry, s.stop, s.direction, mults, parts)
        s.scale_plan = format_targets_ru(s.targets, rest)
    return setups



def load_config(path: str = "config.yaml") -> dict:
    cfg_path = ROOT / path
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def run_scan(
    universe: str = "sample",
    source: str = "moex",
    equity: Optional[float] = None,
    no_news: bool = True,
    max_setups: int = 20,
    strategies: Optional[List[str]] = None,
    plugins_dir: str = "plugins",
    config_path: str = "config.yaml",
    send_telegram: bool = True,
) -> Tuple[List[Setup], str]:
    """
    Run full market scan. Returns (list of setups, log text).
    Used by CLI and by web interface.
    """
    cfg = load_config(config_path)
    equity = equity if equity is not None else cfg.get("equity", 1_000_000)
    news_cfg = cfg.get("news", {})
    news_enabled = news_cfg.get("enabled", True) and not no_news

    buf = io.StringIO()
    with redirect_stdout(buf):
        print("=" * 72)
        print(" RAYNER TEO × MOEX SCANNER (Московская биржа)")
        print(" Философия: Price Action + Rules-based + Trend + Risk First")
        print("=" * 72)
        print("DISCLAIMER: Не финансовая рекомендация. Риск потери капитала.")
        print("=" * 72)

        enabled = strategies or cfg.get("strategies")
        strat_objs = get_strategies(
            enabled=enabled, load_plugins_flag=True, plugins_dir=plugins_dir
        )

        if not strat_objs:
            print("Нет стратегий. Проверьте config или --list-strategies")
            return [], buf.getvalue()

        from data.universe import classify_instrument
        tickers = get_universe(universe)
        fut_tickers = {t for t in tickers if classify_instrument(t) == "futures"}
        share_n = len(tickers) - len(fut_tickers)
        print(f"\n[1/4] Universe: {universe} → {len(tickers)} инструментов "
              f"(акции: {share_n}, фьючерсы: {len(fut_tickers)})")
        if fut_tickers:
            print(f"      FORTS: {', '.join(sorted(fut_tickers))}")
        print(f"[2/4] Данные: {source.upper()}...")

        data = fetch_ohlcv(
            tickers,
            source=source,
            lookback_days=cfg.get("lookback_days", 500),
            use_cache=True,
            futures_tickers=fut_tickers,
        )
        print(f"      Получено данных: {len(data)} инструментов")

        h4_data = {}
        need_h4 = any(getattr(s, "name", "") == "Rayner_BOS_MTF" for s in strat_objs)
        if need_h4:
            print("      Загрузка H4 (1H→4H) для Break of Structure...")
            try:
                h4_data = fetch_h4(list(data.keys()), lookback_days=90, use_cache=True, futures_tickers=fut_tickers)
                print(f"      H4 получено: {len(h4_data)} тикеров")
            except Exception as e:
                print(f"      H4 недоступны ({e}) — fallback Daily BOS")
            for strat in strat_objs:
                if getattr(strat, "name", "") == "Rayner_BOS_MTF" and hasattr(
                    strat, "set_h4_data"
                ):
                    strat.set_h4_data(h4_data)

        print(f"[3/4] Стратегии ({len(strat_objs)}): {[s.name for s in strat_objs]}")
        all_setups: List[Setup] = []
        for ticker, df in data.items():
            if "Close" not in df.columns:
                continue
            for strat in strat_objs:
                try:
                    all_setups.extend(
                        strat.generate_setups(ticker, df, equity=equity)
                    )
                except Exception:
                    continue

        print(f"      Сырых сэтапов: {len(all_setups)}")
        all_setups.sort(key=lambda s: s.score, reverse=True)
        all_setups = ensure_targets(all_setups)
        all_setups = ensure_aov(all_setups, data)

        # ML rank / filter (optional)
        ml_cfg = cfg.get("ml") or {}
        if ml_cfg.get("enabled") and all_setups:
            try:
                from ml.ranker import get_ranker_from_config
                ranker = get_ranker_from_config(cfg)
                before = len(all_setups)
                all_setups = ranker.apply(all_setups, data)
                mode = ml_cfg.get("mode", "rank")
                print(f"      ML ({mode}): {before} → {len(all_setups)}"
                      + (f" model={'yes' if ranker.available else 'no'}" ))
            except Exception as e:
                print(f"      ML skip: {e}")

        if news_enabled and all_setups:
            print("[4/4] Новостной фильтр...")

            def news_func(t: str):
                return aggregate_news(
                    t,
                    sources=news_cfg.get(
                        "sources",
                        [
                            "google",
                            "rbc",
                            "interfax",
                            "finam",
                            "smartlab",
                            "rss",
                        ],
                    ),
                    finnhub_key=(cfg.get("api_keys", {}) or {}).get("finnhub")
                    or os.getenv("FINNHUB_API_KEY"),
                )

            before = len(all_setups)
            all_setups = apply_news_filter(
                all_setups,
                news_func,
                min_sentiment=news_cfg.get("min_sentiment", -0.35),
                skip_high_impact=True,
            )
            print(
                f"      После фильтра: {len(all_setups)} (убрано {before - len(all_setups)})"
            )
        else:
            print("[4/4] Новостной фильтр отключён")

        selected: List[Setup] = []
        seen = set()
        max_pos = cfg.get("max_positions", 8)
        for s in all_setups:
            if s.ticker not in seen:
                selected.append(s)
                seen.add(s.ticker)
            if len(selected) >= max(max_setups, max_pos * 2):
                break

        print_setups(selected, max_rows=max_setups)
        save_csv(selected, str(ROOT / "setups_today.csv"))

        tg_cfg = cfg.get("telegram", {}) or {}
        if send_telegram and tg_cfg.get("enabled", True) and selected:
            if is_telegram_configured():
                send_setups_alert(
                    selected, title=tg_cfg.get("title", "Rayner × MOEX Scanner")
                )
            else:
                print(
                    "[telegram] Не настроен (задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID)"
                )
        elif send_telegram and not selected:
            if is_telegram_configured() and tg_cfg.get("enabled", True):
                send_setups_alert(
                    [], title=tg_cfg.get("title", "Rayner × MOEX Scanner")
                )

        print("\nГотово.")

    return selected, buf.getvalue()


def main():
    parser = argparse.ArgumentParser(
        description="MOEX Scanner (Rayner Teo) — educational"
    )
    parser.add_argument("--universe", default="sample", help="sample | blue | tqbr | full")
    parser.add_argument("--source", default="moex", choices=["moex", "finam"])
    parser.add_argument("--equity", type=float, default=None)
    parser.add_argument("--no-news", action="store_true")
    parser.add_argument("--max-setups", type=int, default=20)
    parser.add_argument("--strategies", nargs="*", default=None)
    parser.add_argument("--list-strategies", action="store_true")
    parser.add_argument("--plugins-dir", default="plugins")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    if args.list_strategies:
        get_strategies(load_plugins_flag=True, plugins_dir=args.plugins_dir)
        print("Зарегистрированные стратегии:")
        for name in list_registered():
            print(f"  - {name}")
        print(f"\nВсего: {len(STRATEGY_REGISTRY)}")
        print("Добавить свою: файл в plugins/ с @register классом Strategy")
        return

    setups, log = run_scan(
        universe=args.universe,
        source=args.source,
        equity=args.equity,
        no_news=args.no_news,
        max_setups=args.max_setups,
        strategies=args.strategies,
        plugins_dir=args.plugins_dir,
        config_path=args.config,
        send_telegram=True,
    )
    print(log)


if __name__ == "__main__":
    main()
