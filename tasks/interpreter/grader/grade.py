#!/usr/bin/env python3
"""Hidden grader for the interpreter."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import CASES, ERRORS  # noqa: E402

MAX_OUTPUT = 1_000_000


def run(workspace: Path, content: str):
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        in_path = tmp / "in.json"
        out_path = tmp / "out.json"
        in_path.write_text(content)
        try:
            proc = subprocess.run(
                [sys.executable, str(workspace / "eval.py"),
                 str(in_path), str(out_path)],
                capture_output=True, text=True, timeout=15,
            )
        except subprocess.TimeoutExpired:
            return {"run_error": "timed out", "rc": None, "stderr": "",
                    "output_exists": out_path.exists(), "output": None}
        except OSError as exc:
            return {"run_error": f"could not execute eval.py: {exc}",
                    "rc": None, "stderr": "",
                    "output_exists": out_path.exists(), "output": None}

        output = None
        read_error = ""
        if out_path.exists():
            try:
                if out_path.stat().st_size > MAX_OUTPUT:
                    read_error = "output is too large"
                else:
                    output = json.loads(out_path.read_text())
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                read_error = f"output is not valid JSON: {exc}"
        return {"run_error": read_error, "rc": proc.returncode,
                "stderr": proc.stderr, "output_exists": out_path.exists(),
                "output": output}


def success_result(run_result, want):
    if run_result["run_error"]:
        return False, run_result["run_error"]
    if run_result["rc"] != 0:
        return False, f"exit {run_result['rc']}: {run_result['stderr'][-120:]}"
    got = run_result["output"]
    if (not isinstance(got, dict) or set(got) != {"result"}
            or type(got["result"]) is not int or got["result"] != want):
        return False, f"got {got!r}, want {{'result': {want!r}}}"
    return True, ""


def error_result(run_result):
    if run_result["run_error"]:
        return False, run_result["run_error"]
    if run_result["rc"] != 1:
        return False, f"expected exit 1, got {run_result['rc']}"
    if run_result["stderr"].strip() != "error":
        return False, f"stderr must be 'error', got {run_result['stderr'][-120:]!r}"
    if run_result["output_exists"]:
        return False, "output file exists after error"
    return True, ""


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)
    results = []

    for name, node, want in CASES:
        ok, detail = success_result(run(workspace, json.dumps(node)), want)
        results.append({"case": name, "passed": ok, "detail": detail})

    for name, node in ERRORS:
        ok, detail = error_result(run(workspace, json.dumps(node)))
        results.append({"case": name, "passed": ok, "detail": detail})

    for name, content in [
        ("malformed_json", "{"),
        ("empty_input", ""),
        ("scalar_input", "1"),
        ("bool_input", "true"),
    ]:
        ok, detail = error_result(run(workspace, content))
        results.append({"case": name, "passed": ok, "detail": detail})

    earned = sum(case["passed"] for case in results)
    score = earned / len(results) if results else 0.0
    passed = all(case["passed"] for case in results)
    detail = "all hidden cases passed" if passed else "; ".join(
        f"{case['case']}: {case['detail']}" for case in results
        if not case["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
