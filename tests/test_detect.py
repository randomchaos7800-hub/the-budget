import unittest
from datetime import date, timedelta

from budget.csv_import import parse_csv
from budget.detect import detect_recurrences
from budget.engine import Frequency


class DetectTests(unittest.TestCase):
    def test_monthly_rent(self):
        rows = [
            (date(2026, n, 1), "RENT ACME APTS", -1600.0) for n in range(1, 7)
        ]
        found = detect_recurrences(rows)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].frequency, Frequency.MONTHLY)
        self.assertEqual(found[0].amount, -1600)
        self.assertGreaterEqual(found[0].confidence, 0.6)

    def test_biweekly_paycheck(self):
        start = date(2026, 1, 2)
        rows = [(start + timedelta(days=14 * i), "ACME PAYROLL", 2200.0) for i in range(8)]
        found = detect_recurrences(rows)
        self.assertEqual(found[0].frequency, Frequency.BIWEEKLY)
        self.assertTrue(found[0].amount > 0)

    def test_skips_existing_names(self):
        rows = [(date(2026, n, 1), "Rent", -1600.0) for n in range(1, 5)]
        found = detect_recurrences(rows, existing_names={"Rent"})
        self.assertEqual(found, [])

    def test_template_csv(self):
        text = "name,amount,type,frequency,category\nRent,1600,expense,monthly,Housing\nPay,2200,income,biweekly,Income\n"
        ledger, templates, kind = parse_csv(text)
        self.assertEqual(kind, "templates")
        self.assertEqual(len(templates), 2)
        self.assertEqual(templates[0]["amount"], -1600)
        self.assertEqual(templates[1]["amount"], 2200)

    def test_bank_csv(self):
        text = "Date,Description,Amount\n01/01/2026,RENT ACME,-1600\n01/15/2026,ACME PAYROLL,2200\n"
        ledger, templates, kind = parse_csv(text)
        self.assertEqual(kind, "ledger")
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[0].amount, -1600)
        self.assertEqual(ledger[1].amount, 2200)

    def test_debit_credit_columns(self):
        text = "date,description,debit,credit\n2026-01-01,Rent,1600,\n2026-01-15,Paycheck,,2200\n"
        ledger, _, kind = parse_csv(text)
        self.assertEqual(kind, "ledger")
        self.assertEqual(ledger[0].amount, -1600)
        self.assertEqual(ledger[1].amount, 2200)


if __name__ == "__main__":
    unittest.main()
