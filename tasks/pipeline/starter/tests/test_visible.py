"""Visible tests for pipeline. They pass on the buggy starter: plain string
values, no special characters, no numbers/booleans/null."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(tool, in_path, out_path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / tool), str(in_path), str(out_path)],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stderr


class TestPipeline(unittest.TestCase):
    def test_roundtrip_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            in_json = tmp / "in.json"
            pipe = tmp / "out.pipe"
            back = tmp / "back.json"
            in_json.write_text(json.dumps({"b": "two", "a": "one"}))
            rc, err = run("pack.py", in_json, pipe)
            self.assertEqual(rc, 0, err)
            rc, err = run("unpack.py", pipe, back)
            self.assertEqual(rc, 0, err)
            self.assertEqual(json.loads(back.read_text()),
                             {"a": "one", "b": "two"})


if __name__ == "__main__":
    unittest.main()
