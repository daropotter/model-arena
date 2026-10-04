"""Visible tests for regex. They pass on the buggy starter and do not require
real backtracking across a group or alternation."""

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
            [sys.executable, str(ROOT / "match.py"),
             str(in_path), str(out_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None, proc.returncode
        return json.loads(out_path.read_text()), 0


class TestRegex(unittest.TestCase):
    def test_literal_full(self):
        got, rc = run({"pattern": "abc", "text": "abc", "full": True})
        self.assertEqual(rc, 0)
        self.assertTrue(got["match"])

    def test_literal_fail(self):
        got, rc = run({"pattern": "abc", "text": "abd", "full": True})
        self.assertEqual(rc, 0)
        self.assertFalse(got["match"])

    def test_class(self):
        got, rc = run({"pattern": "[a-c]", "text": "b", "full": True})
        self.assertEqual(rc, 0)
        self.assertTrue(got["match"])

    def test_star_example_short_text(self):
        got, rc = run({"pattern": "a*a", "text": "aa", "full": True})
        self.assertEqual(rc, 0)
        self.assertTrue(got["match"])


if __name__ == "__main__":
    unittest.main()
