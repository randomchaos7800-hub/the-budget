"""SQLite store. File-based. One household. No cloud."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .engine import (
    CashFlowCategory,
    Frequency,
    ModelAssumptions,
    RoundingMode,
    SimulationStatus,
    StateSnapshot,
    TemplateSnapshot,
    TransactionOrdering,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    frequency TEXT NOT NULL,
    anchor_date TEXT NOT NULL,
    category TEXT NOT NULL,
    min_amount REAL,
    max_amount REAL,
    is_estimate INTEGER NOT NULL DEFAULT 0,
    source_scenario TEXT
);
CREATE TABLE IF NOT EXISTS states (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    date TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    entry_type TEXT NOT NULL,
    template_id TEXT,
    template_name TEXT,
    scheduled_date TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS anchors (
    id TEXT PRIMARY KEY,
    amount REAL NOT NULL,
    date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_amount REAL NOT NULL,
    target_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    frequency TEXT NOT NULL,
    anchor_date TEXT NOT NULL,
    category TEXT NOT NULL,
    min_amount REAL,
    max_amount REAL,
    confidence REAL NOT NULL,
    source TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT NOT NULL,
    acked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nightly_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at TEXT NOT NULL,
    crystallized INTEGER NOT NULL,
    spendable REAL NOT NULL,
    runway_days INTEGER,
    min_balance REAL NOT NULL,
    health TEXT NOT NULL
);
"""


def _d(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])


def _uuid(value: str | UUID | None = None) -> str:
    return str(value or uuid4())


@dataclass
class LedgerEntry:
    id: str
    date: date
    amount: float
    entry_type: str
    template_id: str | None = None
    template_name: str | None = None
    scheduled_date: date | None = None
    note: str | None = None


@dataclass
class Goal:
    id: str
    name: str
    target_amount: float
    target_date: date


