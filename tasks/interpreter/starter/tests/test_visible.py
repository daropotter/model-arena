"""Visible tests for interpreter. They pass on the buggy starter: simple
arithmetic and a top-level let, no shadowing or closures."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(node):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_path = tmp / "in.json"
        out_path = tmp / "out.json"
        in_path.write_text(json.dumps(node))
        proc = subprocess.run(
            [sys.executable, str(ROOT / "eval.py"),
             str(in_path), str(out_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None, proc.returncode
        return json.loads(out_path.read_text()), 0


class TestInterpreter(unittest.TestCase):
    def test_add(self):
        got, rc = run({"type": "add",
                       "l": {"type": "num", "value": 1},
                       "r": {"type": "num", "value": 2}})
        self.assertEqual(rc, 0)
        self.assertEqual(got["result"], 3)

    def test_top_level_let(self):
        got, rc = run({"type": "let", "name": "x",
                       "value": {"type": "num", "value": 1},
                       "body": {"type": "add",
                                "l": {"type": "var", "name": "x"},
                                "r": {"type": "num", "value": 2}}})
        self.assertEqual(rc, 0)
        self.assertEqual(got["result"], 3)

    def test_mul(self):
        got, rc = run({"type": "mul",
                       "l": {"type": "num", "value": 6},
                       "r": {"type": "num", "value": 7}})
        self.assertEqual(rc, 0)
        self.assertEqual(got["result"], 42)


if __name__ == "__main__":
    unittest.main()
