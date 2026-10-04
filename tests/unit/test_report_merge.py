"""H3: merge semantics and report generation (CSV quoting, analysis counts)."""

import csv
import re
import sys
import unittest

from runner import arena
from tests import support

sys.path.insert(0, str(support.ROOT / "runner"))
from runner import analyze  # noqa: E402


class MergePreviousTests(unittest.TestCase):
    def test_refresh_replaces_only_that_cell(self):
        previous = [
            {"model": "modelA", "task": "taskX", "score": 0.1},
            {"model": "modelA", "task": "taskY", "score": 0.2},
            {"model": "modelB", "task": "taskX", "score": 0.3},
        ]
        new = [{"model": "modelA", "task": "taskX", "score": 0.9}]
        merged = arena.merge_previous(previous, new)
        self.assertEqual(len(merged), 3)
        cells = [(r["model"], r["task"]) for r in merged]
        self.assertEqual(len(cells), len(set(cells)))
        by_cell = {(r["model"], r["task"]): r for r in merged}
        self.assertEqual(by_cell[("modelA", "taskX")]["score"], 0.9)
        self.assertEqual(by_cell[("modelA", "taskY")]["score"], 0.2)
        self.assertEqual(by_cell[("modelB", "taskX")]["score"], 0.3)

    def test_all_task_refresh_does_not_duplicate(self):
        previous = [
            {"model": "modelA", "task": "taskX", "score": 0.1},
            {"model": "modelA", "task": "taskY", "score": 0.2},
        ]
        new = [
            {"model": "modelA", "task": "taskX", "score": 0.7},
            {"model": "modelA", "task": "taskY", "score": 0.8},
        ]
        merged = arena.merge_previous(previous, new)
        self.assertEqual(len(merged), 2)
        cells = [(r["model"], r["task"]) for r in merged]
        self.assertEqual(len(cells), len(set(cells)))
        by_cell = {(r["model"], r["task"]): r for r in merged}
        self.assertEqual(by_cell[("modelA", "taskX")]["score"], 0.7)
        self.assertEqual(by_cell[("modelA", "taskY")]["score"], 0.8)

    def test_empty_previous_returns_new_records(self):
        new = [{"model": "modelA", "task": "taskX", "score": 0.5}]
        self.assertEqual(arena.merge_previous([], new), new)


class ReportWritingTests(support.TempDirTestCase, unittest.TestCase):
    def test_write_report_csv_and_markdown_round_trip_detail(self):
        results = self.tmpdir()
        messy = 'first line\nsecond "quoted" line, with comma'
        records = [
            support.base_record(results / "run1", model="model-1", task="task-1"),
            support.base_record(results / "run2", model="model-2", task="task-2",
                                detail=messy, score=0.5),
            support.base_record(results / "run3", model="model-3", task="task-3",
                                score=1.0, passed=True),
        ]
        md_path = arena.write_report(records, results)
        self.assertEqual(md_path, results / "report.md")
        self.assertTrue(md_path.exists())

        with open(results / "report.csv", newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(len(rows), len(records) + 1)
        header = rows[0]
        detail_col = header.index("detail")
        model_col = header.index("model")
        row = next(r for r in rows[1:] if r[model_col] == "model-2")
        self.assertEqual(row[detail_col], messy)

    def test_analyze_failure_mode_counts_reconcile(self):
        results = self.tmpdir()
        records = [
            support.base_record(results / "a1", model="alpha", task="t1",
                                passed=True, score=1.0),
            support.base_record(results / "a2", model="alpha", task="t1",
                                passed=False, score=0.0),
            support.base_record(results / "a3", model="alpha", task="t2",
                                passed=False, timed_out=True),
            support.base_record(results / "a4", model="alpha", task="t2",
                                tool_calls=0,
                                tokens={"input": 0, "output": 0, "reasoning": 0}),
            support.base_record(results / "a5", model="alpha", task="t1",
                                run_outcome="provider_error"),
            support.base_record(results / "a6", model="alpha", task="t2",
                                run_outcome="runner_error"),
            support.base_record(results / "b1", model="beta", task="t1",
                                passed=False, score=0.0),
            support.base_record(results / "b2", model="beta", task="t2",
                                exit_code=1),
            support.base_record(results / "b3", model="beta", task="t1",
                                run_outcome="grader_error"),
        ]
        models = sorted({r["model"] for r in records})
        report = analyze.build_report(records)
        self.assertIsInstance(report, str)
        for model in models:
            self.assertIn(model, report)

        counts = {}
        in_table = False
        for line in report.splitlines():
            if line.startswith("### Failure-mode breakdown"):
                in_table = True
                continue
            if in_table and line.startswith("## "):
                break
            if not in_table or not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and all(re.fullmatch(r"\d+", c) for c in cells[1:]):
                counts[cells[0]] = sum(int(c) for c in cells[1:])
        self.assertEqual(set(counts), set(models))
        for model in models:
            expected = sum(1 for r in records if r["model"] == model)
            self.assertEqual(counts[model], expected, report)


if __name__ == "__main__":
    unittest.main()
