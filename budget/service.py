"""Application service: store + engine + automation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import csv_import
from .engine import (
    ModelAssumptions,
    SimulationStatus,
    StateSnapshot,
    TemplateSnapshot,
    active_plan_states,
    analyze_balance,
    evaluate_goal,
    evaluate_health,
    expected_balance_today,
    plan_category,
)
from .nightly import run_nightly
from .scenarios import LIBRARY, get_scenario, overlay
from .spendable import project, spendable_today
from .store import Store

DEMO = [
    {
        "name": "Paycheck",
        "amount": 2200,
        "frequency": "biWeekly",
        "anchor_date": "2026-08-07",
        "category": "Income",
    },
    {
        "name": "Rent",
        "amount": -1600,
        "frequency": "monthly",
        "anchor_date": "2026-08-01",
        "category": "Housing",
    },
    {
        "name": "Car Payment",
        "amount": -450,
        "frequency": "monthly",
        "anchor_date": "2026-08-15",
        "category": "Transportation",
    },
    {
        "name": "Auto Insurance",
        "amount": -180,
        "frequency": "monthly",
        "anchor_date": "2026-08-10",
        "category": "Insurance",
    },
    {
        "name": "Electric",
        "amount": -140,
        "frequency": "monthly",
        "anchor_date": "2026-08-20",
        "category": "Utilities",
    },
    {
        "name": "Phone",
        "amount": -90,
        "frequency": "monthly",
        "anchor_date": "2026-08-12",
        "category": "Subscriptions",
    },
    {
        "name": "Groceries",
        "amount": -150,
        "frequency": "weekly",
        "anchor_date": "2026-08-08",
        "category": "Food",
    },
]


class Wallet:
    def __init__(self, db_path: Path) -> None:
        self.store = Store(db_path)

    def today(self) -> date:
        return datetime.now(self.store.assumptions().zone).date()

    def dashboard(self, scenario_id: str | None = None, days: int | None = None) -> dict[str, Any]:
        assumptions = self.store.assumptions()
        today = self.today()
        templates = self.store.templates()
        states = self.store.states()
        extra_t: list[TemplateSnapshot] = []
        extra_s: list[StateSnapshot] = []
        scenario_meta = None
        if scenario_id:
            scenario = get_scenario(scenario_id)
            extra_t, extra_s = overlay(scenario, templates, today)
            scenario_meta = {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "stop_income": scenario.stop_income,
            }

        balance = self.store.current_balance()
        output = project(
            balance, today, templates, states, assumptions, extra_t, extra_s, days
        )
        spend = spendable_today(
            balance, today, templates, states, assumptions, extra_t, extra_s
        )
        health = evaluate_health(
            output, assumptions.warning_threshold, assumptions.danger_threshold
        )
        analysis = analyze_balance(output)
        goals = []
        for goal in self.store.goals():
            status = evaluate_goal(output, goal.target_amount, goal.target_date)
            goals.append(
                {
                    "id": goal.id,
                    "name": goal.name,
                    "target_amount": goal.target_amount,
                    "target_date": goal.target_date.isoformat(),
                    "on_track": status.on_track,
                    "projected_amount": status.projected_amount,
                    "shortfall": status.shortfall,
                }
            )
        expected = (
            expected_balance_today(balance, templates, states, assumptions, today)
            if templates
            else balance
        )
        drift = abs(balance - expected)
        upcoming = [
            _txn(t)
            for t in output.transactions
            if t.date <= today + timedelta(days=21)
        ][:24]
        active_plan = [
            s
            for s in active_plan_states(states, today)
            if s.status is not SimulationStatus.STANDARD
        ]
        return {
            "today": today.isoformat(),
            "balance": balance,
            "expected_today": expected,
            "drift": drift,
            "show_drift": drift > 50,
            "spendable": spend.amount,
            "floor": spend.floor,
            "why": spend.why,
            "runway_days": spend.runway_days,
            "min_balance": spend.min_balance,
            "min_date": spend.min_date.isoformat() if spend.min_date else None,
            "health": health.kind.value,
            "health_date": health.date.isoformat() if health.date else None,
            "stats": {
                "min_balance": output.stats.min_balance,
                "max_balance": output.stats.max_balance,
                "avg_balance": output.stats.avg_balance,
                "days_negative": output.stats.days_negative,
                "first_negative_date": (
                    output.stats.first_negative_date.isoformat()
                    if output.stats.first_negative_date
                    else None
                ),
            },
            "analysis": None
            if analysis is None
            else {
                "lowest_date": analysis.lowest_date.isoformat(),
                "lowest_balance": analysis.lowest_balance,
                "highest_date": analysis.highest_date.isoformat(),
                "highest_balance": analysis.highest_balance,
                "average_balance": analysis.average_balance,
                "volatility": analysis.volatility,
                "trend": analysis.trend_direction.value,
            },
            "snapshots": [
                {"date": s.date.isoformat(), "balance": s.balance}
                for s in output.snapshots
            ],
            "upcoming": upcoming,
            "binding_transactions": [_txn(t) for t in spend.binding_transactions],
            "next_income": _txn(spend.next_income) if spend.next_income else None,
            "next_expense": _txn(spend.next_expense) if spend.next_expense else None,
            "templates": [_template(t) for t in templates],
            "plan": [_state(s, today) for s in active_plan],
            "plan_count": len(active_plan),
            "review_needed": len([s for s in active_plan if plan_category(s.date, today).value == "future"])
            >= 5,
            "goals": goals,
            "proposals": [_proposal(p) for p in self.store.proposals()],
            "alerts": self.store.alerts(),
            "settings": _settings(assumptions),
            "scenario": scenario_meta,
            "anchor": _anchor(self.store.anchor()),
        }

    def save_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _template(self.store.upsert_template(payload))

    def delete_template(self, template_id: str) -> None:
        self.store.delete_template(template_id)

    def set_plan(self, template_id: str, when: str, status: str) -> None:
        self.store.set_state(
            template_id, date.fromisoformat(when), SimulationStatus(status)
        )

    def clear_plan(self) -> int:
        return self.store.clear_plan(self.today())

    def reset_plan(self) -> int:
        return self.store.reset_all_plan()

    def set_balance(self, amount: float, when: str | None = None) -> float:
        day = date.fromisoformat(when) if when else self.today()
        current = self.store.current_balance()
        if self.store.anchor() is None:
            self.store.set_anchor(amount, day)
        else:
            delta = amount - current
            if abs(delta) > 0.001:
                self.store.add_ledger(
                    {
                        "date": day.isoformat(),
                        "amount": delta,
                        "entry_type": "adjustment",
                        "note": "balance update",
                    }
                )
        return self.store.current_balance()

    def add_ledger(self, payload: dict[str, Any]) -> dict[str, Any]:
        entry = self.store.add_ledger(payload)
        return {
            "id": entry.id,
            "date": entry.date.isoformat(),
            "amount": entry.amount,
            "entry_type": entry.entry_type,
            "template_name": entry.template_name,
            "note": entry.note,
        }

    def history(self) -> list[dict[str, Any]]:
        return [
            {
                "id": e.id,
                "date": e.date.isoformat(),
                "amount": e.amount,
                "entry_type": e.entry_type,
                "template_id": e.template_id,
                "template_name": e.template_name,
                "note": e.note,
            }
            for e in self.store.ledger()
        ]

    def import_csv(self, text: str) -> dict[str, Any]:
        ledger_rows, template_rows, kind = csv_import.parse_csv(text)
        imported = 0
        if kind == "templates":
            for row in template_rows:
                self.store.upsert_template(row)
                imported += 1
            return {
                "kind": kind,
                "imported": imported,
                "proposals": 0,
                "ledger": 0,
            }

        for row in ledger_rows:
            self.store.add_ledger(
                {
                    "date": row.date.isoformat(),
                    "amount": row.amount,
                    "entry_type": "adjustment",
                    "template_name": row.name,
                    "note": "csv import",
                }
            )
            imported += 1
        if self.store.anchor() is None and ledger_rows:
            first = min(ledger_rows, key=lambda r: r.date)
            # Anchor at zero the day before first imported line so the sum is the balance.
            self.store.set_anchor(0.0, first.date)
        existing = {t.name for t in self.store.templates()}
        self.store.clear_pending_proposals()
        proposals = csv_import.detections_from_ledger(ledger_rows, existing)
        for item in proposals:
            self.store.add_proposal(item)
        return {
            "kind": kind,
            "imported": imported,
            "proposals": len(proposals),
            "ledger": imported,
        }

    def accept_proposal(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.set_proposal_status(proposal_id, "accepted")
        if proposal is None:
            raise KeyError(proposal_id)
        template = self.store.upsert_template(
            {
                "name": proposal.name,
                "amount": proposal.amount,
                "frequency": proposal.frequency.value,
                "anchor_date": proposal.anchor_date.isoformat(),
                "category": proposal.category.value,
                "min_amount": proposal.min_amount,
                "max_amount": proposal.max_amount,
                "is_estimate": proposal.min_amount is not None,
            }
        )
        return _template(template)

    def reject_proposal(self, proposal_id: str) -> None:
        if self.store.set_proposal_status(proposal_id, "rejected") is None:
            raise KeyError(proposal_id)

    def save_goal(self, payload: dict[str, Any]) -> dict[str, Any]:
        goal = self.store.upsert_goal(payload)
        return {
            "id": goal.id,
            "name": goal.name,
            "target_amount": goal.target_amount,
            "target_date": goal.target_date.isoformat(),
        }

    def delete_goal(self, goal_id: str) -> None:
        self.store.delete_goal(goal_id)

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _settings(self.store.update_settings(payload))

    def scenarios(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "category": s.category,
                "stop_income": s.stop_income,
                "changes": [
                    {
                        "name": c.name,
                        "amount": c.suggested_amount,
                        "is_income": c.is_income,
                        "frequency": c.frequency.value,
                        "delay_days": c.delay_days,
                    }
                    for c in s.changes
                ],
            }
            for s in LIBRARY
        ]

    def load_demo(self) -> None:
        for row in DEMO:
            self.store.upsert_template(row)
        if self.store.anchor() is None:
            self.store.set_anchor(1400.0, self.today())

    def nightly(self) -> dict[str, Any]:
        from .nightly import report_json

        return report_json(run_nightly(self.store, self.today()))

    def ack_alert(self, alert_id: str) -> None:
        self.store.ack_alert(alert_id)

    def export(self) -> dict[str, Any]:
        return self.store.export_dict()


def _txn(t) -> dict[str, Any]:
    return {
        "template_id": str(t.template_id),
        "date": t.date.isoformat(),
        "name": t.name,
        "amount": t.amount,
        "is_income": t.is_income,
    }


def _template(t: TemplateSnapshot) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "name": t.name,
        "amount": t.amount,
        "effective_amount": t.effective_amount,
        "frequency": t.frequency.value,
        "frequency_label": t.frequency.label,
        "anchor_date": t.anchor_date.isoformat(),
        "category": t.category.value,
        "min_amount": t.min_amount,
        "max_amount": t.max_amount,
        "is_income": t.is_income,
        "is_variable": t.is_variable,
        "is_estimate": t.is_estimate,
    }


def _state(s: StateSnapshot, today: date) -> dict[str, Any]:
    return {
        "template_id": str(s.template_id),
        "date": s.date.isoformat(),
        "status": s.status.value,
        "category": plan_category(s.date, today).value,
    }


def _proposal(p) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "amount": p.amount,
        "frequency": p.frequency.value,
        "frequency_label": p.frequency.label,
        "anchor_date": p.anchor_date.isoformat(),
        "category": p.category.value,
        "min_amount": p.min_amount,
        "max_amount": p.max_amount,
        "confidence": p.confidence,
        "sample_count": p.sample_count,
        "reason": p.reason,
        "status": p.status,
    }


def _settings(a: ModelAssumptions) -> dict[str, Any]:
    return {
        "timezone": a.timezone,
        "transaction_ordering": a.transaction_ordering.value,
        "rounding_mode": a.rounding_mode.value,
        "projection_days": a.projection_days,
        "warning_threshold": a.warning_threshold,
        "danger_threshold": a.danger_threshold,
        "safety_floor": a.safety_floor,
    }


def _anchor(anchor: tuple[float, date] | None) -> dict[str, Any] | None:
    if anchor is None:
        return None
    amount, when = anchor
    return {"amount": amount, "date": when.isoformat()}
