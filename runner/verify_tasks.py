#!/usr/bin/env python3
"""Verify every task's grader and canonical starter floor.

The starter must fail and the reference solution must pass. Runs the task
programs locally without Docker or an LLM; container isolation is not checked.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"


def grade_locally(task_dir: Path, workspace: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.json"
        proc = subprocess.run(
            [sys.executable, str(task_dir / "grader" / "grade.py"),
             str(workspace), str(out)],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode == 0 and out.exists():
            try:
                result = json.loads(out.read_text())
                if type(result.get("passed")) is not bool:
                    raise ValueError("passed is not boolean")
                if type(result.get("score")) not in (int, float):
                    raise ValueError("score is not numeric")
                return result
            except (json.JSONDecodeError, ValueError) as exc:
                return {"passed": False, "score": 0.0,
                        "detail": f"invalid grader result: {exc}"}
        return {"passed": False, "score": 0.0,
                "detail": f"grader crashed rc={proc.returncode}: {proc.stderr[-400:]}"}


def build_variant(task_dir: Path, variant: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=f"arena-verify-{variant}-"))
    shutil.copytree(task_dir / "starter", tmp, dirs_exist_ok=True)
    extra = task_dir / variant
    if extra.exists():
        for item in extra.rglob("*"):
            if item.is_file():
                rel = item.relative_to(extra)
                dest = tmp / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
    return tmp


def main():
    failures = []
    try:
        baselines = json.loads((TASKS / "baselines.json").read_text())
    except (OSError, json.JSONDecodeError):
        baselines = {}
    for task_dir in sorted(p for p in TASKS.iterdir() if (p / "meta.json").exists()):
        name = task_dir.name
        starter = build_variant(task_dir, "starter")
        solution = build_variant(task_dir, "solution")
        try:
            r_starter = grade_locally(task_dir, starter)
            r_solution = grade_locally(task_dir, solution)
            ok_starter = not r_starter["passed"]
            ok_solution = r_solution["passed"] and r_solution["score"] >= 0.99
            status = "OK " if (ok_starter and ok_solution) else "BAD"
            print(f"{status} {name:16s} starter={r_starter['score']:.2f} "
                  f"solution={r_solution['score']:.2f}")
            if not ok_starter:
                print(f"    starter should fail: {r_starter['detail'][:200]}")
                failures.append(name)
            expected_floor = baselines.get(name)
            # cronlog intentionally races concurrent processes; an unlocked
            # starter can occasionally preserve one extra batch by luck.
            if name != "cronlog" and (expected_floor is None or
                                      abs(r_starter["score"] - expected_floor) > 1e-9):
                print(f"    baseline drift: recorded={expected_floor!r}, "
                      f"actual={r_starter['score']!r}")
                failures.append(name)
            if not ok_solution:
                print(f"    solution should pass: {r_solution['detail'][:200]}")
                failures.append(name)
        finally:
            shutil.rmtree(starter, ignore_errors=True)
            shutil.rmtree(solution, ignore_errors=True)
    if failures:
        print(f"\n{len(failures)} problem(s): {sorted(set(failures))}")
        return 1
    print("\nall graders verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
