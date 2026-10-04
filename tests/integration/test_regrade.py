"""H4: regrade integration against the real docker grader."""

import json
import shutil
import subprocess
import sys
import unittest

from runner import arena
from tests import support


class RegradeIntegrationTests(support.TempDirTestCase, unittest.TestCase):
    def setUp(self):
        support.require_docker(self)
        self.tmp = self.tmpdir()
        self.tasks_root = self.tmp / "tasks"
        self.task_dir = support.make_secret_task(self.tasks_root,
                                                 "s3cret-answer")
        self.results_root = self.tmp / "results"
        self.run_dir = self.results_root / "run1"
        self.submission = self.run_dir / "submission"
        self.record_path = self.run_dir / "record.json"

        workspace = support.make_workspace(self.tmp / "workspace-src",
                                           'print("no-leak")\n')
        self.submission.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(workspace, self.submission)

        record = support.write_record(
            self.run_dir, task="secret", model="test/model",
            run_outcome="completed", score=0.3, passed=False)
        record["provenance"] = support.provenance_for(self.task_dir)
        record["provenance"]["submission_digest"] = arena.tree_digest(
            self.submission)
        self.record_path.write_text(json.dumps(record, indent=2))

    def _regrade(self, *extra):
        return subprocess.run(
            [sys.executable, str(support.ROOT / "runner" / "regrade.py"),
             "--results", str(self.results_root),
             "--tasks", str(self.tasks_root),
             "--task", "secret", "--no-reports", *extra],
            capture_output=True, text=True, timeout=300)

    def _load(self):
        return json.loads(self.record_path.read_text())

    def test_regrade_rewrites_grade_and_preserves_history(self):
        proc = self._regrade()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        record = self._load()
        self.assertIn("regraded_at", record)
        self.assertEqual(record["run_outcome"], "completed")
        self.assertEqual(len(record.get("grade_history", [])), 1)
        history = record["grade_history"][0]
        self.assertEqual(history["score"], 0.3)
        self.assertFalse(history["passed"])
        self.assertEqual(record["score"], 0.0)
        self.assertFalse(record["passed"])
        self.assertTrue(record["valid_for_quality"])

    def test_digest_mismatch_skips_without_touching_record(self):
        first = self._regrade()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        record = self._load()
        self.assertIn("regraded_at", record)
        regraded_at = record["regraded_at"]

        (self.submission / "answer.py").write_text('print("changed")\n')
        second = self._regrade()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        output = second.stdout + second.stderr
        self.assertIn("hash mismatch", output)

        after = self._load()
        self.assertEqual(after["regraded_at"], regraded_at)
        self.assertEqual(after["score"], record["score"])
        self.assertEqual(after["grade_history"], record["grade_history"])

    def test_provider_error_record_is_skipped_and_unchanged(self):
        error_run = self.results_root / "run2"
        support.write_record(
            error_run, task="secret", model="test/model2",
            run_outcome="provider_error", passed=False, score=0.0,
            valid_for_quality=False)
        error_record_path = error_run / "record.json"
        before = error_record_path.read_text()

        proc = self._regrade("--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        output = proc.stdout + proc.stderr
        self.assertIn("SKIP", output)
        self.assertIn("test/model2", output)
        self.assertEqual(error_record_path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
