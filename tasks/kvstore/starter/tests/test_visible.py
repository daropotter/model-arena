"""Visible tests for kvstore. They pass on the buggy starter: they only read
back through the snapshot file, never through WAL-only recovery."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(store, *args):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "kv.py"), str(store), *args],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"kv failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout), proc.returncode


class TestKvStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = self.tmp / "store"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_put_get_round_trip(self):
        got, _ = run(self.store, "put", "k", '{"a": [1, null, "x"]}')
        self.assertEqual(got, {"ok": True, "applied": 1})
        got, _ = run(self.store, "get", "k")
        self.assertEqual(got, {"key": "k", "found": True,
                               "value": {"a": [1, None, "x"]}})

    def test_delete(self):
        run(self.store, "put", "k", "1")
        got, _ = run(self.store, "delete", "k")
        self.assertEqual(got, {"ok": True, "applied": 1})
        got, _ = run(self.store, "get", "k")
        self.assertEqual(got, {"key": "k", "found": False})

    def test_batch_happy_path(self):
        ops = self.tmp / "ops.json"
        ops.write_text(json.dumps([
            {"op": "put", "key": "a", "value": 1},
            {"op": "put", "key": "b", "value": "two"},
            {"op": "delete", "key": "a"},
        ]))
        got, _ = run(self.store, "batch", str(ops))
        self.assertEqual(got, {"ok": True, "applied": 3})
        got, _ = run(self.store, "get", "a")
        self.assertEqual(got, {"key": "a", "found": False})
        got, _ = run(self.store, "get", "b")
        self.assertEqual(got, {"key": "b", "found": True, "value": "two"})

    def test_second_process_sees_values(self):
        run(self.store, "put", "first", "1")
        ops = self.tmp / "more.json"
        ops.write_text(json.dumps([
            {"op": "put", "key": "second", "value": 2},
        ]))
        run(self.store, "batch", str(ops))
        got, _ = run(self.store, "get", "first")
        self.assertEqual(got, {"key": "first", "found": True, "value": 1})
        got, _ = run(self.store, "get", "second")
        self.assertEqual(got, {"key": "second", "found": True, "value": 2})


if __name__ == "__main__":
    unittest.main()
