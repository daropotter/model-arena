"""Visible tests: simple happy path only. Passing them proves nothing about
the rest of SPEC.md."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(input_text):
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "in.csv"
        out = Path(tmp) / "out.csv"
        rep = Path(tmp) / "report.json"
        inp.write_text(input_text)
        proc = subprocess.run(
            [sys.executable, "normalize.py", str(inp), str(out), str(rep)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise AssertionError(f"failed: {proc.stderr}")
        return out.read_text(), json.loads(rep.read_text())


class TestVisible(unittest.TestCase):
    def test_simple_rows(self):
        out, report = run(
            "order_id,customer,amount,currency,date,status\n"
            "b2,Alice Smith,12.50,EUR,2026-01-05,paid\n"
            "a1,Bob,3.00,usd,2026-01-06,pending\n"
        )
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "order_id,customer,amount,currency,date,status")
        self.assertEqual(lines[1], "a1,Bob,3.00,USD,2026-01-06,pending")
        self.assertEqual(lines[2], "b2,Alice Smith,12.50,EUR,2026-01-05,paid")
        self.assertEqual(report["input_rows"], 2)
        self.assertEqual(report["output_rows"], 2)
        self.assertEqual(report["dropped_rows"], 0)
        self.assertEqual(report["total_amount_by_currency"], {"USD": "3.00", "EUR": "12.50"})

    def test_negative_amount(self):
        out, report = run(
            "order_id,customer,amount,currency,date,status\n"
            "a1,Bob,-3.00,EUR,2026-01-06,paid\n"
        )
        self.assertIn("a1,Bob,-3.00,EUR,2026-01-06,paid", out)
        self.assertEqual(report["total_amount_by_currency"], {"EUR": "-3.00"})


if __name__ == "__main__":
    unittest.main()
