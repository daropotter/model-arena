#!/usr/bin/env python3
"""Hidden grader for pipeline.

Runs the submission's pack/unpack on unseen inputs and compares against the
reference implementation of SPEC.md. Includes exact pipe-file comparison,
round trips, and malformed-pipe rejection.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import pack_reference, unpack_reference  # noqa: E402

ROUNDTRIPS = [
    ("mixed_types", {"s": "hello", "i": 5, "f": 0.5, "b": True, "n": None}),
    ("escaped_strings", {"tab": "a\tb", "nl": "a\nb", "backslash": "a\\b",
                         "cr": "a\rb", "combo": "x\t\\\n\r"}),
    ("cr_trailing", {"v": "abc\r"}),
    ("cr_leading", {"v": "\rabc"}),
    ("cr_only", {"v": "\r"}),
    ("cr_in_key", {"k\rk": "v"}),
    ("cr_multi", {"a": "x\r", "b": "\ry", "c": "z\rw"}),
    ("key_sort", {"z": "last", "a": "first", "m": "mid"}),
    ("negative_numbers", {"i": -42, "f": -1.5}),
    ("bool_variants", {"t": True, "f": False}),
    ("empty_string", {"empty": ""}),
    ("float_forms", {"big": 1000.0, "small": 1e-05}),
    ("special_key", {"k\tey": "tabbed key"}),
]

BAD_PIPES = [
    ("wrong_header", "pipe2\na\tsx\n"),
    ("missing_tab", "pipe1\nnoseparator\n"),
    ("bad_typecode", "pipe1\na\tqx\n"),
    ("bad_int", "pipe1\na\ti12x\n"),
    ("bad_bool", "pipe1\na\tbTRUE\n"),
    ("bad_escape", "pipe1\na\tsx\\q\n"),
    ("bad_escape_in_key", "pipe1\nke\\q\tsx\n"),
    ("dangling_escape", "pipe1\na\tsx\\"),
    ("bad_float", "pipe1\na\tfnotafloat\n"),
]


def run(tool, workspace: Path, in_path: Path, out_path: Path):
    proc = subprocess.run(
        [sys.executable, str(workspace / tool), str(in_path), str(out_path)],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    results = []
    total = 0.0
    earned = 0.0

    for name, payload in ROUNDTRIPS:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            in_json = tmp / "in.json"
            in_json.write_text(json.dumps(payload))

            pipe_ref = tmp / "ref.pipe"
            back_ref = tmp / "ref.json"
            pack_reference(in_json, pipe_ref)
            unpack_reference(pipe_ref, back_ref)
            want_pipe = pipe_ref.read_text()
            want_json = json.loads(back_ref.read_text())

            pipe_got = tmp / "got.pipe"
            back_got = tmp / "got.json"
            total += 1
            rc, _, err = run("pack.py", workspace, in_json, pipe_got)
            if rc != 0:
                results.append({"case": name, "passed": False,
                                "detail": f"pack exit {rc}: {err[-120:]}"})
                continue
            if pipe_got.read_text() != want_pipe:
                results.append({
                    "case": name, "passed": False,
                    "detail": f"pipe bytes differ: got {pipe_got.read_text()!r} "
                              f"expected {want_pipe!r}"})
                continue
            rc, _, err = run("unpack.py", workspace, pipe_got, back_got)
            if rc != 0:
                results.append({"case": name, "passed": False,
                                "detail": f"unpack exit {rc}: {err[-120:]}"})
                continue
            got_json = json.loads(back_got.read_text())
            if got_json != want_json:
                results.append({"case": name, "passed": False,
                                "detail": f"json {got_json} != {want_json}"})
                continue
            earned += 1
            results.append({"case": name, "passed": True, "detail": ""})

    for name, content in BAD_PIPES:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bad = tmp / "bad.pipe"
            out_json = tmp / "out.json"
            bad.write_text(content)
            total += 1
            rc, _, _ = run("unpack.py", workspace, bad, out_json)
            if rc != 0 and not out_json.exists():
                earned += 1
                results.append({"case": name, "passed": True, "detail": ""})
            else:
                results.append({"case": name, "passed": False,
                                "detail": f"rc={rc}, output exists="
                                          f"{out_json.exists()}"})

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
