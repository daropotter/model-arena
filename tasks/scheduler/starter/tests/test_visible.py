"""Visible tests for scheduler. They pass on the buggy starter because each
input order is already feasible and optimal, even in the basic fork case."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(payload):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_path = tmp / "in.json"
        out_path = tmp / "out.json"
        in_path.write_text(json.dumps(payload))
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scheduler.py"),
             str(in_path), str(out_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise AssertionError(f"cli failed: {proc.stderr}")
        return json.loads(out_path.read_text())


class TestScheduler(unittest.TestCase):
    def test_no_dependencies(self):
        payload = {"jobs": [
            {"id": "a", "duration": 3, "deadline": 8, "depends": []},
            {"id": "b", "duration": 2, "deadline": 5, "depends": []},
        ]}
        result = run(payload)
        self.assertEqual(sorted(result["order"]), ["a", "b"])
        self.assertEqual(result["late"], 0)

    def test_lateness_uses_cumulative_machine_time(self):
        payload = {"jobs": [
            {"id": "root", "duration": 4, "deadline": 4, "depends": []},
            {"id": "left", "duration": 4, "deadline": 8,
             "depends": ["root"]},
            {"id": "right", "duration": 4, "deadline": 8,
             "depends": ["root"]},
        ]}
        result = run(payload)
        self.assertEqual(result["order"], ["root", "left", "right"])
        self.assertEqual(result["late"], 1)


if __name__ == "__main__":
    unittest.main()
