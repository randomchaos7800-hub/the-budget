"""Faithful port of WhatIfWallet/Core/ProjectionEngine.

Same recurrence rules, same ordering, same rounding, same skip semantics.
Dates are calendar dates. Timezone only matters for resolving "today".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Iterable
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo


class Frequency(str, Enum):
    ONE_TIME = "oneTime"
    WEEKLY = "weekly"
    BIWEEKLY = "biWeekly"
    SEMI_MONTHLY = "semiMonthly"
    MONTHLY = "monthly"
    LAST_DAY_OF_MONTH = "lastDayOfMonth"
    YEARLY = "yearly"
    SEMIANNUAL = "semiAnnual"
    SECOND_WEDNESDAY = "secondWednesday"

    @property
    def label(self) -> str:
        return {
            Frequency.ONE_TIME: "One-Time",
            Frequency.WEEKLY: "Weekly",
            Frequency.BIWEEKLY: "Bi-Weekly",
            Frequency.SEMI_MONTHLY: "1st & 15th",
            Frequency.MONTHLY: "Monthly",
            Frequency.LAST_DAY_OF_MONTH: "Last Day of Month",
            Frequency.YEARLY: "Yearly",
            Frequency.SEMIANNUAL: "Every 6 Months",
            Frequency.SECOND_WEDNESDAY: "Second Wednesday",
        }[self]

    @classmethod
    def parse(cls, value: str) -> "Frequency":
        raw = (value or "").strip()
        aliases = {
            "one-time": cls.ONE_TIME,
            "onetime": cls.ONE_TIME,
            "one_time": cls.ONE_TIME,
            "once": cls.ONE_TIME,
            "weekly": cls.WEEKLY,
            "week": cls.WEEKLY,
            "bi-weekly": cls.BIWEEKLY,
            "biweekly": cls.BIWEEKLY,
            "bi_weekly": cls.BIWEEKLY,
            "every 2 weeks": cls.BIWEEKLY,
            "1st & 15th": cls.SEMI_MONTHLY,
            "1st and 15th": cls.SEMI_MONTHLY,
            "semimonthly": cls.SEMI_MONTHLY,
            "semi-monthly": cls.SEMI_MONTHLY,
            "semi_monthly": cls.SEMI_MONTHLY,
            "monthly": cls.MONTHLY,
            "month": cls.MONTHLY,
            "last day of month": cls.LAST_DAY_OF_MONTH,
            "lastdayofmonth": cls.LAST_DAY_OF_MONTH,
            "month-end": cls.LAST_DAY_OF_MONTH,
            "monthend": cls.LAST_DAY_OF_MONTH,
            "yearly": cls.YEARLY,
            "annual": cls.YEARLY,
            "annually": cls.YEARLY,
            "semiannual": cls.SEMIANNUAL,
            "semi-annual": cls.SEMIANNUAL,
            "every 6 months": cls.SEMIANNUAL,
            "twice a year": cls.SEMIANNUAL,
            "second wednesday": cls.SECOND_WEDNESDAY,
            "2nd wednesday": cls.SECOND_WEDNESDAY,
        }
        key = raw.lower()
        if key in aliases:
            return aliases[key]
        try:
            return cls(raw)
        except ValueError:
            for freq in cls:
                if freq.label.lower() == key:
                    return freq
            raise ValueError(f"Unknown frequency: {value}")


class TransactionOrdering(str, Enum):
    INCOME_FIRST = "incomeFirst"
    EXPENSE_FIRST = "expenseFirst"
    ALPHABETICAL = "alphabetical"


class RoundingMode(str, Enum):
    NEAREST = "nearest"
    DOWN = "down"
    UP = "up"


class SimulationStatus(str, Enum):
    STANDARD = "standard"
    SKIP_ONCE = "skipOnce"
    SKIP_FOREVER = "skipForever"


class CashFlowCategory(str, Enum):
    INCOME = "Income"
    HOUSING = "Housing"
    TRANSPORTATION = "Transportation"
    UTILITIES = "Utilities"
    FOOD = "Food"
    HEALTHCARE = "Healthcare"
    INSURANCE = "Insurance"
    DEBT = "Debt"
    SUBSCRIPTIONS = "Subscriptions"
    OTHER = "Other"

    @classmethod
    def parse(cls, value: str | None, amount: float = 0.0) -> "CashFlowCategory":
        if not value:
            return cls.INCOME if amount >= 0 else cls.OTHER
        raw = value.strip()
        for item in cls:
            if item.value.lower() == raw.lower() or item.name.lower() == raw.lower():
                return item
        return cls.INCOME if amount >= 0 else cls.OTHER


class PlanDateCategory(str, Enum):
    STALE = "stale"
    TODAY = "today"
    FUTURE = "future"


@dataclass(frozen=True)
class ModelAssumptions:
    version: int = 1
    timezone: str = "America/Los_Angeles"
    transaction_ordering: TransactionOrdering = TransactionOrdering.INCOME_FIRST
    rounding_mode: RoundingMode = RoundingMode.NEAREST
    projection_days: int = 365
    warning_threshold: float = 500.0
    danger_threshold: float = 0.0
    safety_floor: float = 0.0

    @classmethod
    def default(cls) -> "ModelAssumptions":
        return cls()

    @classmethod
    def conservative(cls) -> "ModelAssumptions":
        return cls(
            transaction_ordering=TransactionOrdering.EXPENSE_FIRST,
            rounding_mode=RoundingMode.UP,
        )

    @classmethod
    def optimistic(cls) -> "ModelAssumptions":
        return cls(
            transaction_ordering=TransactionOrdering.INCOME_FIRST,
            rounding_mode=RoundingMode.DOWN,
        )

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def round(self, amount: float) -> float:
        cents = amount * 100
        if self.rounding_mode is RoundingMode.NEAREST:
            if cents >= 0:
                rounded = math.floor(cents + 0.5)
            else:
                rounded = math.ceil(cents - 0.5)
            return rounded / 100
        if self.rounding_mode is RoundingMode.DOWN:
            return math.floor(cents) / 100
        return math.ceil(cents) / 100


@dataclass(frozen=True)
class TemplateSnapshot:
    id: UUID
    name: str
    amount: float
    frequency: Frequency
    anchor_date: date
    min_amount: float | None = None
    max_amount: float | None = None
    category: CashFlowCategory = CashFlowCategory.OTHER
    is_estimate: bool = False

    @property
    def effective_amount(self) -> float:
        if self.min_amount is not None and self.max_amount is not None:
            return (self.min_amount + self.max_amount) / 2.0
        return self.amount

    @property
    def is_variable(self) -> bool:
        return self.min_amount is not None and self.max_amount is not None

    @property
    def is_income(self) -> bool:
        return self.effective_amount >= 0


@dataclass(frozen=True)
class StateSnapshot:
    template_id: UUID
    date: date
    status: SimulationStatus


@dataclass(frozen=True)
class DateRange:
    start: date
    days: int

    @property
    def end(self) -> date:
        return self.start + timedelta(days=self.days - 1)


@dataclass(frozen=True)
class DailySnapshot:
    date: date
    balance: float


@dataclass(frozen=True)
class Transaction:
    template_id: UUID
    date: date
    name: str
    amount: float
    is_income: bool


@dataclass(frozen=True)
class ProjectionStats:
    min_balance: float
    max_balance: float
    avg_balance: float
    days_negative: int
    first_negative_date: date | None

    @property
    def goes_negative(self) -> bool:
        return self.days_negative > 0

    @property
    def always_positive(self) -> bool:
        return not self.goes_negative


@dataclass(frozen=True)
class ProjectionInput:
    starting_balance: float
    start_date: date
    templates: list[TemplateSnapshot]
    states: list[StateSnapshot] = field(default_factory=list)
    date_range: DateRange | None = None
    assumptions: ModelAssumptions = field(default_factory=ModelAssumptions.default)

    def resolved_range(self) -> DateRange:
        if self.date_range is not None:
            return self.date_range
        return DateRange(start=self.start_date, days=self.assumptions.projection_days)


@dataclass(frozen=True)
class ProjectionOutput:
    snapshots: list[DailySnapshot]
    stats: ProjectionStats
    transactions: list[Transaction] = field(default_factory=list)


@dataclass(frozen=True)
class GoalStatus:
    on_track: bool
    projected_amount: float
    shortfall: float | None


class ProjectionHealthKind(str, Enum):
    GOOD = "good"
    WARNING = "warning"
    DANGER = "danger"


@dataclass(frozen=True)
class ProjectionHealth:
    kind: ProjectionHealthKind
    date: date | None = None
    balance: float | None = None

    @property
    def is_okay(self) -> bool:
        return self.kind is ProjectionHealthKind.GOOD

    @property
    def message(self) -> str:
        if self.kind is ProjectionHealthKind.GOOD:
            return "You're on track"
        if self.kind is ProjectionHealthKind.WARNING:
            return "Warning: Low balance on"
        return f"Danger: ${self.balance:,.2f} on"


class TrendDirection(str, Enum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


@dataclass(frozen=True)
class BalanceAnalysis:
    lowest_date: date
    lowest_balance: float
    highest_date: date
    highest_balance: float
    average_balance: float
    volatility: float
    trend_direction: TrendDirection


REVIEW_WARNING_COUNT = 5
BALANCE_DRIFT_WARNING = 50.0


def last_day_of_month(value: date) -> int:
    if value.month == 12:
        nxt = date(value.year + 1, 1, 1)
    else:
        nxt = date(value.year, value.month + 1, 1)
    return (nxt - timedelta(days=1)).day


def is_leap_year(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


class RecurrenceEngine:
    def __init__(self, assumptions: ModelAssumptions | None = None) -> None:
        self.assumptions = assumptions or ModelAssumptions.default()

    def is_scheduled(self, check: date, template: TemplateSnapshot) -> bool:
        if check < template.anchor_date:
            return False
        freq = template.frequency
        if freq is Frequency.ONE_TIME:
            return check == template.anchor_date
        if freq is Frequency.WEEKLY:
            return (check - template.anchor_date).days % 7 == 0
        if freq is Frequency.BIWEEKLY:
            return (check - template.anchor_date).days % 14 == 0
        if freq is Frequency.SEMI_MONTHLY:
            return check.day in (1, 15)
        if freq is Frequency.MONTHLY:
            return self._is_monthly(check, template.anchor_date)
        if freq is Frequency.LAST_DAY_OF_MONTH:
            return check.day == last_day_of_month(check)
        if freq is Frequency.YEARLY:
            return self._is_yearly(check, template.anchor_date)
        if freq is Frequency.SEMIANNUAL:
            return self._is_semiannual(check, template.anchor_date)
        if freq is Frequency.SECOND_WEDNESDAY:
            return check.weekday() == 2 and 8 <= check.day <= 14
        return False

    def _is_monthly(self, check: date, anchor: date) -> bool:
        if check.day == anchor.day:
            return True
        return self._month_end_edge(check, anchor.day)

    def _month_end_edge(self, check: date, anchor_day: int) -> bool:
        if anchor_day < 28:
            return False
        last = last_day_of_month(check)
        return check.day == last and anchor_day > last

    def _is_semiannual(self, check: date, anchor: date) -> bool:
        months = (check.year - anchor.year) * 12 + check.month - anchor.month
        if months < 0 or months % 6 != 0:
            return False
        if check.day == anchor.day:
            return True
        return self._month_end_edge(check, anchor.day)

    def _is_yearly(self, check: date, anchor: date) -> bool:
        if anchor.month == 2 and anchor.day == 29:
            if check.month == 2 and check.day == 28 and not is_leap_year(check.year):
                return True
        return check.month == anchor.month and check.day == anchor.day


class ProjectionEngine:
    def __init__(self, assumptions: ModelAssumptions | None = None) -> None:
        self.assumptions = assumptions or ModelAssumptions.default()
        self.recurrence = RecurrenceEngine(self.assumptions)

    def calculate(self, inp: ProjectionInput) -> ProjectionOutput:
        assumptions = inp.assumptions or self.assumptions
        engine = self if assumptions == self.assumptions else ProjectionEngine(assumptions)
        date_range = inp.resolved_range()
        skip_forever, skip_once = _build_skip_lookup(inp.states)
        snapshots: list[DailySnapshot] = []
        transactions: list[Transaction] = []
        current = inp.starting_balance

        for offset in range(date_range.days):
            current_date = date_range.start + timedelta(days=offset)
            day_txns = engine._transactions_for(
                current_date, inp.templates, skip_forever, skip_once
            )
            ordered = engine._order(day_txns)
            for txn in ordered:
                current = assumptions.round(current + txn.amount)
                transactions.append(txn)
            snapshots.append(DailySnapshot(date=current_date, balance=current))

        return ProjectionOutput(
            snapshots=snapshots,
            stats=_stats(snapshots),
            transactions=transactions,
        )

    def _transactions_for(
        self,
        current_date: date,
        templates: Iterable[TemplateSnapshot],
        skip_forever: dict[UUID, date],
        skip_once: dict[UUID, set[date]],
    ) -> list[Transaction]:
        out: list[Transaction] = []
        for template in templates:
            if not self.recurrence.is_scheduled(current_date, template):
                continue
            if _is_skipped(template.id, current_date, skip_forever, skip_once):
                continue
            amount = template.effective_amount
            out.append(
                Transaction(
                    template_id=template.id,
                    date=current_date,
                    name=template.name,
                    amount=amount,
                    is_income=amount >= 0,
                )
            )
        return out

    def _order(self, transactions: list[Transaction]) -> list[Transaction]:
        ordering = self.assumptions.transaction_ordering
        if ordering is TransactionOrdering.INCOME_FIRST:
            return sorted(transactions, key=lambda t: (not t.is_income, t.name))
        if ordering is TransactionOrdering.EXPENSE_FIRST:
            return sorted(transactions, key=lambda t: (t.is_income, t.name))
        return sorted(transactions, key=lambda t: t.name)


def _build_skip_lookup(
    states: Iterable[StateSnapshot],
) -> tuple[dict[UUID, date], dict[UUID, set[date]]]:
    skip_forever: dict[UUID, date] = {}
    skip_once: dict[UUID, set[date]] = {}
    for state in states:
        if state.status is SimulationStatus.SKIP_FOREVER:
            existing = skip_forever.get(state.template_id)
            skip_forever[state.template_id] = (
                state.date if existing is None else min(existing, state.date)
            )
        elif state.status is SimulationStatus.SKIP_ONCE:
            skip_once.setdefault(state.template_id, set()).add(state.date)
    return skip_forever, skip_once


def _is_skipped(
    template_id: UUID,
    current_date: date,
    skip_forever: dict[UUID, date],
    skip_once: dict[UUID, set[date]],
) -> bool:
    forever = skip_forever.get(template_id)
    if forever is not None and current_date >= forever:
        return True
    return current_date in skip_once.get(template_id, set())


def _stats(snapshots: list[DailySnapshot]) -> ProjectionStats:
    if not snapshots:
        return ProjectionStats(0.0, 0.0, 0.0, 0, None)
    balances = [s.balance for s in snapshots]
    first_neg = next((s.date for s in snapshots if s.balance < 0), None)
    return ProjectionStats(
        min_balance=min(balances),
        max_balance=max(balances),
        avg_balance=sum(balances) / len(balances),
        days_negative=sum(1 for b in balances if b < 0),
        first_negative_date=first_neg,
    )


def plan_category(value: date, reference: date) -> PlanDateCategory:
    if value < reference:
        return PlanDateCategory.STALE
    if value == reference:
        return PlanDateCategory.TODAY
    return PlanDateCategory.FUTURE


def active_plan_states(
    states: Iterable[StateSnapshot], reference: date
) -> list[StateSnapshot]:
    return [s for s in states if plan_category(s.date, reference) != PlanDateCategory.STALE]


def expected_balance_today(
    typed_balance: float,
    templates: list[TemplateSnapshot],
    states: list[StateSnapshot],
    assumptions: ModelAssumptions,
    reference: date,
) -> float:
    engine = ProjectionEngine(assumptions)
    output = engine.calculate(
        ProjectionInput(
            starting_balance=typed_balance,
            start_date=reference,
            templates=templates,
            states=active_plan_states(states, reference),
            date_range=DateRange(start=reference, days=1),
            assumptions=assumptions,
        )
    )
    return output.snapshots[0].balance if output.snapshots else typed_balance


def evaluate_goal(
    output: ProjectionOutput, target_amount: float, target_date: date
) -> GoalStatus:
    match = next((s for s in output.snapshots if s.date == target_date), None)
    if match is not None:
        on_track = match.balance >= target_amount
        return GoalStatus(
            on_track=on_track,
            projected_amount=match.balance,
            shortfall=None if on_track else target_amount - match.balance,
        )
    if output.snapshots and target_date > output.snapshots[-1].date:
        last = output.snapshots[-1]
        on_track = last.balance >= target_amount
        return GoalStatus(
            on_track=on_track,
            projected_amount=last.balance,
            shortfall=None if on_track else target_amount - last.balance,
        )
    return GoalStatus(on_track=False, projected_amount=0.0, shortfall=target_amount)


def evaluate_health(
    output: ProjectionOutput,
    warning_threshold: float = 500.0,
    danger_threshold: float = 0.0,
) -> ProjectionHealth:
    if not output.snapshots:
        return ProjectionHealth(ProjectionHealthKind.GOOD)
    lowest = min(output.snapshots, key=lambda s: s.balance)
    if lowest.balance < danger_threshold:
        return ProjectionHealth(ProjectionHealthKind.DANGER, lowest.date, lowest.balance)
    if lowest.balance < warning_threshold:
        return ProjectionHealth(ProjectionHealthKind.WARNING, lowest.date, lowest.balance)
    return ProjectionHealth(ProjectionHealthKind.GOOD)


def analyze_balance(output: ProjectionOutput) -> BalanceAnalysis | None:
    if not output.snapshots:
        return None
    balances = [s.balance for s in output.snapshots]
    lowest = min(output.snapshots, key=lambda s: s.balance)
    highest = max(output.snapshots, key=lambda s: s.balance)
    average = sum(balances) / len(balances)
    variance = sum((b - average) ** 2 for b in balances) / len(balances)
    volatility = math.sqrt(variance)
    sample = max(1, len(balances) // 10)
    first_avg = sum(balances[:sample]) / sample
    last_avg = sum(balances[-sample:]) / sample
    change_pct = abs((last_avg - first_avg) / max(first_avg, 1)) * 100
    if change_pct < 5:
        trend = TrendDirection.STABLE
    elif last_avg > first_avg:
        trend = TrendDirection.INCREASING
    else:
        trend = TrendDirection.DECREASING
    return BalanceAnalysis(
        lowest_date=lowest.date,
        lowest_balance=lowest.balance,
        highest_date=highest.date,
        highest_balance=highest.balance,
        average_balance=average,
        volatility=volatility,
        trend_direction=trend,
    )


def new_id() -> UUID:
    return uuid4()
