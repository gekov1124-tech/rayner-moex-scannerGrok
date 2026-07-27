"""
Multi-source news aggregator for MOEX / Russian market.
Sources: RBC, Interfax, Finam, Smart-Lab, Kommersant, Google News RU, Yahoo RSS, optional Finnhub.
"""

from __future__ import annotations
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from urllib.parse import quote_plus
import os
import re
import requests

try:
    import feedparser
except ImportError:
    feedparser = None

try:
    import yfinance as yf
except ImportError:
    yf = None


# ---------------------------------------------------------------------------
# Individual source fetchers
# ---------------------------------------------------------------------------

def get_yfinance_news(ticker: str, max_items: int = 10) -> List[Dict]:
    if yf is None:
        return []
    try:
        t = yf.Ticker(ticker)
        news = getattr(t, "news", None) or []
        results = []
        for n in news[:max_items]:
            title = (
                n.get("title")
                or (n.get("content") or {}).get("title")
                or n.get("headline")
                or ""
            )
            if not title:
                continue
            results.append({
                "title": title,
                "publisher": n.get("publisher") or "Yahoo",
                "link": n.get("link") or n.get("url") or "",
                "source": "yfinance",
            })
        return results
    except Exception:
        return []


def get_finnhub_news(ticker: str, days: int = 5, api_key: Optional[str] = None) -> List[Dict]:
    api_key = api_key or os.getenv("FINNHUB_API_KEY", "")
    if not api_key:
        return []
    try:
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        url = "https://finnhub.io/api/v1/company-news"
        params = {
            "symbol": ticker,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "token": api_key,
        }
        r = requests.get(url, params=params, timeout=8)
        if r.status_code == 200:
            return [
                {
                    "title": it.get("headline", ""),
                    "publisher": it.get("source", "Finnhub"),
                    "link": it.get("url", ""),
                    "source": "finnhub",
                }
                for it in (r.json() or [])[:12]
                if it.get("headline")
            ]
    except Exception:
        pass
    return []


def _parse_rss(url: str, source_name: str, max_items: int = 12) -> List[Dict]:
    if feedparser is None:
        return []
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            title = entry.get("title", "") or ""
            if not title:
                continue
            items.append({
                "title": title,
                "publisher": source_name,
                "link": entry.get("link", ""),
                "source": source_name.lower().replace(" ", "_"),
            })
        return items
    except Exception:
        return []


def get_yahoo_rss(ticker: str) -> List[Dict]:
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    return _parse_rss(url, "Yahoo RSS")


def get_google_news_ru(ticker: str, company_hint: str = "") -> List[Dict]:
    """Google News RSS search in Russian."""
    q = f"{ticker} акция OR акция {ticker}"
    if company_hint:
        q = f"{ticker} OR {company_hint}"
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=ru&gl=RU&ceid=RU:ru"
    return _parse_rss(url, "Google News RU", max_items=10)


def get_rbc_rss() -> List[Dict]:
    """General RBC economics / markets feed."""
    urls = [
        "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
        "https://rssexport.rbc.ru/rbcnews/news/20/full.rss",
    ]
    items = []
    for u in urls:
        items.extend(_parse_rss(u, "RBC", max_items=15))
        if items:
            break
    return items


def get_interfax_rss() -> List[Dict]:
    urls = [
        "https://www.interfax.ru/rss.asp",
        "https://www.interfax.ru/rss.asp?id=business",
    ]
    items = []
    for u in urls:
        items.extend(_parse_rss(u, "Interfax", max_items=12))
        if items:
            break
    return items


def get_finam_news_rss() -> List[Dict]:
    """Finam market news RSS (if available)."""
    urls = [
        "https://www.finam.ru/analysis/nslent/rss.asp",
        "https://www.finam.ru/international/advanced/rsspoint/",
    ]
    items = []
    for u in urls:
        items.extend(_parse_rss(u, "Finam", max_items=12))
        if items:
            break
    return items


def get_smartlab_rss() -> List[Dict]:
    urls = [
        "https://smart-lab.ru/rss/news/",
        "https://smart-lab.ru/rss/",
    ]
    items = []
    for u in urls:
        items.extend(_parse_rss(u, "Smart-Lab", max_items=12))
        if items:
            break
    return items


