"""Visible tests for filedock. They pass on the buggy starter: a single
valid file with a real date, no duplicates, no invalid dates."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestOrganize(unittest.TestCase):
    def test_single_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inbox = tmp / "inbox"
            inbox.mkdir()
            (inbox / "report-20260115.txt").write_text("alpha\n")
            manifest = tmp / "manifest.json"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "organize.py"), str(inbox), str(manifest)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(manifest.read_text())
            self.assertEqual(data["moved"], ["report-20260115.txt"])
            self.assertEqual(data["duplicates"], [])
            dest = tmp / "reports" / "2026" / "01" / "report-20260115.txt"
            self.assertTrue(dest.exists())


if __name__ == "__main__":
    unittest.main()
