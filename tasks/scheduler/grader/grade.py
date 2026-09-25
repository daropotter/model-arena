#!/usr/bin/env python3
"""Hidden grader for scheduler.

Runs the submission on unseen instances and checks:
  - valid output (order is a permutation, late matches the order),
  - feasibility of the order,
  - `late` equals the reference minimum,
  - invalid inputs are rejected.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import (schedule_reference, feasible, late_count,  # noqa: E402
                       validate)

INSTANCES = [
    ("simple", {"jobs": [
        {"id": "a", "duration": 3, "deadline": 8, "depends": []},
        {"id": "b", "duration": 2, "deadline": 5, "depends": []},
    ]}),
    ("anti_greedy", {"jobs": [
        {"id": "long", "duration": 5, "deadline": 5, "depends": []},
        {"id": "short", "duration": 1, "deadline": 2, "depends": []},
    ]}),
    ("chain", {"jobs": [
        {"id": "a", "duration": 2, "deadline": 4, "depends": []},
        {"id": "b", "duration": 2, "deadline": 6, "depends": ["a"]},
        {"id": "c", "duration": 2, "deadline": 8, "depends": ["b"]},
    ]}),
    ("diamond", {"jobs": [
        {"id": "a", "duration": 1, "deadline": 5, "depends": []},
        {"id": "b", "duration": 1, "deadline": 6, "depends": ["a"]},
        {"id": "c", "duration": 1, "deadline": 6, "depends": ["a"]},
        {"id": "d", "duration": 1, "deadline": 8, "depends": ["b", "c"]},
    ]}),
    ("deadline_race", {"jobs": [
        {"id": "a", "duration": 1, "deadline": 1, "depends": []},
        {"id": "b", "duration": 1, "deadline": 2, "depends": []},
        {"id": "c", "duration": 1, "deadline": 3, "depends": []},
        {"id": "d", "duration": 1, "deadline": 3, "depends": []},
    ]}),
    ("impossible", {"jobs": [
        {"id": "a", "duration": 5, "deadline": 3, "depends": []},
        {"id": "b", "duration": 5, "deadline": 100, "depends": []},
    ]}),
]

INVALID = [
    ("empty_jobs", {"jobs": []}),
    ("missing_deadline", {"jobs": [
        {"id": "a", "duration": 3, "depends": []}]}),
    ("zero_duration", {"jobs": [
        {"id": "a", "duration": 0, "deadline": 3, "depends": []}]}),
    ("duplicate_ids", {"jobs": [
        {"id": "a", "duration": 1, "deadline": 3, "depends": []},
        {"id": "a", "duration": 1, "deadline": 3, "depends": []}]}),
    ("unknown_dep", {"jobs": [
        {"id": "a", "duration": 1, "deadline": 3, "depends": ["zzz"]}]}),
    ("self_dep", {"jobs": [
        {"id": "a", "duration": 1, "deadline": 3, "depends": ["a"]}]}),
    ("cycle", {"jobs": [
        {"id": "a", "duration": 1, "deadline": 3, "depends": ["b"]},
        {"id": "b", "duration": 1, "deadline": 3, "depends": ["a"]}]}),
]


def run(workspace: Path, payload):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_path = tmp / "in.json"
        out_path = tmp / "out.json"
        in_path.write_text(json.dumps(payload))
        proc = subprocess.run(
            [sys.executable, str(workspace / "scheduler.py"),
             str(in_path), str(out_path)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            return None, proc.returncode
        return json.loads(out_path.read_text()), proc.returncode


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    results = []
    total = 0.0
    earned = 0.0

    for name, payload in INSTANCES:
        total += 1
        want = schedule_reference(payload)
        ids, deps, dur, deadline = validate(payload)
        got, rc = run(workspace, payload)
        if got is None:
            results.append({"case": name, "passed": False,
                            "detail": f"exit {rc}"})
            continue
        if not isinstance(got, dict) or set(got.get("order") or []) != set(ids) \
                or "late" not in got:
            results.append({"case": name, "passed": False,
                            "detail": f"bad output shape: {got}"})
            continue
        order = got["order"]
        if sorted(order) != sorted(ids):
            results.append({"case": name, "passed": False,
                            "detail": "order is not a permutation"})
            continue
        if not feasible(order, deps):
            results.append({"case": name, "passed": False,
                            "detail": "order violates dependencies"})
            continue
        if got["late"] != late_count(order, deps, dur, deadline):
            results.append({"case": name, "passed": False,
                            "detail": f"late {got['late']} does not match "
                                      f"the order"})
            continue
        if got["late"] != want["late"]:
            results.append({"case": name, "passed": False,
                            "detail": f"late {got['late']} != minimum "
                                      f"{want['late']}"})
            continue
        earned += 1
        results.append({"case": name, "passed": True, "detail": ""})

    for name, payload in INVALID:
        total += 1
        got, rc = run(workspace, payload)
        if rc != 0:
            earned += 1
            results.append({"case": name, "passed": True, "detail": ""})
        else:
            results.append({"case": name, "passed": False,
                            "detail": f"accepted invalid input: {got}"})

    score = earned / total if total else 0.0
    passed = all(r["passed"] for r in results)
    detail = "all hidden cases passed" if passed else "; ".join(
        f"{r['case']}: {r['detail']}" for r in results if not r["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