def get_kommersant_rss() -> List[Dict]:
    urls = [
        "https://www.kommersant.ru/RSS/news.xml",
        "https://www.kommersant.ru/RSS/corp.xml",
    ]
    items = []
    for u in urls:
        items.extend(_parse_rss(u, "Kommersant", max_items=10))
        if items:
            break
    return items


def get_vedomosti_rss() -> List[Dict]:
    urls = [
        "https://www.vedomosti.ru/rss/news",
        "https://www.vedomosti.ru/rss/companies",
    ]
    items = []
    for u in urls:
        items.extend(_parse_rss(u, "Vedomosti", max_items=10))
        if items:
            break
    return items


# Mapping ticker -> common Russian company name for better search
TICKER_NAMES = {
    "SBER": "Сбербанк",
    "SBERP": "Сбербанк",
    "GAZP": "Газпром",
    "LKOH": "Лукойл",
    "ROSN": "Роснефть",
    "NVTK": "Новатэк",
    "GMKN": "Норникель",
    "YDEX": "Яндекс",
    "T": "Т-Банк OR Т-Технологии",
    "VTBR": "ВТБ",
    "MGNT": "Магнит",
    "ALRS": "Алроса",
    "CHMF": "Северсталь",
    "NLMK": "НЛМК",
    "PLZL": "Полюс",
    "TATN": "Татнефть",
    "SNGS": "Сургутнефтегаз",
    "MTSS": "МТС",
    "MOEX": "Московская биржа",
    "IRAO": "Интер РАО",
    "HYDR": "РусГидро",
    "FEES": "ФСК ЕЭС OR Россети",
    "PIKK": "ПИК",
    "AFLT": "Аэрофлот",
    "AFKS": "АФК Система",
    "PHOR": "ФосАгро",
    "OZON": "Ozon",
    "MAGN": "ММК",
    "RUAL": "Русал",
}


def _filter_relevant(items: List[Dict], ticker: str, company: str) -> List[Dict]:
    """Keep only items that mention ticker or company name."""
    if not items:
        return []
    keys = [ticker.lower()]
    if company:
        keys.extend([w.lower() for w in re.split(r"\s+OR\s+|\s+", company) if len(w) > 2])
    relevant = []
    for it in items:
        title_l = (it.get("title") or "").lower()
        if any(k in title_l for k in keys):
            relevant.append(it)
    return relevant


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def aggregate_news(
    ticker: str,
    sources: Optional[List[str]] = None,
    finnhub_key: Optional[str] = None,
    general_market_news: bool = True,
) -> List[Dict]:
    """
    Collect news for a ticker from multiple sources.
    sources examples: ["rss", "rbc", "interfax", "finam", "smartlab",
                       "kommersant", "vedomosti", "google", "yfinance", "finnhub"]
    """
    sources = sources or ["rss", "google", "rbc", "interfax", "finam", "smartlab"]
    sources = [s.lower() for s in sources]
    company = TICKER_NAMES.get(ticker.upper(), "")

    all_news: List[Dict] = []

    # Per-ticker sources
    if "yfinance" in sources:
        all_news.extend(get_yfinance_news(ticker))
    if "finnhub" in sources:
        all_news.extend(get_finnhub_news(ticker, api_key=finnhub_key))
    if "rss" in sources or "yahoo" in sources:
        all_news.extend(get_yahoo_rss(ticker))
    if "google" in sources:
        all_news.extend(get_google_news_ru(ticker, company))

    # General market feeds → filter by ticker/company mention
    general: List[Dict] = []
    if general_market_news:
        if "rbc" in sources:
            general.extend(get_rbc_rss())
        if "interfax" in sources:
            general.extend(get_interfax_rss())
        if "finam" in sources:
            general.extend(get_finam_news_rss())
        if "smartlab" in sources:
            general.extend(get_smartlab_rss())
        if "kommersant" in sources:
            general.extend(get_kommersant_rss())
        if "vedomosti" in sources:
            general.extend(get_vedomosti_rss())

    if general:
        all_news.extend(_filter_relevant(general, ticker, company))

    # Deduplicate by title
    seen = set()
    unique = []
    for n in all_news:
        title = (n.get("title") or "").strip()
        if title and title not in seen:
            seen.add(title)
            unique.append(n)
    return unique
