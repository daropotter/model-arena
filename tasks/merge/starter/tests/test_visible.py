"""Visible tests for merge. They pass on the buggy starter: no change and a
simple identical change on both sides."""

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
            [sys.executable, str(ROOT / "merge.py"),
             str(in_path), str(out_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None, proc.returncode
        return json.loads(out_path.read_text()), 0


class TestMerge(unittest.TestCase):
    def test_no_change(self):
        got, rc = run({"base": ["a", "b"], "ours": ["a", "b"],
                       "theirs": ["a", "b"]})
        self.assertEqual(rc, 0)
        self.assertEqual(got, ["a", "b"])

    def test_both_changed_same(self):
        got, rc = run({"base": ["a", "b"], "ours": ["a", "c"],
                       "theirs": ["a", "c"]})
        self.assertEqual(rc, 0)
        self.assertEqual(got, ["a", "c"])


if __name__ == "__main__":
    unittest.main()
