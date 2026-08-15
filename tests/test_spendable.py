import unittest
from datetime import date
from uuid import uuid4

from whatifwallet.engine import Frequency, ModelAssumptions, TemplateSnapshot
from whatifwallet.scenarios import get_scenario, overlay
from whatifwallet.spendable import spendable_today


class SpendableTests(unittest.TestCase):
    def test_no_bills_can_spend_down_to_floor(self):
        result = spendable_today(
            1000,
            date(2024, 1, 1),
            [],
            [],
            ModelAssumptions(safety_floor=200, projection_days=30),
        )
        self.assertEqual(result.amount, 800)

    def test_upcoming_rent_constrains_spend(self):
        rent = TemplateSnapshot(
            uuid4(), "Rent", -900, Frequency.ONE_TIME, date(2024, 1, 10)
        )
        result = spendable_today(
            1000,
            date(2024, 1, 1),
            [rent],
            [],
            ModelAssumptions(safety_floor=0, projection_days=30),
        )
        self.assertEqual(result.amount, 100)

    def test_already_underwater_is_zero(self):
        rent = TemplateSnapshot(
            uuid4(), "Rent", -2000, Frequency.ONE_TIME, date(2024, 1, 2)
        )
        result = spendable_today(
            100,
            date(2024, 1, 1),
            [rent],
            [],
            ModelAssumptions(safety_floor=0, projection_days=10),
        )
        self.assertEqual(result.amount, 0)
        self.assertEqual(result.health, "danger")

    def test_job_loss_stops_income(self):
        pay = TemplateSnapshot(
            uuid4(), "Paycheck", 2000, Frequency.BIWEEKLY, date(2024, 1, 1)
        )
        rent = TemplateSnapshot(
            uuid4(), "Rent", -1500, Frequency.MONTHLY, date(2024, 1, 1)
        )
        assumptions = ModelAssumptions(projection_days=60, safety_floor=0)
        baseline = spendable_today(1400, date(2024, 1, 1), [pay, rent], [], assumptions)
        scenario = get_scenario("job-loss")
        extras, extra_states = overlay(scenario, [pay, rent], date(2024, 1, 1))
        lost = spendable_today(
            1400, date(2024, 1, 1), [pay, rent], [], assumptions, extras, extra_states
        )
        self.assertGreater(baseline.amount, lost.amount)
        self.assertTrue(extra_states)
        self.assertEqual(extra_states[0].template_id, pay.id)


if __name__ == "__main__":
    unittest.main()
