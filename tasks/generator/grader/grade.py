#!/usr/bin/env python3
"""Hidden grader for the generator task.

Checks predictions on unseen seeds, at offsets the samples do not cover, and
compares against the hidden reference algorithm. Also rejects hardcoded
sample answers.
"""

import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import generate, SAMPLE_SEEDS  # noqa: E402

SEED_POOL = [
    7, 31337, 424242, 8675309, 1234567890, 2147483647, 2147483646,
    999999999, 536870912, 1073741824, 65535, 1048576,
]


def run_submission(workspace: Path, seed: int, n: int):
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, "predict.py", str(seed), str(n)],
            cwd=workspace, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            return None, f"exit {proc.returncode}: {proc.stderr[-200:]}"
        lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
        if len(lines) != n:
            return None, f"expected {n} lines, got {len(lines)}"
        try:
            return [int(l) for l in lines], None
        except ValueError as exc:
            return None, f"non-integer output: {exc}"


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)
    rng = random.Random(20260101)
    results = []

    # Case 1: unseen seeds, first 50 outputs
    seeds = rng.sample(SEED_POOL, 5)
    ok = 0
    detail_errors = []
    for seed in seeds:
        want = generate(seed, 50)
        got, err = run_submission(workspace, seed, 50)
        if err:
            detail_errors.append(f"seed {seed}: {err}")
            continue
        mismatch = next((i for i, (g, w) in enumerate(zip(got, want)) if g != w), None)
        if mismatch is None:
            ok += 1
        else:
            detail_errors.append(
                f"seed {seed} step {mismatch + 1}: {got[mismatch]} != {want[mismatch]}")
    results.append({"case": "unseen_seeds_short", "passed": ok == len(seeds),
                    "detail": "" if ok == len(seeds) else "; ".join(detail_errors)})

    # Case 2: deep offsets: skip ahead using a seed with known long run
    deep_seed = 555555
    skip = 0
    ok = 0
    errors = []
    for _ in range(10):
        skip += rng.randint(50, 200)
        want = generate(deep_seed, skip)[-20:]
        got, err = run_submission(workspace, deep_seed, skip)
        if err:
            errors.append(err)
            continue
        if got[-20:] == want:
            ok += 1
    results.append({"case": "deep_offsets", "passed": ok == 10,
                    "detail": "" if ok == 10 else "; ".join(errors[:3])})

    # Case 3: long run, 500 values, must match exactly
    want = generate(31337, 500)
    got, err = run_submission(workspace, 31337, 500)
    results.append({"case": "long_run_500",
                    "passed": got == want,
                    "detail": err or "mismatch in first 500 outputs"})

    # Case 4: sample seeds at a step beyond the recorded samples
    errors = []
    for seed in SAMPLE_SEEDS:
        want = generate(seed, 60)[45:]
        got, err = run_submission(workspace, seed, 60)
        if err:
            errors.append(f"{seed}: {err}")
        elif got[45:] != want:
            errors.append(f"{seed}: mismatch after sample range")
    results.append({"case": "samples_extrapolated", "passed": not errors,
                    "detail": "; ".join(errors)})

    passed = all(r["passed"] for r in results)
    score = sum(1 for r in results if r["passed"]) / len(results)
    detail = "generator reconstructed exactly" if passed else "; ".join(
        f"{r['case']}: {r['detail']}" for r in results if not r["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