@dataclass
class Proposal:
    id: str
    name: str
    amount: float
    frequency: Frequency
    anchor_date: date
    category: CashFlowCategory
    min_amount: float | None
    max_amount: float | None
    confidence: float
    source: str
    sample_count: int
    status: str
    reason: str | None


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def assumptions(self) -> ModelAssumptions:
        raw = self._settings()
        return ModelAssumptions(
            timezone=raw.get("timezone", "America/Los_Angeles"),
            transaction_ordering=TransactionOrdering(
                raw.get("transaction_ordering", "incomeFirst")
            ),
            rounding_mode=RoundingMode(raw.get("rounding_mode", "nearest")),
            projection_days=int(raw.get("projection_days", 365)),
            warning_threshold=float(raw.get("warning_threshold", 500)),
            danger_threshold=float(raw.get("danger_threshold", 0)),
            safety_floor=float(raw.get("safety_floor", 0)),
        )

    def update_settings(self, values: dict[str, Any]) -> ModelAssumptions:
        allowed = {
            "timezone",
            "transaction_ordering",
            "rounding_mode",
            "projection_days",
            "warning_threshold",
            "danger_threshold",
            "safety_floor",
        }
        for key, value in values.items():
            if key not in allowed:
                continue
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
        self.conn.commit()
        return self.assumptions()

    def _settings(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def templates(self) -> list[TemplateSnapshot]:
        rows = self.conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
        return [self._template(r) for r in rows]

    def get_template(self, template_id: str) -> TemplateSnapshot | None:
        row = self.conn.execute(
            "SELECT * FROM templates WHERE id=?", (template_id,)
        ).fetchone()
        return self._template(row) if row else None

    def upsert_template(self, payload: dict[str, Any]) -> TemplateSnapshot:
        tid = _uuid(payload.get("id"))
        amount = float(payload["amount"])
        min_amount = payload.get("min_amount")
        max_amount = payload.get("max_amount")
        category = CashFlowCategory.parse(payload.get("category"), amount)
        freq = Frequency.parse(payload["frequency"])
        self.conn.execute(
            """
            INSERT INTO templates(id, name, amount, frequency, anchor_date, category,
                                  min_amount, max_amount, is_estimate, source_scenario)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, amount=excluded.amount, frequency=excluded.frequency,
                anchor_date=excluded.anchor_date, category=excluded.category,
                min_amount=excluded.min_amount, max_amount=excluded.max_amount,
                is_estimate=excluded.is_estimate, source_scenario=excluded.source_scenario
            """,
            (
                tid,
                payload["name"].strip(),
                amount,
                freq.value,
                _d(payload["anchor_date"]).isoformat(),
                category.value,
                None if min_amount in (None, "") else float(min_amount),
                None if max_amount in (None, "") else float(max_amount),
                1 if payload.get("is_estimate") else 0,
                payload.get("source_scenario"),
            ),
        )
        self.conn.commit()
        found = self.get_template(tid)
        assert found is not None
        return found

    def delete_template(self, template_id: str) -> None:
        self.conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        self.conn.execute("DELETE FROM states WHERE template_id=?", (template_id,))
        self.conn.commit()

    def states(self) -> list[StateSnapshot]:
        rows = self.conn.execute("SELECT * FROM states").fetchall()
        return [
            StateSnapshot(
                template_id=UUID(r["template_id"]),
                date=_d(r["date"]),
                status=SimulationStatus(r["status"]),
            )
            for r in rows
        ]

    def set_state(self, template_id: str, when: date, status: SimulationStatus) -> None:
        existing = self.conn.execute(
            "SELECT id FROM states WHERE template_id=? AND date=?",
            (template_id, when.isoformat()),
        ).fetchone()
        if status is SimulationStatus.STANDARD:
            if existing:
                self.conn.execute("DELETE FROM states WHERE id=?", (existing["id"],))
        elif existing:
            self.conn.execute(
                "UPDATE states SET status=? WHERE id=?", (status.value, existing["id"])
            )
        else:
            self.conn.execute(
                "INSERT INTO states(id, template_id, date, status) VALUES(?,?,?,?)",
                (_uuid(), template_id, when.isoformat(), status.value),
            )
        self.conn.commit()

    def clear_plan(self, reference: date, include_today: bool = True) -> int:
        cutoff = reference.isoformat()
        if include_today:
            cur = self.conn.execute("DELETE FROM states WHERE date >= ?", (cutoff,))
        else:
            cur = self.conn.execute("DELETE FROM states WHERE date > ?", (cutoff,))
        self.conn.commit()
        return cur.rowcount

    def reset_all_plan(self) -> int:
        cur = self.conn.execute("DELETE FROM states")
        self.conn.commit()
        return cur.rowcount

    def ledger(self) -> list[LedgerEntry]:
        rows = self.conn.execute("SELECT * FROM ledger ORDER BY date DESC, id DESC").fetchall()
        return [self._ledger(r) for r in rows]

    def add_ledger(self, payload: dict[str, Any]) -> LedgerEntry:
        lid = _uuid(payload.get("id"))
        self.conn.execute(
            """
            INSERT INTO ledger(id, date, amount, entry_type, template_id, template_name,
                               scheduled_date, note)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                lid,
                _d(payload["date"]).isoformat(),
                float(payload["amount"]),
                payload.get("entry_type", "adjustment"),
                payload.get("template_id"),
                payload.get("template_name"),
                _d(payload["scheduled_date"]).isoformat()
                if payload.get("scheduled_date")
                else None,
                payload.get("note"),
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM ledger WHERE id=?", (lid,)).fetchone()
        return self._ledger(row)

    def ledger_key_set(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT template_id, scheduled_date, date, entry_type FROM ledger"
        ).fetchall()
        keys = set()
        for r in rows:
            day = r["scheduled_date"] or r["date"]
            if r["template_id"] and day:
                keys.add(f"{r['template_id']}|{day}|{r['entry_type']}")
        return keys

    def anchor(self) -> tuple[float, date] | None:
        row = self.conn.execute(
            "SELECT amount, date FROM anchors ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return float(row["amount"]), _d(row["date"])

    def set_anchor(self, amount: float, when: date) -> None:
        self.conn.execute("DELETE FROM anchors")
        self.conn.execute(
            "INSERT INTO anchors(id, amount, date) VALUES(?,?,?)",
            (_uuid(), amount, when.isoformat()),
        )
        self.conn.commit()

    def current_balance(self) -> float:
        anchor = self.anchor()
        if anchor is None:
            return 0.0
        amount, when = anchor
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM ledger WHERE date >= ?",
            (when.isoformat(),),
        ).fetchone()
        return amount + float(row["total"])

    def goals(self) -> list[Goal]:
        rows = self.conn.execute("SELECT * FROM goals ORDER BY target_date").fetchall()
        return [
            Goal(r["id"], r["name"], float(r["target_amount"]), _d(r["target_date"]))
            for r in rows
        ]

    def upsert_goal(self, payload: dict[str, Any]) -> Goal:
        gid = _uuid(payload.get("id"))
        self.conn.execute(
            """
            INSERT INTO goals(id, name, target_amount, target_date) VALUES(?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, target_amount=excluded.target_amount,
                target_date=excluded.target_date
            """,
            (
                gid,
                payload["name"].strip(),
                float(payload["target_amount"]),
                _d(payload["target_date"]).isoformat(),
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM goals WHERE id=?", (gid,)).fetchone()
        return Goal(row["id"], row["name"], float(row["target_amount"]), _d(row["target_date"]))

    def delete_goal(self, goal_id: str) -> None:
        self.conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        self.conn.commit()

    def proposals(self, status: str | None = "pending") -> list[Proposal]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM proposals WHERE status=? ORDER BY confidence DESC",
                (status,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM proposals ORDER BY confidence DESC"
            ).fetchall()
        return [self._proposal(r) for r in rows]

    def add_proposal(self, payload: dict[str, Any]) -> Proposal:
        pid = _uuid(payload.get("id"))
        self.conn.execute(
            """
            INSERT INTO proposals(id, name, amount, frequency, anchor_date, category,
                                  min_amount, max_amount, confidence, source, sample_count,
                                  status, reason)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid,
                payload["name"],
                float(payload["amount"]),
                Frequency.parse(payload["frequency"]).value,
                _d(payload["anchor_date"]).isoformat(),
                CashFlowCategory.parse(payload.get("category"), float(payload["amount"])).value,
                payload.get("min_amount"),
                payload.get("max_amount"),
                float(payload["confidence"]),
                payload.get("source", "csv"),
                int(payload.get("sample_count", 0)),
                payload.get("status", "pending"),
                payload.get("reason"),
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        return self._proposal(row)

    def set_proposal_status(self, proposal_id: str, status: str) -> Proposal | None:
        self.conn.execute(
            "UPDATE proposals SET status=? WHERE id=?", (status, proposal_id)
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM proposals WHERE id=?", (proposal_id,)
        ).fetchone()
        return self._proposal(row) if row else None

    def clear_pending_proposals(self) -> None:
        self.conn.execute("DELETE FROM proposals WHERE status='pending'")
        self.conn.commit()

    def add_alert(self, kind: str, message: str, payload: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO alerts(id, created_at, kind, message, payload, acked) VALUES(?,?,?,?,?,0)",
            (
                _uuid(),
                datetime.now().isoformat(timespec="seconds"),
                kind,
                message,
                json.dumps(payload),
            ),
        )
        self.conn.commit()

    def alerts(self, include_acked: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM alerts"
        if not include_acked:
            sql += " WHERE acked=0"
        sql += " ORDER BY created_at DESC"
        rows = self.conn.execute(sql).fetchall()
        return [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "kind": r["kind"],
                "message": r["message"],
                "payload": json.loads(r["payload"]),
                "acked": bool(r["acked"]),
            }
            for r in rows
        ]

    def ack_alert(self, alert_id: str) -> None:
        self.conn.execute("UPDATE alerts SET acked=1 WHERE id=?", (alert_id,))
        self.conn.commit()

    def log_nightly(
        self,
        crystallized: int,
        spendable: float,
        runway_days: int | None,
        min_balance: float,
        health: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO nightly_log(ran_at, crystallized, spendable, runway_days, min_balance, health)
            VALUES(?,?,?,?,?,?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                crystallized,
                spendable,
                runway_days,
                min_balance,
                health,
            ),
        )
        self.conn.commit()

    def last_nightly(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM nightly_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def export_dict(self) -> dict[str, Any]:
        return {
            "templates": [dict(r) for r in self.conn.execute("SELECT * FROM templates")],
            "states": [dict(r) for r in self.conn.execute("SELECT * FROM states")],
            "ledger": [dict(r) for r in self.conn.execute("SELECT * FROM ledger")],
            "anchors": [dict(r) for r in self.conn.execute("SELECT * FROM anchors")],
            "goals": [dict(r) for r in self.conn.execute("SELECT * FROM goals")],
            "settings": self._settings(),
        }

    def _template(self, row: sqlite3.Row) -> TemplateSnapshot:
        return TemplateSnapshot(
            id=UUID(row["id"]),
            name=row["name"],
            amount=float(row["amount"]),
            frequency=Frequency(row["frequency"]),
            anchor_date=_d(row["anchor_date"]),
            min_amount=None if row["min_amount"] is None else float(row["min_amount"]),
            max_amount=None if row["max_amount"] is None else float(row["max_amount"]),
            category=CashFlowCategory.parse(row["category"], float(row["amount"])),
        )

    def _ledger(self, row: sqlite3.Row) -> LedgerEntry:
        return LedgerEntry(
            id=row["id"],
            date=_d(row["date"]),
            amount=float(row["amount"]),
            entry_type=row["entry_type"],
            template_id=row["template_id"],
            template_name=row["template_name"],
            scheduled_date=_d(row["scheduled_date"]) if row["scheduled_date"] else None,
            note=row["note"],
        )

    def _proposal(self, row: sqlite3.Row) -> Proposal:
        return Proposal(
            id=row["id"],
            name=row["name"],
            amount=float(row["amount"]),
            frequency=Frequency(row["frequency"]),
            anchor_date=_d(row["anchor_date"]),
            category=CashFlowCategory.parse(row["category"], float(row["amount"])),
            min_amount=None if row["min_amount"] is None else float(row["min_amount"]),
            max_amount=None if row["max_amount"] is None else float(row["max_amount"]),
            confidence=float(row["confidence"]),
            source=row["source"],
            sample_count=int(row["sample_count"]),
            status=row["status"],
            reason=row["reason"],
        )
