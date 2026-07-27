"""MOEX (Moscow Exchange) universe providers."""

from __future__ import annotations
from typing import List
import requests

MOEX_BLUE_CHIPS = [
    "SBER", "GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "YDEX", "T",
    "VTBR", "MGNT", "ALRS", "CHMF", "NLMK", "PLZL", "TATN", "SNGS",
    "MTSS", "MOEX", "IRAO", "HYDR", "FEES", "PIKK", "AFLT", "AFKS",
    "PHOR", "SBERP", "TATNP", "SNGSP", "TRNFP", "MAGN", "RTKM",
    "CBOM", "BSPB", "RUAL", "OZON", "POSI", "ENPG",
]


def get_moex_sample() -> List[str]:
    return MOEX_BLUE_CHIPS[:25].copy()


def get_moex_blue_chips() -> List[str]:
    return MOEX_BLUE_CHIPS.copy()


def get_moex_tqbr_all(limit: int = 80) -> List[str]:
    try:
        url = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
        params = {
            "iss.meta": "off",
            "iss.only": "securities",
            "securities.columns": "SECID,SHORTNAME,LISTLEVEL",
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        j = r.json()
        cols = j["securities"]["columns"]
        data = j["securities"]["data"]
        tickers = []
        for row in data:
            d = dict(zip(cols, row))
            secid = d.get("SECID")
            level = d.get("LISTLEVEL")
            if secid and (level is None or int(level or 99) <= 2):
                tickers.append(secid)
        return tickers[:limit] if limit else tickers
    except Exception as e:
        print(f"[universe] MOEX ISS list failed: {e}. Using blue chips.")
        return get_moex_blue_chips()


def get_universe(name: str = "sample") -> List[str]:
    name = (name or "sample").lower()
    if name in ("sample", "demo"):
        return get_moex_sample()
    if name in ("blue", "bluechips", "moexbc"):
        return get_moex_blue_chips()
    if name in ("tqbr", "all", "moex"):
        return get_moex_tqbr_all(60)
    if name == "full":
        return get_moex_tqbr_all(120)
    return get_moex_sample()
