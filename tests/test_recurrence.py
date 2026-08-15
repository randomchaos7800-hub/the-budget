import unittest
from datetime import date
from uuid import uuid4

from budget.engine import Frequency, RecurrenceEngine, TemplateSnapshot


class RecurrenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = RecurrenceEngine()

    def tmpl(self, freq, anchor):
        return TemplateSnapshot(uuid4(), "Test", 100, freq, anchor)

    def test_one_time(self):
        t = self.tmpl(Frequency.ONE_TIME, date(2024, 1, 15))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 15), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 1, 14), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 1, 16), t))

    def test_weekly(self):
        t = self.tmpl(Frequency.WEEKLY, date(2024, 1, 1))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 1), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 8), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 15), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 1, 2), t))

    def test_biweekly(self):
        t = self.tmpl(Frequency.BIWEEKLY, date(2024, 1, 1))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 1), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 1, 8), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 15), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 29), t))

    def test_semi_monthly(self):
        t = self.tmpl(Frequency.SEMI_MONTHLY, date(2024, 1, 1))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 1), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 15), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 2, 1), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 2, 15), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 1, 10), t))

    def test_monthly(self):
        t = self.tmpl(Frequency.MONTHLY, date(2024, 1, 15))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 15), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 2, 15), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 3, 15), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 2, 14), t))

    def test_monthly_on_day_31(self):
        t = self.tmpl(Frequency.MONTHLY, date(2024, 1, 31))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 31), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 3, 31), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 2, 29), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 2, 28), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 4, 30), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 4, 29), t))

    def test_last_day_of_month(self):
        t = self.tmpl(Frequency.LAST_DAY_OF_MONTH, date(2024, 1, 1))
        self.assertTrue(self.engine.is_scheduled(date(2024, 1, 31), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 2, 29), t))
        self.assertTrue(self.engine.is_scheduled(date(2024, 4, 30), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 1, 30), t))

    def test_yearly(self):
        t = self.tmpl(Frequency.YEARLY, date(2024, 3, 15))
        self.assertTrue(self.engine.is_scheduled(date(2024, 3, 15), t))
        self.assertTrue(self.engine.is_scheduled(date(2025, 3, 15), t))
        self.assertTrue(self.engine.is_scheduled(date(2026, 3, 15), t))
        self.assertFalse(self.engine.is_scheduled(date(2024, 3, 16), t))

    def test_yearly_leap_day(self):
        t = self.tmpl(Frequency.YEARLY, date(2024, 2, 29))
        self.assertTrue(self.engine.is_scheduled(date(2024, 2, 29), t))
        self.assertTrue(self.engine.is_scheduled(date(2025, 2, 28), t))
        self.assertTrue(self.engine.is_scheduled(date(2028, 2, 29), t))
        self.assertFalse(self.engine.is_scheduled(date(2025, 2, 27), t))

    def test_semiannual(self):
        t = self.tmpl(Frequency.SEMIANNUAL, date(2026, 6, 29))
        self.assertTrue(self.engine.is_scheduled(date(2026, 6, 29), t))
        self.assertTrue(self.engine.is_scheduled(date(2026, 12, 29), t))
        self.assertTrue(self.engine.is_scheduled(date(2027, 6, 29), t))
        self.assertFalse(self.engine.is_scheduled(date(2027, 1, 29), t))

    def test_second_wednesday(self):
        t = self.tmpl(Frequency.SECOND_WEDNESDAY, date(2026, 8, 12))
        self.assertTrue(self.engine.is_scheduled(date(2026, 8, 12), t))
        self.assertTrue(self.engine.is_scheduled(date(2026, 9, 9), t))
        self.assertFalse(self.engine.is_scheduled(date(2026, 8, 5), t))
        self.assertFalse(self.engine.is_scheduled(date(2026, 8, 19), t))

    def test_does_not_fire_before_anchor(self):
        t = self.tmpl(Frequency.MONTHLY, date(2024, 1, 15))
        self.assertFalse(self.engine.is_scheduled(date(2024, 1, 14), t))
        self.assertFalse(self.engine.is_scheduled(date(2023, 12, 15), t))


if __name__ == "__main__":
    unittest.main()
