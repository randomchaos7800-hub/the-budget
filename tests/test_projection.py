import unittest
from datetime import date
from uuid import uuid4

from whatifwallet.engine import (
    DateRange,
    Frequency,
    ModelAssumptions,
    ProjectionEngine,
    ProjectionInput,
    RoundingMode,
    SimulationStatus,
    StateSnapshot,
    TemplateSnapshot,
    TransactionOrdering,
)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.assumptions = ModelAssumptions(timezone="America/New_York")
        self.engine = ProjectionEngine(self.assumptions)

    def test_simple_income(self):
        template = TemplateSnapshot(
            uuid4(), "Paycheck", 1000, Frequency.WEEKLY, date(2024, 1, 1)
        )
        output = self.engine.calculate(
            ProjectionInput(
                0,
                date(2024, 1, 1),
                [template],
                date_range=DateRange(date(2024, 1, 1), 28),
                assumptions=self.assumptions,
            )
        )
        self.assertEqual(len(output.snapshots), 28)
        self.assertEqual(output.snapshots[-1].balance, 4000)

    def test_income_and_expense(self):
        paycheck = TemplateSnapshot(
            uuid4(), "Paycheck", 2000, Frequency.BIWEEKLY, date(2024, 1, 1)
        )
        rent = TemplateSnapshot(
            uuid4(), "Rent", -1500, Frequency.MONTHLY, date(2024, 1, 1)
        )
        output = self.engine.calculate(
            ProjectionInput(
                1000,
                date(2024, 1, 1),
                [paycheck, rent],
                date_range=DateRange(date(2024, 1, 1), 30),
                assumptions=self.assumptions,
            )
        )
        self.assertEqual(output.snapshots[0].balance, 1500)
        self.assertEqual(output.snapshots[14].balance, 3500)

    def test_income_first_ordering(self):
        income = TemplateSnapshot(
            uuid4(), "Paycheck", 1000, Frequency.ONE_TIME, date(2024, 1, 1)
        )
        expense = TemplateSnapshot(
            uuid4(), "Bill", -800, Frequency.ONE_TIME, date(2024, 1, 1)
        )
        output = self.engine.calculate(
            ProjectionInput(0, date(2024, 1, 1), [expense, income], assumptions=self.assumptions)
        )
        self.assertEqual(output.snapshots[0].balance, 200)

    def test_skip_once(self):
        tid = uuid4()
        template = TemplateSnapshot(
            tid, "Subscription", -10, Frequency.WEEKLY, date(2024, 1, 1)
        )
        skip = StateSnapshot(tid, date(2024, 1, 8), SimulationStatus.SKIP_ONCE)
        output = self.engine.calculate(
            ProjectionInput(
                100,
                date(2024, 1, 1),
                [template],
                [skip],
                DateRange(date(2024, 1, 1), 21),
                self.assumptions,
            )
        )
        self.assertEqual(output.snapshots[0].balance, 90)
        self.assertEqual(output.snapshots[7].balance, 90)
        self.assertEqual(output.snapshots[14].balance, 80)

    def test_skip_forever(self):
        tid = uuid4()
        template = TemplateSnapshot(
            tid, "Subscription", -10, Frequency.WEEKLY, date(2024, 1, 1)
        )
        skip = StateSnapshot(tid, date(2024, 1, 8), SimulationStatus.SKIP_FOREVER)
        output = self.engine.calculate(
            ProjectionInput(
                100,
                date(2024, 1, 1),
                [template],
                [skip],
                DateRange(date(2024, 1, 1), 21),
                self.assumptions,
            )
        )
        self.assertEqual(output.snapshots[0].balance, 90)
        self.assertEqual(output.snapshots[7].balance, 90)
        self.assertEqual(output.snapshots[14].balance, 90)

    def test_statistics(self):
        template = TemplateSnapshot(
            uuid4(), "Income", 100, Frequency.WEEKLY, date(2024, 1, 8)
        )
        output = self.engine.calculate(
            ProjectionInput(
                -50,
                date(2024, 1, 1),
                [template],
                date_range=DateRange(date(2024, 1, 1), 30),
                assumptions=self.assumptions,
            )
        )
        self.assertTrue(output.stats.min_balance < 0)
        self.assertTrue(output.stats.max_balance > 0)
        self.assertTrue(output.stats.days_negative > 0)
        self.assertIsNotNone(output.stats.first_negative_date)
        self.assertTrue(output.stats.goes_negative)

    def test_variable_amount(self):
        template = TemplateSnapshot(
            uuid4(),
            "Gig Work",
            0,
            Frequency.WEEKLY,
            date(2024, 1, 1),
            min_amount=200,
            max_amount=800,
        )
        output = self.engine.calculate(
            ProjectionInput(
                0,
                date(2024, 1, 1),
                [template],
                date_range=DateRange(date(2024, 1, 1), 7),
                assumptions=self.assumptions,
            )
        )
        self.assertEqual(output.snapshots[0].balance, 500)


class AssumptionsTests(unittest.TestCase):
    def test_defaults(self):
        a = ModelAssumptions.default()
        self.assertEqual(a.version, 1)
        self.assertEqual(a.transaction_ordering, TransactionOrdering.INCOME_FIRST)
        self.assertEqual(a.rounding_mode, RoundingMode.NEAREST)
        self.assertEqual(a.projection_days, 365)

    def test_rounding_nearest(self):
        a = ModelAssumptions(rounding_mode=RoundingMode.NEAREST)
        self.assertEqual(a.round(1.234), 1.23)
        self.assertEqual(a.round(1.235), 1.24)
        self.assertEqual(a.round(1.999), 2.00)
        self.assertEqual(a.round(-1.234), -1.23)

    def test_rounding_down(self):
        a = ModelAssumptions(rounding_mode=RoundingMode.DOWN)
        self.assertEqual(a.round(1.239), 1.23)
        self.assertEqual(a.round(1.999), 1.99)
        self.assertEqual(a.round(-1.231), -1.24)

    def test_rounding_up(self):
        a = ModelAssumptions(rounding_mode=RoundingMode.UP)
        self.assertEqual(a.round(1.231), 1.24)
        self.assertEqual(a.round(1.001), 1.01)
        self.assertEqual(a.round(-1.239), -1.23)

    def test_presets(self):
        self.assertEqual(
            ModelAssumptions.conservative().transaction_ordering,
            TransactionOrdering.EXPENSE_FIRST,
        )
        self.assertEqual(
            ModelAssumptions.optimistic().transaction_ordering,
            TransactionOrdering.INCOME_FIRST,
        )


if __name__ == "__main__":
    unittest.main()
