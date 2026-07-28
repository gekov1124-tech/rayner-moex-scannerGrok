"""MOEX trading session helpers (Moscow time)."""

from __future__ import annotations
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    return datetime.now(MSK)


def is_weekday(dt: datetime | None = None) -> bool:
    dt = dt or now_msk()
    return dt.weekday() < 5  # Mon=0 .. Fri=4


def is_session_open(
    dt: datetime | None = None,
    start: str = "10:00",
    end: str = "18:50",
) -> bool:
    """
    Main MOEX equity session roughly 10:00–18:40 MSK.
    Futures trade longer; default window covers cash + late main session.
    """
    dt = dt or now_msk()
    if not is_weekday(dt):
        return False
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    t = dt.time()
    return time(sh, sm) <= t <= time(eh, em)


def seconds_until_next_open(start: str = "10:00") -> int:
    dt = now_msk()
    sh, sm = map(int, start.split(":"))
    target = dt.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if dt.time() >= time(sh, sm) or not is_weekday(dt):
        # next weekday
        days = 1
        while True:
            candidate = (dt + timedelta(days=days)).replace(
                hour=sh, minute=sm, second=0, microsecond=0
            )
            if candidate.weekday() < 5:
                target = candidate
                break
            days += 1
    elif dt < target:
        pass
    else:
        target = target + timedelta(days=1)
        while target.weekday() >= 5:
            target += timedelta(days=1)
    return max(0, int((target - dt).total_seconds()))


def session_status(start: str = "10:00", end: str = "18:50") -> dict:
    dt = now_msk()
    open_ = is_session_open(dt, start, end)
    return {
        "msk_now": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "weekday": is_weekday(dt),
        "session_open": open_,
        "session_start": start,
        "session_end": end,
        "seconds_to_open": 0 if open_ else seconds_until_next_open(start),
    }
