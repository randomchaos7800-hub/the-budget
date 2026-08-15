"""Spendable-today: the product question the iOS app never made primary.

Binary-search the largest one-time spend today that keeps the projected
minimum at or above the safety floor. Deterministic. No probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from .engine import (
    DateRange,
    Frequency,
    ModelAssumptions,
    ProjectionEngine,
    ProjectionInput,
    ProjectionOutput,
    SimulationStatus,
    StateSnapshot,
    TemplateSnapshot,
    Transaction,
    active_plan_states,
    evaluate_health,
)


@dataclass(frozen=True)
class SpendableResult:
    amount: float
    floor: float
    runway_days: int | None
    min_balance: float
    min_date: date | None
    first_negative_date: date | None
    health: str
    binding_date: date | None
    binding_transactions: list[Transaction]
    next_income: Transaction | None
    next_expense: Transaction | None
    why: str


def project(
    starting_balance: float,
    start_date: date,
    templates: list[TemplateSnapshot],
    states: list[StateSnapshot],
    assumptions: ModelAssumptions,
    extra_templates: list[TemplateSnapshot] | None = None,
    extra_states: list[StateSnapshot] | None = None,
    days: int | None = None,
) -> ProjectionOutput:
    all_templates = list(templates) + list(extra_templates or [])
    all_states = active_plan_states(list(states) + list(extra_states or []), start_date)
    engine = ProjectionEngine(assumptions)
    return engine.calculate(
        ProjectionInput(
            starting_balance=starting_balance,
            start_date=start_date,
            templates=all_templates,
            states=all_states,
            date_range=DateRange(start=start_date, days=days or assumptions.projection_days),
            assumptions=assumptions,
        )
    )


def spendable_today(
    starting_balance: float,
    start_date: date,
    templates: list[TemplateSnapshot],
    states: list[StateSnapshot],
    assumptions: ModelAssumptions,
    extra_templates: list[TemplateSnapshot] | None = None,
    extra_states: list[StateSnapshot] | None = None,
) -> SpendableResult:
    floor = assumptions.safety_floor
    baseline = project(
        starting_balance,
        start_date,
        templates,
        states,
        assumptions,
        extra_templates,
        extra_states,
    )
    if not baseline.snapshots:
        return SpendableResult(
            amount=0.0,
            floor=floor,
            runway_days=None,
            min_balance=starting_balance,
            min_date=None,
            first_negative_date=None,
            health="good",
            binding_date=None,
            binding_transactions=[],
            next_income=None,
            next_expense=None,
            why="No projection window.",
        )

    def survives(cents: int) -> bool:
        spend = cents / 100.0
        extra = [_today_spend(start_date, spend)]
        output = project(
            starting_balance,
            start_date,
            templates,
            states,
            assumptions,
            list(extra_templates or []) + extra,
            extra_states,
        )
        return min(s.balance for s in output.snapshots) >= floor

    if not survives(0):
        amount = 0.0
    else:
        high = 0
        probe = 100
        # Grow until the spend breaks the floor, then binary search.
        while survives(probe) and probe < 100_000_000:
            high = probe
            probe *= 2
        if survives(probe):
            amount = probe / 100.0
        else:
            low = high
            high = probe
            while low < high:
                mid = (low + high + 1) // 2
                if survives(mid):
                    low = mid
                else:
                    high = mid - 1
            amount = low / 100.0

    health = evaluate_health(
        baseline, assumptions.warning_threshold, assumptions.danger_threshold
    )
    lowest = min(baseline.snapshots, key=lambda s: s.balance)
    first_neg = baseline.stats.first_negative_date
    first_below_floor = next(
        (s.date for s in baseline.snapshots if s.balance < floor), None
    )
    binding = first_below_floor or lowest.date
    binding_txns = [t for t in baseline.transactions if t.date <= binding][-8:]
    next_income = next((t for t in baseline.transactions if t.is_income), None)
    next_expense = next((t for t in baseline.transactions if not t.is_income), None)
    runway = None
    if first_below_floor is not None:
        runway = (first_below_floor - start_date).days
    elif first_neg is not None:
        runway = (first_neg - start_date).days

    return SpendableResult(
        amount=assumptions.round(amount),
        floor=floor,
        runway_days=runway,
        min_balance=lowest.balance,
        min_date=lowest.date,
        first_negative_date=first_neg,
        health=health.kind.value,
        binding_date=binding,
        binding_transactions=binding_txns,
        next_income=next_income,
        next_expense=next_expense,
        why=_why(amount, floor, lowest.date, lowest.balance, next_expense, runway),
    )


def _today_spend(start_date: date, amount: float) -> TemplateSnapshot:
    return TemplateSnapshot(
        id=uuid4(),
        name="Spendable Today",
        amount=-abs(amount),
        frequency=Frequency.ONE_TIME,
        anchor_date=start_date,
    )


def _why(
    amount: float,
    floor: float,
    min_date: date,
    min_balance: float,
    next_expense: Transaction | None,
    runway: int | None,
) -> str:
    if amount <= 0 and min_balance < floor:
        return (
            f"Already below the ${floor:,.0f} floor. Tightest day is {min_date.isoformat()} "
            f"at ${min_balance:,.2f}."
        )
    if next_expense is None:
        return f"${amount:,.2f} keeps every day at or above ${floor:,.0f}."
    runway_bit = (
        f" Runway to the floor is {runway} days."
        if runway is not None
        else " Projection stays above the floor."
    )
    return (
        f"${amount:,.2f} is the most you can spend today without going below "
        f"${floor:,.0f}. Binding low is {min_date.isoformat()} at ${min_balance:,.2f}. "
        f"Next bill: {next_expense.name} ${abs(next_expense.amount):,.2f} on "
        f"{next_expense.date.isoformat()}.{runway_bit}"
    )


def income_stop_states(
    templates: list[TemplateSnapshot], start_date: date
) -> list[StateSnapshot]:
    """Job-loss semantics the iOS scenario never actually did."""
    return [
        StateSnapshot(
            template_id=t.id,
            date=start_date,
            status=SimulationStatus.SKIP_FOREVER,
        )
        for t in templates
        if t.is_income
    ]
