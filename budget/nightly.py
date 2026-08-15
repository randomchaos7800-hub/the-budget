"""Nightly reality pass.

Crystallize past scheduled transactions into the ledger, recompute
spendable, and fail loudly if runway dropped.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from .engine import RecurrenceEngine, SimulationStatus
from .spendable import spendable_today
from .store import Store


@dataclass
class NightlyReport:
    ran_at: str
    today: str
    crystallized: int
    skipped: int
    spendable: float
    previous_spendable: float | None
    runway_days: int | None
    previous_runway: int | None
    min_balance: float
    min_date: str | None
    health: str
    alerts: list[str]


def run_nightly(store: Store, today: date | None = None) -> NightlyReport:
    assumptions = store.assumptions()
    today = today or datetime.now(assumptions.zone).date()
    crystallized, skipped = crystallize(store, today)
    templates = store.templates()
    states = store.states()
    balance = store.current_balance()
    result = spendable_today(balance, today, templates, states, assumptions)
    previous = store.last_nightly()
    prev_spendable = float(previous["spendable"]) if previous else None
    prev_runway = previous["runway_days"] if previous else None
    alerts: list[str] = []

    if result.health == "danger":
        msg = (
            f"Projection goes negative"
            f"{' on ' + result.first_negative_date.isoformat() if result.first_negative_date else ''}."
        )
        store.add_alert("danger", msg, {"min_balance": result.min_balance})
        alerts.append(msg)
    elif result.runway_days is not None and result.runway_days < 90:
        msg = f"Runway dropped to {result.runway_days} days."
        store.add_alert("runway", msg, {"runway_days": result.runway_days})
        alerts.append(msg)

    if prev_spendable is not None and result.amount < prev_spendable - 25:
        msg = f"Spendable today fell from ${prev_spendable:,.2f} to ${result.amount:,.2f}."
        store.add_alert(
            "spendable_drop",
            msg,
            {"from": prev_spendable, "to": result.amount},
        )
        alerts.append(msg)

    store.log_nightly(
        crystallized=crystallized,
        spendable=result.amount,
        runway_days=result.runway_days,
        min_balance=result.min_balance,
        health=result.health,
    )
    return NightlyReport(
        ran_at=datetime.now().isoformat(timespec="seconds"),
        today=today.isoformat(),
        crystallized=crystallized,
        skipped=skipped,
        spendable=result.amount,
        previous_spendable=prev_spendable,
        runway_days=result.runway_days,
        previous_runway=prev_runway,
        min_balance=result.min_balance,
        min_date=result.min_date.isoformat() if result.min_date else None,
        health=result.health,
        alerts=alerts,
    )


def crystallize(store: Store, today: date) -> tuple[int, int]:
    """Write past scheduled/skipped occurrences into the ledger.

    Does not rewrite today. Past only. Matches iOS LedgerService.applyPastTransactions.
    """
    anchor = store.anchor()
    if anchor is None:
        return 0, 0
    _amount, anchor_date = anchor
    if anchor_date >= today:
        return 0, 0

    assumptions = store.assumptions()
    recurrence = RecurrenceEngine(assumptions)
    templates = store.templates()
    skip_forever, skip_once = _skip_lookup(store.states())
    existing = store.ledger_key_set()
    created = 0
    skipped = 0
    current = anchor_date + timedelta(days=1)
    while current < today:
        for template in templates:
            if not recurrence.is_scheduled(current, template):
                continue
            was_skipped = _skipped(template.id, current, skip_forever, skip_once)
            entry_type = "skipped" if was_skipped else "scheduled"
            key = f"{template.id}|{current.isoformat()}|{entry_type}"
            if key in existing:
                continue
            store.add_ledger(
                {
                    "date": current.isoformat(),
                    "amount": 0.0 if was_skipped else template.effective_amount,
                    "entry_type": entry_type,
                    "template_id": str(template.id),
                    "template_name": template.name,
                    "scheduled_date": current.isoformat(),
                    "note": "crystallized" if not was_skipped else "skipped",
                }
            )
            existing.add(key)
            created += 1
            if was_skipped:
                skipped += 1
        current += timedelta(days=1)
    return created, skipped


def _skip_lookup(states):
    forever = {}
    once = {}
    for state in states:
        if state.status is SimulationStatus.SKIP_FOREVER:
            existing = forever.get(state.template_id)
            forever[state.template_id] = (
                state.date if existing is None else min(existing, state.date)
            )
        elif state.status is SimulationStatus.SKIP_ONCE:
            once.setdefault(state.template_id, set()).add(state.date)
    return forever, once


def _skipped(template_id: UUID, current: date, forever, once) -> bool:
    stop = forever.get(template_id)
    if stop is not None and current >= stop:
        return True
    return current in once.get(template_id, set())


def report_json(report: NightlyReport) -> dict:
    return asdict(report)
