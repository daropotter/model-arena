#!/usr/bin/env python3
"""Hidden grader for the ledger task.

Runs the submission CLI on unseen inputs and compares against the reference
implementation of SPEC.md. Reports per-case scores.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import summarize_reference  # noqa: E402

CASES = [
    ("round_ties", {
        "transactions": [
            {"id": f"t{i}", "account": "a", "amount": amt,
             "timestamp": f"2026-01-0{i + 1}T00:00:00+00:00"}
            for i, amt in enumerate(["2.50", "1.50", "0.50", "3.50", "0.10"])
        ]
    }),
    ("negative_amounts", {
        "transactions": [
            {"id": "n1", "account": "a", "amount": "-12.50",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "n2", "account": "a", "amount": "-0.50",
             "timestamp": "2026-01-02T00:00:00+00:00"},
            {"id": "n3", "account": "b", "amount": "100.00",
             "timestamp": "2026-01-03T00:00:00+00:00"},
            {"id": "n4", "account": "b", "amount": "-95.00",
             "timestamp": "2026-01-04T00:00:00+00:00"},
        ]
    }),
    ("zero_amounts_not_counted", {
        "transactions": [
            {"id": "z1", "account": "a", "amount": "0.00",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "z2", "account": "a", "amount": "0.00",
             "timestamp": "2026-01-02T00:00:00+00:00"},
            {"id": "z3", "account": "a", "amount": "5.50",
             "timestamp": "2026-01-03T00:00:00+00:00"},
            {"id": "z4", "account": "empty", "amount": "0.00",
             "timestamp": "2026-01-04T00:00:00+00:00"},
        ]
    }),
    ("stable_ties", {
        "transactions": [
            {"id": "c", "account": "a", "amount": "1.00",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "a", "account": "a", "amount": "2.00",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "b", "account": "a", "amount": "3.00",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "d", "account": "a", "amount": "4.00",
             "timestamp": "2025-12-31T23:00:00+00:00"},
        ]
    }),
    ("decimal_precision", {
        "transactions": [
            {"id": "p1", "account": "a", "amount": "0.01",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "p2", "account": "a", "amount": "0.04",
             "timestamp": "2026-01-02T00:00:00+00:00"},
            {"id": "p3", "account": "a", "amount": "123456.78",
             "timestamp": "2026-01-03T00:00:00+00:00"},
            {"id": "p4", "account": "a", "amount": "-0.05",
             "timestamp": "2026-01-04T00:00:00+00:00"},
            {"id": "p5", "account": "a", "amount": "99999.99",
             "timestamp": "2026-01-05T00:00:00+00:00"},
        ]
    }),
    ("balance_rounding", {
        "transactions": [
            {"id": "r1", "account": "a", "amount": "0.005",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "r2", "account": "a", "amount": "0.005",
             "timestamp": "2026-01-02T00:00:00+00:00"},
            {"id": "r3", "account": "a", "amount": "0.015",
             "timestamp": "2026-01-03T00:00:00+00:00"},
        ]
    }),
    ("fees_total_rounding", {
        "transactions": [
            {"id": "f1", "account": "a", "amount": "10.50",
             "timestamp": "2026-01-01T00:00:00+00:00"},
            {"id": "f2", "account": "a", "amount": "10.50",
             "timestamp": "2026-01-02T00:00:00+00:00"},
            {"id": "f3", "account": "a", "amount": "10.50",
             "timestamp": "2026-01-03T00:00:00+00:00"},
        ]
    }),
]

WEIGHTS = {"cli_contract": 2.0}
CASE_WEIGHT = 1.0


def run_cli(workspace: Path, payload: dict):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        in_path = Path(tmp) / "in.json"
        out_path = Path(tmp) / "out.json"
        in_path.write_text(json.dumps(payload))
        proc = subprocess.run(
            [sys.executable, "-m", "ledger", "summarize", str(in_path), str(out_path)],
            cwd=workspace, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return None, f"exit {proc.returncode}: {proc.stderr.strip()[-200:]}"
        if not out_path.exists():
            return None, "no output file"
        try:
            return json.loads(out_path.read_text()), None
        except json.JSONDecodeError as exc:
            return None, f"invalid json: {exc}"


def compare(got: dict, want: dict) -> str:
    if got.keys() != want.keys():
        return f"top-level keys {sorted(got.keys())} != {sorted(want.keys())}"
    for t in got.get("transactions", []):
        if not isinstance(t, dict) or "id" not in t:
            return f"malformed transaction entry: {t!r}"
    got_ids = [t["id"] for t in got.get("transactions", [])]
    want_ids = [t["id"] for t in want["transactions"]]
    if got_ids != want_ids:
        return f"transaction order {got_ids} != {want_ids}"
    for g, w in zip(got["transactions"], want["transactions"]):
        if str(g.get("fee")) != w["fee"]:
            return f"fee for {w['id']}: {g.get('fee')!r} != {w['fee']!r}"
    if sorted(got.get("accounts", {}).keys()) != sorted(want["accounts"].keys()):
        return (f"accounts {sorted(got.get('accounts', {}).keys())} != "
                f"{sorted(want['accounts'].keys())}")
    for name, w in want["accounts"].items():
        g = got["accounts"][name]
        if str(g.get("balance")) != w["balance"]:
            return f"balance {name}: {g.get('balance')!r} != {w['balance']!r}"
        if int(g.get("count", -1)) != w["count"]:
            return f"count {name}: {g.get('count')!r} != {w['count']!r}"
    if str(got.get("fees_total")) != want["fees_total"]:
        return f"fees_total {got.get('fees_total')!r} != {want['fees_total']!r}"
    return ""


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    results = []
    total = 0.0
    earned = 0.0

    for name, payload in CASES:
        want = summarize_reference(payload)
        got, err = run_cli(workspace, payload)
        total += CASE_WEIGHT
        if got is None:
            results.append({"case": name, "passed": False,
                            "detail": err or "no result"})
            continue
        diff = compare(got, want)
        if diff == "":
            earned += CASE_WEIGHT
            results.append({"case": name, "passed": True, "detail": ""})
        else:
            results.append({"case": name, "passed": False, "detail": diff})

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
