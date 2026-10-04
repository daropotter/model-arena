"""H3: run outcome classification, status precedence, latest-valid selection."""

import unittest

from runner import reporting
from tests import support


def legacy_record(run_dir, **overrides):
    """A pre-run_outcome record: no run_outcome, no valid_for_quality."""
    record = support.base_record(run_dir, **overrides)
    record.pop("run_outcome", None)
    record.pop("valid_for_quality", None)
    return record


class OutcomeTests(support.TempDirTestCase, unittest.TestCase):
    def setUp(self):
        self.tmp = self.tmpdir()

    def test_explicit_error_outcomes_invalid_despite_work(self):
        cases = {
            "provider_error": "PROVIDER_ERROR",
            "api_error": "API_ERROR",
            "runner_error": "RUNNER_ERROR",
            "grader_error": "GRADER_ERROR",
        }
        for outcome, category in cases.items():
            with self.subTest(outcome=outcome):
                record = support.base_record(
                    self.tmp, run_outcome=outcome, tool_calls=5, passed=True,
                    score=1.0,
                    tokens={"input": 100, "output": 50, "reasoning": 0})
                self.assertEqual(reporting.error_category(record), category)
                self.assertFalse(reporting.is_valid(record))
                self.assertEqual(reporting.status_of(record), category)

    def test_valid_for_quality_false_without_outcome(self):
        record = support.base_record(self.tmp, valid_for_quality=False)
        record.pop("run_outcome", None)
        self.assertEqual(reporting.error_category(record), "RUNNER_ERROR")
        self.assertFalse(reporting.is_valid(record))
        self.assertEqual(reporting.status_of(record), "RUNNER_ERROR")

    def test_legacy_api_errors_without_work_invalid(self):
        record = legacy_record(
            self.tmp, api_errors=3, tool_calls=0,
            tokens={"input": 0, "output": 0, "reasoning": 0})
        self.assertEqual(reporting.error_category(record), "API_ERROR")
        self.assertFalse(reporting.is_valid(record))
        self.assertEqual(reporting.status_of(record), "API_ERROR")

    def test_legacy_api_errors_with_work_valid(self):
        worked = legacy_record(self.tmp, api_errors=3, tool_calls=2)
        tokened = legacy_record(
            self.tmp, api_errors=3, tool_calls=0,
            tokens={"input": 5, "output": 42, "reasoning": 0})
        for record in (worked, tokened):
            with self.subTest(tool_calls=record["tool_calls"],
                              output=record["tokens"]["output"]):
                self.assertIsNone(reporting.error_category(record))
                self.assertTrue(reporting.is_valid(record))

    def test_status_precedence(self):
        cases = [
            (dict(passed=True, timed_out=True, exit_code=1, tool_calls=3), "PASS"),
            (dict(passed=False, timed_out=True, exit_code=0, tool_calls=3), "TIMEOUT"),
            (dict(passed=False, timed_out=False, exit_code=1, tool_calls=0),
             "AGENT_ERROR"),
            (dict(passed=False, timed_out=False, exit_code=0, tool_calls=0),
             "NO_ACTION"),
            (dict(passed=False, timed_out=False, exit_code=0, tool_calls=4), "FAIL"),
            (dict(passed=False, timed_out=False, exit_code=None, tool_calls=4),
             "FAIL"),
        ]
        for overrides, expected in cases:
            with self.subTest(expected=expected):
                record = support.base_record(self.tmp, **overrides)
                self.assertEqual(reporting.status_of(record), expected)

    def test_latest_valid_beats_later_invalid(self):
        results = self.tmp / "results"
        support.write_record(
            results / "run-early", task="secret", model="test/model",
            batch_id="batch-early", run_outcome="completed", passed=False,
            score=0.4, finished_at="2026-09-01T00:00:00+00:00")
        support.write_record(
            results / "run-late", task="secret", model="test/model",
            batch_id="batch-late", run_outcome="provider_error", passed=False,
            score=0.0, finished_at="2026-09-02T00:00:00+00:00")
        selected = reporting.load_records([results])
        self.assertEqual(len(selected), 1)
        record = selected[0]
        self.assertTrue(reporting.is_valid(record))
        self.assertEqual(record["score"], 0.4)
        self.assertEqual(record["_record_path"],
                         str(results / "run-early" / "record.json"))
        self.assertEqual(record["_later_invalid"], ["PROVIDER_ERROR"])
        self.assertEqual(record["_attempt_count"], 2)

    def test_no_valid_attempt_returns_invalid_record(self):
        results = self.tmp / "results"
        support.write_record(
            results / "only-run", task="secret", model="test/model",
            run_outcome="grader_error", passed=False, score=0.0,
            finished_at="2026-09-03T00:00:00+00:00")
        selected = reporting.load_records([results])
        self.assertEqual(len(selected), 1)
        self.assertFalse(reporting.is_valid(selected[0]))
        self.assertEqual(reporting.error_category(selected[0]), "GRADER_ERROR")
        self.assertEqual(selected[0]["_later_invalid"], [])


if __name__ == "__main__":
    unittest.main()
