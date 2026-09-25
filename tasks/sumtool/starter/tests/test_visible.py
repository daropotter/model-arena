"""Visible tests for sumtool. They pass on the buggy starter: no decimals,
no signs, no whitespace-heavy input."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(text):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "sumtool.py"), text],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestSumtool(unittest.TestCase):
    def test_integers(self):
        rc, out, _ = run("1,2,3")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "6\n")

    def test_single_number(self):
        rc, out, _ = run("42")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "42\n")


if __name__ == "__main__":
    unittest.main()
