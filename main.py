#!/usr/bin/env python3
"""
Rayner Teo Inspired Multi-Strategy Scanner — MOEX (Московская биржа)
Данные: MOEX ISS (бесплатно) + опционально Finam.
Деплой: GitHub → Railway (Cron).
Плагины: папка plugins/ для дополнительных стратегий.

Образовательный инструмент. НЕ является финансовой рекомендацией.
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
from typing import List

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


def load_config(path: str = "config.yaml") -> dict:
    cfg_path = ROOT / path
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def main():
    parser = argparse.ArgumentParser(description="MOEX Scanner (Rayner Teo) — educational")
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

    cfg = load_config(args.config)
    equity = args.equity or cfg.get("equity", 1_000_000)
    news_cfg = cfg.get("news", {})
    news_enabled = news_cfg.get("enabled", True) and not args.no_news

    print("=" * 72)
    print(" RAYNER TEO × MOEX SCANNER (Московская биржа)")
    print(" Философия: Price Action + Rules-based + Trend + Risk First")
    print("=" * 72)
    print("DISCLAIMER: Не финансовая рекомендация. Риск потери капитала.")
    print("=" * 72)

    enabled = args.strategies or cfg.get("strategies")
    strategies = get_strategies(enabled=enabled, load_plugins_flag=True, plugins_dir=args.plugins_dir)

    if args.list_strategies:
        print("Зарегистрированные стратегии:")
        for name in list_registered():
            print(f"  - {name}")
        print(f"\nВсего: {len(STRATEGY_REGISTRY)}")
        print("Добавить свою: файл в plugins/ с @register классом Strategy")
        return

    if not strategies:
        print("Нет стратегий. Проверьте config или --list-strategies")
        return

    tickers = get_universe(args.universe)
    print(f"\n[1/4] Universe: {args.universe} → {len(tickers)} тикеров MOEX")
    print(f"[2/4] Данные: {args.source.upper()}...")

    data = fetch_ohlcv(tickers, source=args.source, lookback_days=cfg.get("lookback_days", 500), use_cache=True)
    print(f"      Получено данных: {len(data)} тикеров")

    # H4 for Rayner BOS MTF (Daily HTF + H4 LTF)
    h4_data = {}
    need_h4 = any(getattr(s, "name", "") == "Rayner_BOS_MTF" for s in strategies)
    if need_h4:
        print("      Загрузка H4 (1H→4H) для Break of Structure...")
        try:
            h4_data = fetch_h4(list(data.keys()), lookback_days=90, use_cache=True)
            print(f"      H4 получено: {len(h4_data)} тикеров")
        except Exception as e:
            print(f"      H4 недоступны ({e}) — fallback Daily BOS")
        for strat in strategies:
            if getattr(strat, "name", "") == "Rayner_BOS_MTF" and hasattr(strat, "set_h4_data"):
                strat.set_h4_data(h4_data)

    print(f"[3/4] Стратегии ({len(strategies)}): {[s.name for s in strategies]}")
    all_setups: List[Setup] = []
    for ticker, df in data.items():
        if "Close" not in df.columns:
            continue
        for strat in strategies:
            try:
                all_setups.extend(strat.generate_setups(ticker, df, equity=equity))
            except Exception:
                continue

    print(f"      Сырых сэтапов: {len(all_setups)}")
    all_setups.sort(key=lambda s: s.score, reverse=True)

    if news_enabled and all_setups:
        print("[4/4] Новостной фильтр...")
        def news_func(t: str):
            return aggregate_news(
                t,
                sources=news_cfg.get("sources", ["google", "rbc", "interfax", "finam", "smartlab", "rss"]),
                finnhub_key=(cfg.get("api_keys", {}) or {}).get("finnhub") or os.getenv("FINNHUB_API_KEY"),
            )
        before = len(all_setups)
        all_setups = apply_news_filter(all_setups, news_func, min_sentiment=news_cfg.get("min_sentiment", -0.35), skip_high_impact=True)
        print(f"      После фильтра: {len(all_setups)} (убрано {before - len(all_setups)})")
    else:
        print("[4/4] Новостной фильтр отключён")

    selected: List[Setup] = []
    seen = set()
    max_pos = cfg.get("max_positions", 8)
    for s in all_setups:
        if s.ticker not in seen:
            selected.append(s)
            seen.add(s.ticker)
        if len(selected) >= max(args.max_setups, max_pos * 2):
            break

    print_setups(selected, max_rows=args.max_setups)
    save_csv(selected, str(ROOT / "setups_today.csv"))

    # Telegram alerts
    tg_cfg = cfg.get("telegram", {}) or {}
    if tg_cfg.get("enabled", True) and selected:
        if is_telegram_configured():
            send_setups_alert(selected, title=tg_cfg.get("title", "Rayner × MOEX Scanner"))
        else:
            print("[telegram] Не настроен (задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID)")

    print("\nСледующие шаги:")
    print("  1. Проверьте reason каждого сэтапа.")
    print("  2. Paper-trade / бэктест.")
    print("  3. Добавить стратегию → plugins/ + @register")
    print("  4. Деплой: GitHub → Railway Cron (см. DEPLOY.md)")
    print("\nГотово.")


if __name__ == "__main__":
    main()
