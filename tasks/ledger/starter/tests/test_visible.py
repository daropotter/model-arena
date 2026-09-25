"""Visible tests. They pass on the current code but cover only a small part
of SPEC.md: no rounding ties, no negative amounts, no zero amounts, no
timestamp ties."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_summarize(payload: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "in.json"
        out_path = Path(tmp) / "out.json"
        in_path.write_text(json.dumps(payload))
        proc = subprocess.run(
            [sys.executable, "-m", "ledger", "summarize", str(in_path), str(out_path)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise AssertionError(f"cli failed: {proc.stderr}")
        return json.loads(out_path.read_text())


class TestSummarize(unittest.TestCase):
    def test_basic_fee_and_balance(self):
        result = run_summarize({
            "transactions": [
                {"id": "a", "account": "alice", "amount": "10.00",
                 "timestamp": "2026-01-01T00:00:00+00:00"},
                {"id": "b", "account": "alice", "amount": "20.00",
                 "timestamp": "2026-01-02T00:00:00+00:00"},
            ]
        })
        self.assertEqual(result["fees_total"], "0.30")
        self.assertEqual(result["accounts"]["alice"], {"balance": "30.00", "count": 2})
        self.assertEqual([t["id"] for t in result["transactions"]], ["a", "b"])

    def test_ordering(self):
        result = run_summarize({
            "transactions": [
                {"id": "later", "account": "a", "amount": "1.00",
                 "timestamp": "2026-02-01T00:00:00+00:00"},
                {"id": "earlier", "account": "a", "amount": "1.00",
                 "timestamp": "2026-01-01T00:00:00+00:00"},
            ]
        })
        self.assertEqual([t["id"] for t in result["transactions"]], ["earlier", "later"])

    def test_multiple_accounts(self):
        result = run_summarize({
            "transactions": [
                {"id": "a", "account": "alice", "amount": "5.00",
                 "timestamp": "2026-01-01T00:00:00+00:00"},
                {"id": "b", "account": "bob", "amount": "7.00",
                 "timestamp": "2026-01-02T00:00:00+00:00"},
            ]
        })
        self.assertEqual(result["accounts"]["alice"]["balance"], "5.00")
        self.assertEqual(result["accounts"]["bob"]["balance"], "7.00")


if __name__ == "__main__":
    unittest.main()
