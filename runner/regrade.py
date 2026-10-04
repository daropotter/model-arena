#!/usr/bin/env python3
"""Re-grade saved submissions while preserving the previous grade in history.

Use after fixing a grader: takes each run's saved workspace, runs the current
grader against it (in docker, workspace read-only), and rewrites the record's
score/passed/detail. Also updates all result reports.

Usage:
  python3 runner/regrade.py                      # valid repeats in selected batches
  python3 runner/regrade.py --task datajanitor
  python3 runner/regrade.py --task datajanitor --dry-run
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runner"))
import arena  # noqa: E402
import reporting  # noqa: E402
import run_lock  # noqa: E402


def latest_records(results_root: Path):
    """Individual attempts in each selected batch, never report aggregates."""
    selected = {(record["model"], record["task"]): record
                for record in reporting.load_records(
                    [results_root], include_smoke=True)}
    attempts = []
    for path in sorted(results_root.glob("*/record.json")):
        try:
            record = reporting.normalize_record(json.loads(path.read_text()), path)
        except (OSError, UnicodeError, ValueError, TypeError):
            continue
        if record is None:
            continue
        choice = selected.get((record["model"], record["task"]))
        if choice is None:
            continue
        same_batch = (choice.get("batch_id")
                      and record.get("batch_id") == choice["batch_id"]
                      and reporting.is_valid(record))
        if str(path) == choice["_record_path"] or same_batch:
            attempts.append((path, record))
    return attempts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--tasks", default=str(ROOT / "tasks"))
    ap.add_argument("--task", nargs="*", default=None)
    ap.add_argument("--models", nargs="+", default=None,
                    help="re-grade only the specified model identifiers")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-reports", action="store_true",
                    help="do not regenerate report.md and derived reports")
    args = ap.parse_args()

    results_root = Path(args.results).resolve()
    tasks_dir = Path(args.tasks).resolve()
    records = latest_records(results_root)

    regraded = 0
    skipped = 0
    changed_count = 0
    for record_path, record in records:
        model, task = record["model"], record["task"]
        if args.models and model not in args.models:
            continue
        if args.task and task not in args.task:
            continue
        if task == "smoke":
            continue
        if not reporting.is_valid(record):
            print(f"SKIP {model} x {task}: infrastructure failure, no valid submission")
            skipped += 1
            continue
        saved_submission = record_path.parent / "submission"
        workspace_value = record.get("workspace")
        workspace = saved_submission if saved_submission.exists() else (
            Path(workspace_value) if workspace_value else None)
        if workspace is None or not workspace.is_absolute() or not workspace.exists():
            print(f"SKIP {model} x {task}: workspace gone")
            skipped += 1
            continue
        expected_submission = (record.get("provenance") or {}).get("submission_digest")
        if expected_submission and arena.tree_digest(workspace) != expected_submission:
            print(f"SKIP {model} x {task}: saved submission hash mismatch")
            skipped += 1
            continue
        task_meta = arena.load_task(tasks_dir, task)

        # Tamper is taken from the record, not recomputed: the starter on disk
        # may have been edited since the run (fixing a task updates SPEC.md),
        # which would look like tampering. Only the run-time snapshot knows what
        # the model really touched. Old records that flagged __pycache__ are
        # sanitized because that is a build artifact, not tampering.
        tamper = record.get("tamper") or {}
        touched = [f for f in (tamper.get("touched_protected") or [])
                   if not (f.endswith(".pyc") or "__pycache__" in f)]
        if touched:
            print(f"SKIP {model} x {task}: tampered protected files: {touched}")
            skipped += 1
            continue
        tamper["touched_protected"] = []
        record["tamper"] = tamper
        if args.dry_run:
            print(f"WOULD re-grade {model} x {task} from {workspace}")
            continue
        result = arena.grade(task_meta, workspace, tasks_dir / task / "grader",
                             record_path.parent)
        if result.get("grader_error"):
            print(f"SKIP {model} x {task}: {result.get('detail')}")
            skipped += 1
            continue
        old_score, old_passed = record.get("score"), record.get("passed")
        history = record.setdefault("grade_history", [])
        history.append({
            "passed": old_passed,
            "score": old_score,
            "detail": record.get("detail", ""),
            "graded_at": record.get("regraded_at") or record.get("finished_at"),
            "grader_digest": (record.get("provenance") or {}).get("grader_digest"),
        })
        record["passed"] = bool(result.get("passed"))
        record["score"] = float(result.get("score", 0.0))
        record["detail"] = result.get("detail", "")
        record["regraded_at"] = datetime.now(timezone.utc).isoformat()
        if record.get("timed_out"):
            record["run_outcome"] = "agent_timeout"
        elif record.get("exit_code") not in (0, None):
            record["run_outcome"] = "agent_error"
        else:
            record["run_outcome"] = "completed"
        record["valid_for_quality"] = True
        provenance = record.setdefault("provenance", {})
        provenance["grader_digest"] = arena.tree_digest(tasks_dir / task / "grader")
        provenance["task_digest"] = arena.tree_digest(tasks_dir / task)
        (record_path.parent / "grade" / "result.json").write_text(
            json.dumps(result, indent=2))
        persisted = {key: value for key, value in record.items()
                     if not key.startswith("_")}
        record_path.write_text(json.dumps(persisted, indent=2))
        regraded += 1
        if (old_score, old_passed) != (record["score"], record["passed"]):
            changed_count += 1
            print(f"CHANGED {model} x {task}: "
                  f"{old_score:.2f}/{old_passed} -> "
                  f"{record['score']:.2f}/{record['passed']}")
        else:
            print(f"same {model} x {task}: {record['score']:.2f}")

    print(f"\nre-graded: {regraded}, changed: {changed_count}, skipped: {skipped}")

    if not args.dry_run and regraded and not args.no_reports:
        all_records = arena.load_all_records(results_root)
        arena.write_report(all_records, results_root)
        for script in ("analyze.py", "roster.py", "report_models.py"):
            subprocess.run([sys.executable, str(ROOT / "runner" / script),
                            "--results", str(results_root)],
                           check=True)
        print("all reports regenerated")


if __name__ == "__main__":
    with run_lock.exclusive(ROOT):
        main()
