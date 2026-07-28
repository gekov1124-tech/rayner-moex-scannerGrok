"""Persistent paper-trade journal (JSON + CSV)."""

from __future__ import annotations
import csv
import json
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
JOURNAL_DIR = ROOT / "output" / "journal"
JOURNAL_JSON = JOURNAL_DIR / "trades.json"
JOURNAL_CSV = JOURNAL_DIR / "trades.csv"


@dataclass
class PaperTrade:
    id: str
    ticker: str
    strategy: str
    direction: str
    status: str  # open | closed | cancelled
    signal_date: str
    entry_date: str
    entry_price: float
    stop: float
    exit_rule: str
    shares: int
    risk_amount: float
    score: float = 0.0
    reason: str = ""
    exit_date: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0
    bars_held: int = 0
    notes: str = ""
    scale_plan: str = ""
    mtm_price: float = 0.0
    mtm_pnl: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PaperTrade":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore
        return cls(**{k: v for k, v in d.items() if k in known})


class JournalStore:
    def __init__(self, path: Path = JOURNAL_JSON):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.trades: List[PaperTrade] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.trades = [PaperTrade.from_dict(x) for x in raw]
            except Exception as e:
                print(f"[journal] load error: {e}")
                self.trades = []
        else:
            self.trades = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [t.to_dict() for t in self.trades]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._export_csv()

    def _export_csv(self) -> None:
        if not self.trades:
            return
        keys = list(self.trades[0].to_dict().keys())
        with open(JOURNAL_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for t in self.trades:
                w.writerow(t.to_dict())

    def open_trades(self) -> List[PaperTrade]:
        return [t for t in self.trades if t.status == "open"]

    def closed_trades(self) -> List[PaperTrade]:
        return [t for t in self.trades if t.status == "closed"]

    def find_open(self, ticker: str, strategy: str, direction: str) -> Optional[PaperTrade]:
        for t in self.open_trades():
            if t.ticker == ticker and t.strategy == strategy and t.direction == direction:
                return t
        return None

    def add_from_setup(self, setup, signal_date: str) -> Optional[PaperTrade]:
        """Open paper trade from scanner Setup; skip if same key already open."""
        if self.find_open(setup.ticker, setup.strategy, setup.direction):
            return None
        trade = PaperTrade(
            id=str(uuid.uuid4())[:8],
            ticker=setup.ticker,
            strategy=setup.strategy,
            direction=setup.direction,
            status="open",
            signal_date=signal_date,
            entry_date=signal_date,
            entry_price=float(setup.entry),
            stop=float(setup.stop),
            exit_rule=setup.exit_rule or "",
            shares=int(setup.suggested_shares or 1),
            risk_amount=float(setup.risk_amount or 0),
            score=float(setup.score or 0),
            reason=setup.reason or "",
            scale_plan=getattr(setup, "scale_plan", "") or "",
            mtm_price=float(setup.entry),
        )
        self.trades.append(trade)
        self.save()
        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_date: str,
        exit_reason: str,
        bars_held: int = 0,
    ) -> Optional[PaperTrade]:
        for t in self.trades:
            if t.id == trade_id and t.status == "open":
                t.status = "closed"
                t.exit_price = float(exit_price)
                t.exit_date = exit_date
                t.exit_reason = exit_reason
                t.bars_held = bars_held
                if t.direction == "long":
                    t.pnl = (t.exit_price - t.entry_price) * t.shares
                    t.pnl_pct = (t.exit_price / t.entry_price - 1.0) if t.entry_price else 0
                else:
                    t.pnl = (t.entry_price - t.exit_price) * t.shares
                    t.pnl_pct = (t.entry_price / t.exit_price - 1.0) if t.exit_price else 0
                t.mtm_price = t.exit_price
                t.mtm_pnl = t.pnl
                self.save()
                return t
        return None
