import tempfile
import unittest
from datetime import date
from pathlib import Path

from budget.nightly import crystallize, run_nightly
from budget.store import Store


class NightlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "w.db")
        self.store.upsert_template(
            {
                "name": "Rent",
                "amount": -100,
                "frequency": "weekly",
                "anchor_date": "2026-08-01",
                "category": "Housing",
            }
        )
        self.store.set_anchor(500, date(2026, 8, 1))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_crystallize_past_only(self):
        created, skipped = crystallize(self.store, date(2026, 8, 15))
        self.assertGreater(created, 0)
        self.assertEqual(skipped, 0)
        again, _ = crystallize(self.store, date(2026, 8, 15))
        self.assertEqual(again, 0)
        self.assertLess(self.store.current_balance(), 500)

    def test_nightly_writes_report(self):
        report = run_nightly(self.store, date(2026, 8, 15))
        self.assertGreaterEqual(report.crystallized, 1)
        self.assertIsInstance(report.spendable, float)
        logged = self.store.last_nightly()
        self.assertIsNotNone(logged)


if __name__ == "__main__":
    unittest.main()
