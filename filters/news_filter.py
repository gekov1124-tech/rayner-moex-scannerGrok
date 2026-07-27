"""Heuristic multi-source news filter (RU + EN keywords) for MOEX setups."""

from __future__ import annotations
from typing import List, Dict, Tuple
from strategies.base import Setup

POSITIVE_KW = [
    # EN
    "beat", "upgrade", "growth", "record", "surge", "profit", "strong",
    "outperform", "raise", "bullish", "partnership", "approval", "raised",
    "beats", "exceeded", "positive", "buy",
    # RU
    "рост", "прибыль", "дивиденд", "дивиденды", "рекорд", "сильный", "сильная",
    "увеличил", "увеличила", "upgrade", "рекоменд", "покуп", "оптимист",
    "превысил", "превысила", "успех", "контракт", "сделка",
]

NEGATIVE_KW = [
    # EN
    "miss", "downgrade", "lawsuit", "investigation", "fraud", "bankruptcy",
    "sec", "probe", "cut", "weak", "decline", "loss", "warning", "layoff",
    "delay", "missed", "cuts", "plunges", "falls", "recall", "sell",
    # RU
    "падение", "убыток", "убытки", "санкции", "санкци", "штраф", "иск",
    "расследование", "банкротство", "предупреждение", "сокращение", "увольнен",
    "снизил", "снизила", "упал", "упала", "просел", "просела", "слабо",
    "downgrade", "продаж", "риски", "проблемы", "скандал", "арест",
]

HIGH_IMPACT = [
    # EN
    "earnings", "guidance", "fda", "merger", "acquisition", "bankruptcy",
    "lawsuit", "sec", "investigation", "recall", "delisting", "chapter 11",
    # RU
    "отчётность", "отчетность", "дивиденд", "дивиденды", "санкции", "санкци",
    "банкротство", "иск", "расследование", "штраф", "слияние", "поглощение",
    "делистинг", "мсфо", "рсбу", "собрание акционеров", "совдиректоров",
]


def simple_keyword_sentiment(text: str) -> float:
    text = (text or "").lower()
    pos = sum(1 for w in POSITIVE_KW if w in text)
    neg = sum(1 for w in NEGATIVE_KW if w in text)
    if pos + neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def score_news(news_list: List[Dict]) -> Tuple[float, str, bool]:
    """Returns (avg_sentiment, summary, high_impact_negative_flag)."""
    if not news_list:
        return 0.0, "Нет свежих новостей", False

    scores = []
    titles = []
    high_impact_neg = False

    for n in news_list:
        title = n.get("title") or n.get("headline") or ""
        if not title:
            continue
        titles.append(title)
        s = simple_keyword_sentiment(title)
        scores.append(s)
        title_l = title.lower()
        if any(h in title_l for h in HIGH_IMPACT) and s < -0.15:
            high_impact_neg = True

    avg = sum(scores) / len(scores) if scores else 0.0
    summary = " | ".join(titles[:3]) if titles else "Нет заголовков"
    return avg, summary[:350], high_impact_neg


def apply_news_filter(
    setups: List[Setup],
    news_func,
    min_sentiment: float = -0.35,
    skip_high_impact: bool = True,
) -> List[Setup]:
    filtered: List[Setup] = []
    for s in setups:
        try:
            news = news_func(s.ticker)
            score, summary, high_neg = score_news(news)
            s.news_score = score
            s.news_summary = summary
            if high_neg and skip_high_impact:
                continue
            if score < min_sentiment:
                continue
            filtered.append(s)
        except Exception:
            s.news_score = 0.0
            s.news_summary = "Ошибка новостей / нейтрально"
            filtered.append(s)
    return filtered
