#!/usr/bin/env python3
"""Re-grade existing runs in place, without re-running the models.

Use after fixing a grader: takes each run's saved workspace, runs the current
grader against it (in docker, workspace read-only), and rewrites the record's
score/passed/detail. Also updates all result reports.

Usage:
  python3 runner/regrade.py                      # every run with a live workspace
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


def latest_records(results_root: Path):
    """Latest record per (model, task), with its run directory."""
    latest = {}
    for path in sorted(results_root.glob("*/record.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        key = (record["model"], record["task"])
        finished = record.get("finished_at") or ""
        if key not in latest or finished > (latest[key][1].get("finished_at") or ""):
            latest[key] = (path, record)
    return latest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--task", nargs="*", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results_root = Path(args.results).resolve()
    tasks_dir = ROOT / "tasks"
    records = latest_records(results_root)

    regraded = 0
    skipped = 0
    changed_count = 0
    for (model, task), (record_path, record) in sorted(records.items()):
        if args.task and task not in args.task:
            continue
        if task == "smoke":
            continue
        workspace = Path(record.get("workspace") or "")
        if not workspace.exists():
            print(f"SKIP {model} x {task}: workspace gone")
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
        old_score, old_passed = record.get("score"), record.get("passed")
        record["passed"] = bool(result.get("passed"))
        record["score"] = float(result.get("score", 0.0))
        record["detail"] = result.get("detail", "")
        record["regraded_at"] = datetime.now(timezone.utc).isoformat()
        (record_path.parent / "grade" / "result.json").write_text(
            json.dumps(result, indent=2))
        record_path.write_text(json.dumps(record, indent=2))
        regraded += 1
        if (old_score, old_passed) != (record["score"], record["passed"]):
            changed_count += 1
            print(f"CHANGED {model} x {task}: "
                  f"{old_score:.2f}/{old_passed} -> "
                  f"{record['score']:.2f}/{record['passed']}")
        else:
            print(f"same {model} x {task}: {record['score']:.2f}")

    print(f"\nre-graded: {regraded}, changed: {changed_count}, skipped: {skipped}")

    if not args.dry_run and regraded:
        all_records = arena.load_all_records(results_root)
        arena.write_report(all_records, results_root)
        print("report regenerated: results/report.md")


if __name__ == "__main__":
    main()
