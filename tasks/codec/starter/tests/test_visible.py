"""Visible tests for codec. They pass on the buggy starter: a short payload
fits the single-byte length and the wrong CRC bytes are consistent between
the starter's own encode and decode."""

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


class TestCodec(unittest.TestCase):
    def test_roundtrip_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            in_json = tmp / "in.json"
            frame = tmp / "out.bin"
            back = tmp / "back.json"
            in_json.write_text(json.dumps({"text": "hello"}))
            rc, err = run("encode.py", in_json, frame)
            self.assertEqual(rc, 0, err)
            rc, err = run("decode.py", frame, back)
            self.assertEqual(rc, 0, err)
            self.assertEqual(json.loads(back.read_text()), {"text": "hello"})


if __name__ == "__main__":
    unittest.main()
