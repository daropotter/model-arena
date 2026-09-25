#!/usr/bin/env python3
"""Hidden grader for the order-export normalization task.

Runs the submission on unseen exports and compares the output CSV and report
JSON against the reference implementation of SPEC.md.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import normalize_files  # noqa: E402

HEADER = "order_id,customer,amount,currency,date,status"


def csv_text(rows, header=HEADER):
    return "\n".join([header] + [",".join(r) for r in rows]) + "\n"


CASES = {
    "amounts_and_currencies": (
        "order_id,customer,amount,currency,date,status\n"
        'a1,Alice,"1,234.50",USD,2026-01-01,paid\n'
        'a2,Bob,"1.234,50",EUR,2026-01-02,paid\n'
        "a3,Carol,$12.5,usd,2026-01-03,pending\n"
        "a4,Dan,(45.00),EUR,2026-01-04,pending\n"
        'a5,Eve,"(45,00)",USD,2026-01-05,cancelled\n'
        "a6,Frank,-0.005,USD,2026-01-06,paid\n"
        "a7,Ann,000123.40,USD,2026-01-07,paid\n"
    ),
    "dates": (
        "order_id,customer,amount,currency,date,status\n"
        "d1,Alice,1.00,EUR,2026-01-05,paid\n"
        "d2,Bob,1.00,EUR,01/05/2026,paid\n"
        "d3,Carol,1.00,EUR,1/5/2026,paid\n"
        'd4,Dan,1.00,EUR,"Jan 5, 2026",paid\n'
        "d5,Eve,1.00,EUR,jan 5 2026,paid\n"
        "d6,Frank,1.00,EUR,2026-02-30,paid\n"
        "d7,Gina,1.00,EUR,13/05/2026,paid\n"
        "d8,Hans,1.00,EUR,2026-1-05,paid\n"
        'd9,Ivan,1.00,EUR,"January 5, 2026",paid\n'
    ),
    "statuses_and_dups": (
        "order_id,customer,amount,currency,date,status\n"
        "s1,Alice,10.00,EUR,2026-01-01,PAID\n"
        "s1,Alice,10.00,EUR,2026-01-01,paid\n"
        "s1,Alice,10.000,EUR,2026-01-01,paid\n"
        "s2,Bob,10.00,EUR,2026-01-02,Paid\n"
        "s3,Carol,10.00,EUR,2026-01-03,pend.\n"
        "s4,Dan,10.00,EUR,2026-01-04, PENDING \n"
        "s5,Eve,10.00,EUR,2026-01-05,canceled\n"
        "s6,Frank,10.00,EUR,2026-01-06,Cancelled\n"
        "s7,Gina,10.00,EUR,2026-01-07,unknown\n"
    ),
    "structure_and_lexicographic": (
        "order_id,customer,amount,currency,date,status\n"
        "10,Zed,1.00,USD,2026-01-01,paid\n"
        "9,Amy,2.00,USD,2026-01-02,paid\n"
        "b,Bob,3.00,USD,2026-01-03,paid\n"
        "B,Bea,4.00,USD,2026-01-04,paid\n"
        "a,Aaa,5.00,USD,2026-01-05,paid\n"
        "\n"
        "order_id,customer,amount,currency,date,status\n"
        "c,Carl,6.00,USD,2026-01-06,paid\n"
        "extra,field,row\n"
        "\n"
        "d,Dee,7.00,USD,2026-01-07,paid\n"
    ),
    "quoting_and_customer": (
        "order_id,customer,amount,currency,date,status\n"
        'q1,"Smith, Alice",1.00,USD,2026-01-01,paid\n'
        'q2,"Bob  Jones",2.00,USD,2026-01-02,paid\n'
        'q3,"He said ""hi""",3.00,USD,2026-01-03,paid\n'
        'q4,"Line\nBreak",4.00,USD,2026-01-04,paid\n'
        "q5,,5.00,USD,2026-01-05,paid\n"
    ),
    "empty_and_totals": (
        "order_id,customer,amount,currency,date,status\n"
        "e1,A,0.00,USD,2026-01-01,paid\n"
        "e2,B,-0.00,USD,2026-01-02,paid\n"
        "e3,C,1.005,USD,2026-01-03,paid\n"
        "e4,D,2.005,USD,2026-01-04,paid\n"
        "e5,E,0,zz,2026-01-05,paid\n"
    ),
    "only_bad_rows": (
        "order_id,customer,amount,currency,date,status\n"
        ",A,1.00,USD,2026-01-01,paid\n"
        "x,B,1.00,USD,2026-01-01,paid,extra\n"
        "y,C,not-a-number,USD,2026-01-01,paid\n"
    ),
}


def run_submission(workspace: Path, text: str):
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "in.csv"
        out = Path(tmp) / "out.csv"
        rep = Path(tmp) / "report.json"
        inp.write_text(text)
        proc = subprocess.run(
            [sys.executable, "normalize.py", str(inp), str(out), str(rep)],
            cwd=workspace, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return None, None, f"exit {proc.returncode}: {proc.stderr[-200:]}"
        if not out.exists() or not rep.exists():
            return None, None, "missing output.csv or report.json"
        try:
            return out.read_text(), json.loads(rep.read_text()), None
        except json.JSONDecodeError as exc:
            return None, None, f"report is not valid json: {exc}"


def diff_csv(got: str, want: str):
    if got == want:
        return ""
    gl = got.splitlines()
    wl = want.splitlines()
    for i in range(max(len(gl), len(wl))):
        g = gl[i] if i < len(gl) else "<missing>"
        w = wl[i] if i < len(wl) else "<missing>"
        if g != w:
            return f"first difference at line {i}: got {g!r} expected {w!r}"
    return "differs in trailing bytes"


def diff_report(got: dict, want: dict):
    if set(got.keys()) != set(want.keys()):
        return f"keys {sorted(got.keys())} != {sorted(want.keys())}"
    for key in want:
        if got[key] != want[key]:
            return f"{key}: {got[key]!r} != {want[key]!r}"
    return ""


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)
    import tempfile as tf

    results = []
    with tf.TemporaryDirectory() as ref_tmp:
        ref_dir = Path(ref_tmp)
        for name, text in CASES.items():
            want_csv, want_report = normalize_files(
                _write(ref_dir, text), ref_dir / f"{name}.out.csv",
                ref_dir / f"{name}.report.json")
            got_csv, got_report, err = run_submission(workspace, text)
            if err:
                results.append({"case": name, "passed": False, "detail": err})
                continue
            d_csv = diff_csv(got_csv, want_csv)
            d_rep = diff_report(got_report, want_report)
            if not d_csv and not d_rep:
                results.append({"case": name, "passed": True, "detail": ""})
            else:
                detail = "; ".join(x for x in (d_csv, d_rep) if x)
                results.append({"case": name, "passed": False, "detail": detail})

    passed = all(r["passed"] for r in results)
    score = sum(1 for r in results if r["passed"]) / len(results)
    detail = "all hidden exports passed" if passed else "; ".join(
        f"{r['case']}: {r['detail']}" for r in results if not r["passed"])
    result = {"passed": passed, "score": round(score, 3),
              "detail": detail, "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


def _write(dir_path: Path, text: str) -> Path:
    p = dir_path / "input.csv"
    p.write_text(text)
    return p


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
