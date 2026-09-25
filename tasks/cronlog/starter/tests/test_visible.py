"""Visible tests: single-process happy paths only. Nothing here touches
concurrency, which is what SPEC.md is mostly about."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(store, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "cronlog", "--store", str(store), *args],
        cwd=ROOT, capture_output=True, text=True,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError(f"non-json output: {proc.stdout!r} {proc.stderr!r}")
    return proc.returncode, payload


class TestVisible(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_list_stats(self):
        rc, event = run(self.store, "add", "backup")
        self.assertEqual(rc, 0)
        self.assertEqual(event["name"], "backup")
        _, listed = run(self.store, "list")
        self.assertEqual(len(listed["events"]), 1)
        _, stats = run(self.store, "stats")
        self.assertEqual(stats, {"total": 1, "by_name": {"backup": 1}})

    def test_ids_increment(self):
        _, e1 = run(self.store, "add", "a")
        _, e2 = run(self.store, "add", "b")
        self.assertEqual(e2["id"], e1["id"] + 1)

    def test_prune(self):
        run(self.store, "add", "old")
        events_path = self.store / "events.json"
        data = json.loads(events_path.read_text())
        data["events"][0]["ts"] = "2020-01-01T00:00:00Z"
        events_path.write_text(json.dumps(data))
        rc, result = run(self.store, "prune", "--before", "2021-01-01")
        self.assertEqual(rc, 0)
        self.assertEqual(result["removed"], 1)


if __name__ == "__main__":
    unittest.main()
