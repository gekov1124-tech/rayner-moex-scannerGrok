"""Analyze paper journal for learning insights."""

from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List
import numpy as np

from journal.store import JournalStore, PaperTrade


def analyze_journal(store: JournalStore | None = None) -> Dict[str, Any]:
    store = store or JournalStore()
    closed = store.closed_trades()
    open_ = store.open_trades()

    report: Dict[str, Any] = {
        "open_count": len(open_),
        "closed_count": len(closed),
        "open_mtm_pnl": round(sum(t.mtm_pnl for t in open_), 2),
        "by_strategy": {},
        "by_ticker": {},
        "by_exit_reason": {},
        "lessons": [],
        "summary": {},
    }

    if not closed:
        report["lessons"].append(
            "Пока нет закрытых виртуальных сделок. Копите журнал 2–4 недели, затем повторите анализ."
        )
        report["summary"] = {"trades": 0}
        return report

    pnls = [t.pnl for t in closed]
    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    gross_win = sum(t.pnl for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

    report["summary"] = {
        "trades": len(closed),
        "win_rate": round(100.0 * len(wins) / len(closed), 1),
        "total_pnl": round(sum(pnls), 2),
        "avg_pnl": round(float(np.mean(pnls)), 2),
        "avg_pnl_pct": round(float(np.mean([t.pnl_pct for t in closed])) * 100, 2),
        "profit_factor": round(pf, 2),
        "avg_bars": round(float(np.mean([t.bars_held for t in closed])), 1),
        "best_trade": max(closed, key=lambda t: t.pnl).to_dict(),
        "worst_trade": min(closed, key=lambda t: t.pnl).to_dict(),
    }

    # by strategy
    by_s: Dict[str, List[PaperTrade]] = defaultdict(list)
    for t in closed:
        by_s[t.strategy].append(t)
    for name, ts in by_s.items():
        w = [x for x in ts if x.pnl > 0]
        report["by_strategy"][name] = {
            "trades": len(ts),
            "win_rate": round(100.0 * len(w) / len(ts), 1),
            "total_pnl": round(sum(x.pnl for x in ts), 2),
            "avg_pnl_pct": round(float(np.mean([x.pnl_pct for x in ts])) * 100, 2),
        }

    # by ticker
    by_t: Dict[str, List[PaperTrade]] = defaultdict(list)
    for t in closed:
        by_t[t.ticker].append(t)
    for name, ts in sorted(by_t.items(), key=lambda kv: sum(x.pnl for x in kv[1])):
        report["by_ticker"][name] = {
            "trades": len(ts),
            "total_pnl": round(sum(x.pnl for x in ts), 2),
        }

    # exit reasons
    by_e: Dict[str, int] = defaultdict(int)
    for t in closed:
        by_e[t.exit_reason or "unknown"] += 1
    report["by_exit_reason"] = dict(by_e)

    # Lessons (rule-based coaching)
    lessons = []
    s = report["summary"]
    if s["win_rate"] >= 55 and s["profit_factor"] < 1.0:
        lessons.append(
            "Много прибыльных сделок, но PF < 1: убытки крупнее прибылей. "
            "Проверьте стопы и не удерживайте слабые позиции дольше правила выхода."
        )
    if s["win_rate"] < 40 and s["profit_factor"] >= 1.2:
        lessons.append(
            "Низкий win rate при хорошем PF — нормально для трендовых систем (Rayner TF). "
            "Не отключайте стратегию только из‑за частых мелких стопов."
        )
    if s["profit_factor"] < 0.9 and s["trades"] >= 15:
        lessons.append(
            "PF устойчиво ниже 1 на живой выборке: уменьшите частоту входов или отключите "
            "худшую стратегию (см. блок by_strategy)."
        )
    # worst strategy
    if report["by_strategy"]:
        worst = min(report["by_strategy"].items(), key=lambda kv: kv[1]["total_pnl"])
        best = max(report["by_strategy"].items(), key=lambda kv: kv[1]["total_pnl"])
        if worst[1]["trades"] >= 5 and worst[1]["total_pnl"] < 0:
            lessons.append(
                f"Слабее других: {worst[0]} (PnL {worst[1]['total_pnl']}). "
                f"Сильнее: {best[0]} (PnL {best[1]['total_pnl']}). "
                "Имеет смысл сузить universe или параметры слабой стратегии."
            )
    stop_exits = by_e.get("stop", 0)
    if stop_exits >= max(3, len(closed) * 0.5):
        lessons.append(
            "Больше половины выходов по стопу: либо вход слишком ранний, либо стоп тесный. "
            "Сверьте ATR-множитель и зону входа (Area of Value)."
        )
    if s["avg_bars"] <= 2 and "RSI" in str(by_s.keys()):
        lessons.append(
            "Очень короткое удержание — характерно для RSI mean-reversion. "
            "Следите, чтобы комиссии не съели край на реальном счёте."
        )
    if not lessons:
        lessons.append(
            "Статистики пока недостаточно для жёстких выводов, либо результаты сбалансированы. "
            "Продолжайте вести журнал и сравнивайте с бэктестом раз в месяц."
        )
    report["lessons"] = lessons
    return report


def format_report_text(report: Dict[str, Any]) -> str:
    lines = ["=" * 60, " АНАЛИЗ ЖУРНАЛА ВИРТУАЛЬНЫХ СДЕЛОК", "=" * 60]
    s = report.get("summary") or {}
    lines.append(f"Открытых: {report.get('open_count', 0)} · Закрытых: {report.get('closed_count', 0)}")
    if report.get("open_count"):
        lines.append(f"MTM по открытым: {report.get('open_mtm_pnl', 0)}")
    if s.get("trades"):
        lines.append(
            f"Win rate: {s.get('win_rate')}% · Total PnL: {s.get('total_pnl')} · "
            f"PF: {s.get('profit_factor')} · Avg bars: {s.get('avg_bars')}"
        )
    if report.get("by_strategy"):
        lines.append("\nПо стратегиям:")
        for name, m in report["by_strategy"].items():
            lines.append(
                f"  {name}: n={m['trades']} win={m['win_rate']}% pnl={m['total_pnl']} avg%={m['avg_pnl_pct']}"
            )
    if report.get("by_exit_reason"):
        lines.append("\nПричины выхода: " + ", ".join(f"{k}={v}" for k, v in report["by_exit_reason"].items()))
    lines.append("\nУроки / рекомендации:")
    for i, L in enumerate(report.get("lessons") or [], 1):
        lines.append(f"  {i}. {L}")
    lines.append("=" * 60)
    return "\n".join(lines)
