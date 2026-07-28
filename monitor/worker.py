"""
Background monitor: scan during session, Telegram only on NEW signals.
"""

from __future__ import annotations
import json
import os
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from monitor.session import is_session_open, now_msk, session_status
from journal.store import JournalStore
from journal.tracker import update_open_trades

ROOT = Path(__file__).resolve().parent.parent
SEEN_FILE = ROOT / "cache" / "seen_signals.json"


class MarketMonitor:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.enabled = True
        self.interval_minutes = 30
        self.session_start = "10:00"
        self.session_end = "18:50"
        self.universe = "mixed"
        self.no_news = True
        self.last_scan_at: Optional[str] = None
        self.last_scan_count = 0
        self.last_new_count = 0
        self.last_error: Optional[str] = None
        self.last_setups: list = []
        self.running = False
        self._seen: Set[str] = set()
        self._load_seen()

    def configure_from_cfg(self, cfg: dict):
        m = cfg.get("monitor") or {}
        self.enabled = bool(m.get("enabled", True))
        self.interval_minutes = int(m.get("interval_minutes", 30))
        self.session_start = m.get("session_start", "10:00")
        self.session_end = m.get("session_end", "18:50")
        self.universe = m.get("universe") or cfg.get("universe") or "mixed"
        self.no_news = bool(m.get("no_news", True))

    def _load_seen(self):
        try:
            SEEN_FILE.parent.mkdir(exist_ok=True)
            if SEEN_FILE.exists():
                data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
                # keep only today's keys
                today = now_msk().strftime("%Y-%m-%d")
                self._seen = {k for k in data if k.startswith(today)}
        except Exception:
            self._seen = set()

    def _save_seen(self):
        try:
            SEEN_FILE.parent.mkdir(exist_ok=True)
            SEEN_FILE.write_text(
                json.dumps(sorted(self._seen), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def signal_key(s) -> str:
        day = now_msk().strftime("%Y-%m-%d")
        return f"{day}|{s.ticker}|{s.strategy}|{s.direction}|{round(float(s.entry), 4)}"

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="moex-monitor", daemon=True)
        self._thread.start()
        print("[monitor] background thread started")

    def stop(self):
        self._stop.set()

    def status(self) -> dict:
        st = session_status(self.session_start, self.session_end)
        return {
            **st,
            "monitor_enabled": self.enabled,
            "monitor_running": bool(self._thread and self._thread.is_alive()),
            "interval_minutes": self.interval_minutes,
            "universe": self.universe,
            "last_scan_at": self.last_scan_at,
            "last_scan_count": self.last_scan_count,
            "last_new_count": self.last_new_count,
            "last_error": self.last_error,
            "seen_today": len(self._seen),
        }

    def run_once(self, force: bool = False, send_telegram: bool = True) -> dict:
        """
        Single scan cycle. If force=False, skip outside session.
        Returns dict with setups / new_setups counts.
        """
        if not force and not is_session_open(
            start=self.session_start, end=self.session_end
        ):
            return {"skipped": True, "reason": "outside_session", "new": 0, "total": 0}

        from main import run_scan

        try:
            setups, log = run_scan(
                universe=self.universe,
                source="moex",
                no_news=self.no_news,
                max_setups=25,
                send_telegram=False,  # we handle TG ourselves for "new only"
            )
        except Exception as e:
            self.last_error = str(e)
            traceback.print_exc()
            return {"error": str(e), "new": 0, "total": 0}

        self.last_scan_at = now_msk().strftime("%Y-%m-%d %H:%M:%S MSK")
        self.last_scan_count = len(setups)
        self.last_setups = setups
        self.last_error = None

        new_setups = []
        for s in setups:
            key = self.signal_key(s)
            if key not in self._seen:
                new_setups.append(s)
        self.last_new_count = len(new_setups)

        tg_ok = False
        if send_telegram and new_setups:
            try:
                from notify.telegram_alerts import send_setups_alert, is_telegram_configured
                if is_telegram_configured():
                    tg_ok = send_setups_alert(
                        new_setups,
                        title=f"🔔 Новые сэтапы MOEX ({self.last_scan_at})",
                    )
                    print(f"[monitor] Telegram new setups: {len(new_setups)} sent={tg_ok}")
                else:
                    print("[monitor] Telegram НЕ настроен — сэтапы не отправлены")
            except Exception as e:
                print(f"[monitor] Telegram error: {e}")
                tg_ok = False

        # Mark as seen ONLY after successful send (or if TG disabled / not configured)
        # so a failed send can be retried next cycle
        from notify.telegram_alerts import is_telegram_configured
        if new_setups:
            if tg_ok or not send_telegram or not is_telegram_configured():
                for s in new_setups:
                    self._seen.add(self.signal_key(s))
                self._save_seen()
            else:
                print("[monitor] Сэтапы НЕ помечены seen — повторная попытка в следующем цикле")

        # Paper journal: open virtual trades + update MTM / exits
        try:
            from main import load_config
            from data.moex_fetcher import fetch_ohlcv
            from data.universe import classify_instrument
            jcfg = (load_config().get("journal") or {})
            if jcfg.get("enabled", True):
                store = JournalStore()
                day = now_msk().strftime("%Y-%m-%d")
                opened = 0
                for s in setups:
                    if store.add_from_setup(s, day):
                        opened += 1
                # refresh prices for open tickers
                open_tickers = list({t.ticker for t in store.open_trades()})
                if open_tickers:
                    fut = {x for x in open_tickers if classify_instrument(x) == "futures"}
                    pdata = fetch_ohlcv(
                        open_tickers, source="moex", lookback_days=120,
                        use_cache=True, futures_tickers=fut,
                    )
                    closed = update_open_trades(store, pdata)
                    if closed and send_telegram:
                        try:
                            from notify.telegram_alerts import send_telegram_message, is_telegram_configured
                            if is_telegram_configured():
                                lines = [f"<b>📒 Закрыты виртуальные сделки: {len(closed)}</b>"]
                                for ct in closed[:10]:
                                    sign = "+" if ct.pnl >= 0 else ""
                                    lines.append(
                                        f"{ct.ticker} {ct.strategy}: {sign}{ct.pnl:.0f} "
                                        f"({ct.pnl_pct*100:.1f}%) · {ct.exit_reason}"
                                    )
                                send_telegram_message("\n".join(lines))
                        except Exception as e:
                            print("[journal] TG close alert", e)
                    print(f"[journal] opened={opened} open_now={len(store.open_trades())} closed_now={len(closed)}")
        except Exception as e:
            print(f"[journal] error: {e}")

        return {
            "skipped": False,
            "total": len(setups),
            "new": len(new_setups),
            "setups": setups,
            "new_setups": new_setups,
            "log": log,
            "at": self.last_scan_at,
        }

    def _loop(self):
        self.running = True
        # small delay so Flask can bind port first
        time.sleep(5)
        while not self._stop.is_set():
            try:
                if self.enabled and is_session_open(
                    start=self.session_start, end=self.session_end
                ):
                    print(f"[monitor] session open → scan ({self.universe})")
                    self.run_once(force=True, send_telegram=True)
                else:
                    st = session_status(self.session_start, self.session_end)
                    print(
                        f"[monitor] session closed (MSK {st['msk_now']}), "
                        f"sleep {self.interval_minutes}m"
                    )
            except Exception as e:
                self.last_error = str(e)
                print(f"[monitor] loop error: {e}")
                traceback.print_exc()

            # sleep in chunks so stop is responsive
            for _ in range(max(1, self.interval_minutes * 6)):
                if self._stop.is_set():
                    break
                time.sleep(10)
        self.running = False
        print("[monitor] stopped")


# Singleton
monitor = MarketMonitor()
