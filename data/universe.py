"""MOEX universe providers: shares (TQBR) + futures (FORTS)."""

from __future__ import annotations
from typing import List, Dict, Tuple
from datetime import date
import requests

MOEX_BLUE_CHIPS = [
    "SBER", "GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "YDEX", "T",
    "VTBR", "MGNT", "ALRS", "CHMF", "NLMK", "PLZL", "TATN", "SNGS",
    "MTSS", "MOEX", "IRAO", "HYDR", "FEES", "PIKK", "AFLT", "AFKS",
    "PHOR", "SBERP", "TATNP", "SNGSP", "TRNFP", "MAGN", "RTKM",
    "CBOM", "BSPB", "RUAL", "OZON", "POSI", "ENPG",
]

# Liquid FORTS asset codes (MOEX ASSETCODE)
# Index / FX / commodity + stock futures
FORTS_ASSET_CODES = [
    "Si",    # USD/RUB
    "RTS",   # RTS index
    "MIX",   # MOEX index
    "BR",    # Brent
    "GOLD",  # Gold
    "NG",    # Natural gas
    "Eu",    # EUR/RUB
    "ED",    # EUR/USD
    "SBRF",  # Sber futures
    "GAZR",  # Gazprom futures
    "LKOH",  # Lukoil futures
    "ROSN",  # Rosneft futures
    "VTBR",  # VTB futures
    "GMKR",  # Nornickel futures (code may vary)
    "YNDX",  # Yandex futures if listed
    "CNY",   # CNY/RUB if listed
]

# Human-readable names for Telegram / UI
FORTS_NAMES = {
    "Si": "USD/RUB",
    "RTS": "Индекс RTS",
    "MIX": "Индекс МосБиржи",
    "BR": "Brent",
    "GOLD": "Золото",
    "NG": "Газ NG",
    "Eu": "EUR/RUB",
    "ED": "EUR/USD",
    "SBRF": "Фьюч. Сбер",
    "GAZR": "Фьюч. Газпром",
    "LKOH": "Фьюч. Лукойл",
    "ROSN": "Фьюч. Роснефть",
    "VTBR": "Фьюч. ВТБ",
    "GMKR": "Фьюч. Норникель",
    "YNDX": "Фьюч. Яндекс",
    "CNY": "CNY/RUB",
}


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


def resolve_forts_front_contracts(
    asset_codes: List[str] | None = None,
) -> Dict[str, Dict]:
    """
    Resolve nearest liquid futures contract per asset by open interest.
    Returns: {SECID: {asset, shortname, expiry, oi, last}}
    """
    asset_codes = asset_codes or FORTS_ASSET_CODES
    today = date.today().isoformat()
    result: Dict[str, Dict] = {}
    try:
        url = "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json"
        r = requests.get(
            url,
            params={"iss.meta": "off", "iss.only": "securities,marketdata"},
            timeout=20,
        )
        r.raise_for_status()
        j = r.json()
        sc = j["securities"]["columns"]
        sd = j["securities"]["data"]
        mc = j["marketdata"]["columns"]
        md = j["marketdata"]["data"]

        oi_map: Dict[str, Tuple] = {}
        for row in md:
            d = dict(zip(mc, row))
            sid = d.get("SECID")
            if sid:
                oi_map[sid] = (
                    d.get("OPENPOSITION") or 0,
                    d.get("VOLTODAY") or 0,
                    d.get("LAST"),
                )

        by_asset: Dict[str, list] = {a: [] for a in asset_codes}
        for row in sd:
            d = dict(zip(sc, row))
            ac = d.get("ASSETCODE")
            ltd = d.get("LASTTRADEDATE") or ""
            sid = d.get("SECID")
            if not sid or ac not in by_asset:
                continue
            if ltd < today:
                continue
            oi, vol, last = oi_map.get(sid, (0, 0, None))
            by_asset[ac].append(
                {
                    "secid": sid,
                    "asset": ac,
                    "shortname": d.get("SHORTNAME") or sid,
                    "expiry": ltd,
                    "oi": int(oi or 0),
                    "volume": int(vol or 0),
                    "last": last,
                }
            )

        for ac, items in by_asset.items():
            if not items:
                continue
            # Prefer max open interest, then nearest expiry
            items.sort(key=lambda x: (-x["oi"], x["expiry"]))
            best = items[0]
            result[best["secid"]] = best
            print(
                f"  [forts] {ac:5} → {best['secid']:6} "
                f"{best['shortname']:12} exp={best['expiry']} OI={best['oi']}"
            )
    except Exception as e:
        print(f"[universe] FORTS resolve failed: {e}")
    return result


def get_moex_futures() -> List[str]:
    """Front-month SECID list for liquid FORTS assets."""
    contracts = resolve_forts_front_contracts()
    if contracts:
        return list(contracts.keys())
    # Fallback static (may be stale after roll)
    return ["SiU6", "RIU6", "MXU6", "BRQ6", "GDU6", "EuU6", "SRU6", "GZU6"]


def get_moex_mixed() -> List[str]:
    """Blue chips + liquid futures front contracts."""
    shares = get_moex_sample()
    futs = get_moex_futures()
    # Avoid duplicate display if same symbol space (unlikely)
    return shares + [t for t in futs if t not in shares]


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
    if name in ("futures", "forts", "fut"):
        return get_moex_futures()
    if name in ("mixed", "all_instruments", "shares_futures"):
        return get_moex_mixed()
    return get_moex_sample()


def classify_instrument(secid: str) -> str:
    """Return 'futures' or 'share' for routing data fetch."""
    # FORTS SECIDs typically end with month code letter+digit (e.g. SiU6, BRQ6)
    if not secid:
        return "share"
    # Known share tickers are mostly letters only (SBER, GAZP) or with P suffix
    if secid in MOEX_BLUE_CHIPS or (secid.isalpha() and len(secid) <= 5):
        return "share"
    # Pattern: letters + month letter + year digit(s)
    import re
    if re.match(r"^[A-Za-z]{1,5}[FGHJKMNQUVXZ]\d{1,2}$", secid):
        return "futures"
    if any(c.isdigit() for c in secid):
        return "futures"
    return "share"
