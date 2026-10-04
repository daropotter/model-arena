#!/usr/bin/env python3
"""Hidden grader for merge: run the submission on unseen three-way inputs."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import merge_reference, CASES, ERRORS  # noqa: E402


def run(workspace: Path, payload):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        in_path = tmp / "in.json"
        out_path = tmp / "out.json"
        in_path.write_text(json.dumps(payload))
        try:
            proc = subprocess.run(
                [sys.executable, str(workspace / "merge.py"),
                 str(in_path), str(out_path)],
                capture_output=True, text=True, timeout=15,
            )
        except subprocess.TimeoutExpired:
            return None, None, "", False, "timed out"
        except OSError as exc:
            return None, None, "", False, str(exc)
        if proc.returncode != 0:
            return None, proc.returncode, proc.stderr, out_path.exists(), ""
        try:
            if out_path.stat().st_size > 1_000_000:
                raise ValueError("output too large")
            got = json.loads(out_path.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            return None, 0, proc.stderr, out_path.exists(), str(exc)
        return got, 0, proc.stderr, True, ""


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    results = []
    total = 0.0
    earned = 0.0

    for name, base, ours, theirs in CASES:
        total += 1
        want = merge_reference(base, ours, theirs)
        payload = {"base": base, "ours": ours, "theirs": theirs}
        got, rc, _, _, run_error = run(workspace, payload)
        if rc != 0 or run_error:
            results.append({"case": name, "passed": False,
                            "detail": run_error or f"exit {rc}"})
            continue
        if got != want:
            results.append({"case": name, "passed": False,
                            "detail": f"got {got}, want {want}"})
            continue
        earned += 1
        results.append({"case": name, "passed": True, "detail": ""})

    for name, payload in ERRORS:
        total += 1
        _, rc, stderr, output_exists, run_error = run(workspace, payload)
        if not run_error and rc == 1 and stderr.strip() == "error" \
                and not output_exists:
            earned += 1
            results.append({"case": name, "passed": True, "detail": ""})
        else:
            results.append({"case": name, "passed": False,
                            "detail": run_error or "invalid error contract"})

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
