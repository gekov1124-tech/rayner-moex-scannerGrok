#!/usr/bin/env python3
"""Paper journal CLI: status / analyze / export."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from journal.store import JournalStore, JOURNAL_CSV, JOURNAL_JSON
from journal.analyze import analyze_journal, format_report_text


def main():
    ap = argparse.ArgumentParser(description="Virtual trades journal")
    ap.add_argument("cmd", choices=["status", "analyze", "list"], nargs="?", default="analyze")
    args = ap.parse_args()
    store = JournalStore()

    if args.cmd == "status":
        print(f"JSON: {JOURNAL_JSON}")
        print(f"CSV:  {JOURNAL_CSV}")
        print(f"Open: {len(store.open_trades())} · Closed: {len(store.closed_trades())}")
        for t in store.open_trades()[:20]:
            print(f"  OPEN {t.id} {t.ticker} {t.strategy} entry={t.entry_price} mtm={t.mtm_pnl:.0f}")
        return

    if args.cmd == "list":
        for t in store.trades[-30:]:
            print(
                f"{t.status:6} {t.ticker:6} {t.strategy:22} "
                f"pnl={t.pnl:.0f} exit={t.exit_reason or '-'}"
            )
        return

    report = analyze_journal(store)
    print(format_report_text(report))


if __name__ == "__main__":
    main()
