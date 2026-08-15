import unittest
from datetime import date
from uuid import uuid4

from whatifwallet.engine import (
    DailySnapshot,
    Frequency,
    ProjectionOutput,
    ProjectionStats,
    SimulationStatus,
    StateSnapshot,
    TemplateSnapshot,
    analyze_balance,
    evaluate_goal,
    evaluate_health,
    expected_balance_today,
    plan_category,
    PlanDateCategory,
    ProjectionHealthKind,
    TrendDirection,
)
from whatifwallet.engine import ModelAssumptions


def snaps(*pairs):
    return [DailySnapshot(d, b) for d, b in pairs]


def output(items):
    stats = ProjectionStats(
        min(s.balance for s in items),
        max(s.balance for s in items),
        sum(s.balance for s in items) / len(items),
        sum(1 for s in items if s.balance < 0),
        next((s.date for s in items if s.balance < 0), None),
    )
    return ProjectionOutput(items, stats)


class HelperTests(unittest.TestCase):
    def test_goal_on_track(self):
        out = output(
            snaps(
                (date(2024, 1, 1), 1000),
                (date(2024, 1, 15), 2000),
                (date(2024, 2, 1), 3000),
            )
        )
        status = evaluate_goal(out, 2500, date(2024, 2, 1))
        self.assertTrue(status.on_track)
        self.assertEqual(status.projected_amount, 3000)
        self.assertIsNone(status.shortfall)

    def test_goal_off_track(self):
        out = output(snaps((date(2024, 1, 1), 1000), (date(2024, 1, 15), 1500)))
        status = evaluate_goal(out, 2000, date(2024, 1, 15))
        self.assertFalse(status.on_track)
        self.assertEqual(status.projected_amount, 1500)
        self.assertEqual(status.shortfall, 500)

    def test_goal_beyond_projection(self):
        out = output(snaps((date(2024, 1, 1), 1000), (date(2024, 1, 15), 2500)))
        status = evaluate_goal(out, 3000, date(2024, 2, 1))
        self.assertFalse(status.on_track)
        self.assertEqual(status.projected_amount, 2500)
        self.assertEqual(status.shortfall, 500)

    def test_health_good(self):
        out = output(snaps((date(2024, 1, 1), 1000), (date(2024, 1, 15), 2000)))
        self.assertEqual(evaluate_health(out).kind, ProjectionHealthKind.GOOD)

    def test_health_warning(self):
        out = output(snaps((date(2024, 1, 1), 800), (date(2024, 1, 15), 400)))
        health = evaluate_health(out)
        self.assertEqual(health.kind, ProjectionHealthKind.WARNING)
        self.assertEqual(health.date, date(2024, 1, 15))

    def test_health_danger(self):
        out = output(snaps((date(2024, 1, 1), 100), (date(2024, 1, 15), -50)))
        health = evaluate_health(out)
        self.assertEqual(health.kind, ProjectionHealthKind.DANGER)
        self.assertEqual(health.balance, -50)

    def test_analyze_increasing(self):
        items = snaps(*[(date(2024, 1, 1 + i), 100 + i * 20) for i in range(20)])
        analysis = analyze_balance(output(items))
        self.assertEqual(analysis.trend_direction, TrendDirection.INCREASING)

    def test_plan_category(self):
        today = date(2024, 1, 10)
        self.assertEqual(plan_category(date(2024, 1, 9), today), PlanDateCategory.STALE)
        self.assertEqual(plan_category(today, today), PlanDateCategory.TODAY)
        self.assertEqual(plan_category(date(2024, 1, 11), today), PlanDateCategory.FUTURE)

    def test_stale_skip_does_not_affect_expected_today(self):
        tid = uuid4()
        template = TemplateSnapshot(
            tid, "Bill", -50, Frequency.ONE_TIME, date(2024, 1, 10)
        )
        stale = StateSnapshot(tid, date(2024, 1, 1), SimulationStatus.SKIP_ONCE)
        expected = expected_balance_today(
            100,
            [template],
            [stale],
            ModelAssumptions(),
            date(2024, 1, 10),
        )
        self.assertEqual(expected, 50)


if __name__ == "__main__":
    unittest.main()
