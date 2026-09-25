#!/usr/bin/env python3
"""Hidden grader for sumtool.

Runs the submission CLI on unseen inputs and compares against the reference
implementation of the contract. Reports per-case scores.
"""

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

CASES = [
    ("decimals", "1.5, 2.5"),
    ("mixed_decimals", "1.5, 2"),
    ("negative_decimals", "-1.5, 0.5"),
    ("signed_ints", "-2, +1"),
    ("leading_zeros", "007, 0.10"),
    ("big_numbers", "999999999999999999, 1"),
    ("whitespace", "  1 , 2  ,3"),
    ("zero_sum", "5, -5"),
    ("half", "0.5"),
    ("cancel_to_int", "1.5, -1.5"),
    ("plus_decimal", "+2.25, -0.25"),
    ("minus_zero_decimal", "-0.5, 0.5"),
    ("invalid_letter", "1, a"),
    ("invalid_double_dot", "12.3.4, 1"),
    ("invalid_currency", "$5, 2"),
    ("invalid_sci", "1e3, 2"),
    ("invalid_empty_tail", "1, "),
    ("invalid_empty", ""),
]


def reference(text: str):
    tokens = [t.strip() for t in text.split(",")]
    if not tokens or any(t == "" for t in tokens):
        return 1, "", "error\n"
    total = Decimal("0")
    for token in tokens:
        sign, body = 1, token
        if body.startswith("+"):
            body = body[1:]
        elif body.startswith("-"):
            sign, body = -1, body[1:]
        if not body:
            return 1, "", "error\n"
        if "." in body:
            whole, frac = body.split(".", 1)
            if (not whole.isdigit()) or (not frac) or (not frac.isdigit()):
                return 1, "", "error\n"
        elif not body.isdigit():
            return 1, "", "error\n"
        total += sign * Decimal(body)
    if total == total.to_integral_value():
        return 0, str(total.quantize(Decimal("1"))) + "\n", ""
    return 0, str(total) + "\n", ""


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    results = []
    total = 0.0
    earned = 0.0
    for name, text in CASES:
        want_rc, want_out, want_err = reference(text)
        try:
            proc = subprocess.run(
                [sys.executable, str(workspace / "sumtool.py"), text],
                capture_output=True, text=True, timeout=30,
            )
            got_rc, got_out, got_err = proc.returncode, proc.stdout, proc.stderr
        except FileNotFoundError:
            results.append({"case": name, "passed": False,
                            "detail": "sumtool.py missing"})
            total += 1
            continue
        total += 1
        ok = (got_rc == want_rc and got_out == want_out
              and (want_rc == 0 or got_err.strip() == want_err.strip()))
        if ok:
            earned += 1
            results.append({"case": name, "passed": True, "detail": ""})
        else:
            results.append({
                "case": name, "passed": False,
                "detail": (f"rc {got_rc} out {got_out!r} err {got_err!r} "
                           f"expected rc {want_rc} out {want_out!r}"),
            })

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
