#!/usr/bin/env python3
"""
Train ML ranker from paper journal + backtest trades.

  python ml_train.py
  python ml_train.py --journal-only
  python backtest_run.py --universe sample --all   # generate labels first
  python ml_train.py
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ml.dataset import build_dataset
from ml.train import train_model, MODEL_PATH


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal-only", action="store_true")
    ap.add_argument("--backtest-only", action="store_true")
    args = ap.parse_args()

    use_j = not args.backtest_only
    use_b = not args.journal_only
    X, y, meta = build_dataset(use_journal=use_j, use_backtest=use_b)
    print("=" * 60)
    print(" ML TRAIN · setup success classifier")
    print("=" * 60)
    print(f"Samples: journal={meta['journal']} backtest={meta['backtest']} total={len(y)}")
    if len(y) < 10:
        print(
            "\nНедостаточно данных (нужно ≥ 10 закрытых сделок).\n"
            "1) python backtest_run.py --universe sample --all\n"
            "2) или накопите journal (виртуальные сделки)\n"
            "3) python ml_train.py"
        )
        return
    print(f"Positive rate: {y.mean():.2%}")
    try:
        payload = train_model(X, y)
    except ValueError as e:
        print("Train error:", e)
        return
    m = payload["meta"]
    print(f"Train n={m['n_train']} test n={m['n_test']}")
    print(f"Holdout accuracy: {m['test_accuracy']:.1%}")
    print(f"Model saved: {MODEL_PATH}")
    print("\nВ config.yaml:")
    print("  ml:")
    print("    enabled: true")
    print("    mode: rank   # или filter")
    print("    min_probability: 0.55")


if __name__ == "__main__":
    main()
