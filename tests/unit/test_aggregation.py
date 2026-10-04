"""H3: repeat aggregation (batch mean/median) and invalid-attempt filtering."""

import unittest

from runner import reporting
from tests import support


class AggregationTests(support.TempDirTestCase, unittest.TestCase):
    def _write_attempt(self, results, name, finished_at, **overrides):
        return support.write_record(
            results / name, task="secret", model="test/model",
            batch_id="batch-1", finished_at=finished_at, **overrides)

    def test_repeats_selected_by_mean_and_median(self):
        results = self.tmpdir() / "results"
        self._write_attempt(results, "r0", "2026-09-01T00:00:00+00:00",
                            repeat_index=0, score=1.0, passed=True, duration_s=10)
        self._write_attempt(results, "r1", "2026-09-01T00:01:00+00:00",
                            repeat_index=1, score=0.5, passed=False, duration_s=20)
        self._write_attempt(results, "r2", "2026-09-01T00:02:00+00:00",
                            repeat_index=2, score=0.0, passed=False, duration_s=90)

        selected = reporting.load_records([results])
        self.assertEqual(len(selected), 1)
        record = selected[0]
        # Exact batch mean, not the latest attempt's 0.0: no rounding slack.
        self.assertEqual(record["score"], 0.5)
        self.assertNotEqual(record["score"], 0.0)
        self.assertFalse(record["passed"])
        self.assertEqual(record["duration_s"], 20)
        self.assertEqual(record["_repeat_scores"], [1.0, 0.5, 0.0])
        self.assertEqual(record["_repeat_scores"][-1], 0.0)
        self.assertEqual(record["_repeat_pass_rate"], 1 / 3)
        self.assertEqual(record["_attempt_count"], 3)

    def test_all_repeats_passing_stays_passed(self):
        results = self.tmpdir() / "results"
        self._write_attempt(results, "r0", "2026-09-01T00:00:00+00:00",
                            repeat_index=0, score=1.0, passed=True, duration_s=10)
        self._write_attempt(results, "r1", "2026-09-01T00:01:00+00:00",
                            repeat_index=1, score=0.5, passed=True, duration_s=20)
        self._write_attempt(results, "r2", "2026-09-01T00:02:00+00:00",
                            repeat_index=2, score=1.0, passed=True, duration_s=30)

        record = reporting.load_records([results])[0]
        self.assertTrue(record["passed"])
        self.assertEqual(record["_repeat_pass_rate"], 1.0)

    def test_quality_records_excludes_invalid_attempts(self):
        tmp = self.tmpdir()
        records = [
            support.base_record(tmp, run_outcome="completed", passed=True,
                                score=1.0),
            support.base_record(tmp, run_outcome="provider_error"),
            support.base_record(tmp, run_outcome="api_error"),
            support.base_record(tmp, run_outcome="runner_error"),
            support.base_record(tmp, run_outcome="grader_error"),
            support.base_record(tmp, run_outcome=None, valid_for_quality=False),
        ]
        quality = reporting.quality_records(records)
        self.assertEqual(len(quality), 1)
        self.assertTrue(quality[0]["passed"])
        self.assertTrue(reporting.is_valid(quality[0]))


if __name__ == "__main__":
    unittest.main()
