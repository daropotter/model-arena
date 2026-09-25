"""Visible tests: existing commands only. They say nothing about snooze,
migration, or the extended summary."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(store, *args):
    proc = subprocess.run(
        [sys.executable, "-m", "tasklog", "--store", str(store), *args],
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
        self.store = Path(self.tmp.name) / "store.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_show(self):
        rc, task = run(self.store, "add", "write tests", "--tag", "dev")
        self.assertEqual(rc, 0)
        self.assertEqual(task["title"], "write tests")
        self.assertEqual(task["tags"], ["dev"])
        rc, shown = run(self.store, "show", str(task["id"]))
        self.assertEqual(shown["id"], task["id"])

    def test_ids_increment(self):
        _, t1 = run(self.store, "add", "one")
        _, t2 = run(self.store, "add", "two")
        self.assertEqual(t2["id"], t1["id"] + 1)

    def test_done_and_list_filter(self):
        _, t1 = run(self.store, "add", "one")
        run(self.store, "add", "two")
        run(self.store, "done", str(t1["id"]))
        _, done = run(self.store, "list", "--status", "done")
        self.assertEqual(len(done), 1)
        _, open_tasks = run(self.store, "list", "--status", "open")
        self.assertEqual(len(open_tasks), 1)

    def test_unknown_command(self):
        rc, payload = run(self.store, "frobnicate")
        self.assertEqual(rc, 1)
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
