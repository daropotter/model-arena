#!/usr/bin/env python3
"""Hidden grader for filedock."""

import json
import random
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import organize_reference  # noqa: E402

VALID_DATES = [date(2025, 3, 15), date(2024, 12, 31),
               date(2023, 2, 28), date(2026, 1, 1),
               date(2026, 6, 30), date(2022, 11, 5)]
MAX_MANIFEST = 1_000_000


def build_inbox(base: Path, seed: int) -> None:
    rng = random.Random(seed)
    inbox = base / "inbox"
    inbox.mkdir(parents=True)

    def put(name: str, content: bytes) -> None:
        (inbox / name).write_bytes(content)

    for d in VALID_DATES:
        put(f"report-{d:%Y%m%d}.txt",
            f"content-{rng.randrange(1000)}\n".encode())
    put("report-20240229.txt", b"leap\n")
    put("report-20230229.txt", b"notleap\n")
    put("report-20260230.txt", b"impossible\n")
    put("report-20261301.txt", b"badmonth\n")
    put("report-2026010.txt", b"badlen\n")
    put("report-20260115.csv", b"wrongext\n")
    put("notes.txt", b"ignored\n")
    put("REPORT-20260101.TXT", b"uppercase\n")
    put("report-20260101.txt", b"")
    put("report-20260102.txt", b"dup-content\n")
    put("report-20260404.txt", b"dup-content\n")
    put("report-20260405.txt", b"dup-content\n")
    put("report-20251201.txt", b"same-date-a\n")
    put("report-20251201-b.txt", b"ignored variant\n")
    put("report-20250101.txt", b"same-name-collision\n")
    put("report-20250101-b.txt", b"other\n")

    # Exercise overwrite behavior and preservation of unrelated output files.
    old = base / "reports" / "2025" / "03" / "report-20250315.txt"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old destination bytes\n")
    (base / "reports" / "keep.bin").write_bytes(b"keep\x00me")


def read_manifest(path: Path):
    try:
        if path.stat().st_size > MAX_MANIFEST:
            return None, "manifest is too large"
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"manifest unreadable: {exc}"
    if not isinstance(value, dict) or set(value) != {"moved", "duplicates"}:
        return None, "manifest must have exactly moved and duplicates keys"
    for key in ("moved", "duplicates"):
        if not isinstance(value[key], list) or any(
                not isinstance(item, str) for item in value[key]):
            return None, f"manifest {key} must be a list of strings"
    return value, ""


def tree_snapshot(root: Path, manifest: Path):
    """Return exact relative directory names and file bytes, sans manifest."""
    entries = {}
    try:
        paths = list(root.rglob("*"))
        if len(paths) > 1_000:
            return None, "too many filesystem entries"
        for path in paths:
            if path == manifest:
                continue
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                entries[rel] = ("symlink", path.readlink().as_posix())
            elif path.is_dir():
                entries[rel] = ("dir",)
            elif path.is_file():
                if path.stat().st_size > 10_000_000:
                    return None, f"oversized file: {rel}"
                entries[rel] = ("file", path.read_bytes())
            else:
                entries[rel] = ("other",)
    except OSError as exc:
        return None, f"cannot inspect output tree: {exc}"
    return entries, ""


def run_submission(workspace: Path, inbox: Path, manifest: Path):
    try:
        proc = subprocess.run(
            [sys.executable, str(workspace / "organize.py"),
             str(inbox), str(manifest)],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as exc:
        return False, f"could not execute organize.py: {exc}"
    if proc.returncode != 0:
        return False, f"exit {proc.returncode}: {proc.stderr[-200:]}"
    return True, ""


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)
    results = []

    def record(name, passed, detail=""):
        results.append({"case": name, "passed": passed, "detail": detail})

    for seed in (7, 42):
        with tempfile.TemporaryDirectory() as tmp_name:
            base = Path(tmp_name)
            reference_root = base / "reference"
            candidate_root = base / "candidate"
            build_inbox(reference_root, seed)
            build_inbox(candidate_root, seed)
            reference_root.chmod(0o700)
            ref_manifest = reference_root / "manifest.json"
            got_manifest = candidate_root / "manifest.json"

            want_first = organize_reference(
                reference_root / "inbox", ref_manifest)
            ok, detail = run_submission(
                workspace, candidate_root / "inbox", got_manifest)
            got_first = None
            if ok:
                got_first, detail = read_manifest(got_manifest)
                ok = got_first == want_first
                if not ok and not detail:
                    detail = f"manifest {got_first!r} != {want_first!r}"
            if ok:
                want_tree, want_err = tree_snapshot(reference_root, ref_manifest)
                got_tree, got_err = tree_snapshot(candidate_root, got_manifest)
                ok = want_tree is not None and got_tree == want_tree
                if not ok:
                    detail = want_err or got_err or "resulting filesystem tree/bytes differ"
            record(f"seed{seed}-first-run", ok, detail)

            # Both second passes operate on their own first-pass output.
            want_second = organize_reference(
                reference_root / "inbox", ref_manifest)
            ok, detail = run_submission(
                workspace, candidate_root / "inbox", got_manifest)
            if ok:
                got_second, detail = read_manifest(got_manifest)
                ok = got_second == want_second == {"moved": [], "duplicates": []}
                if not ok and not detail:
                    detail = f"second manifest was {got_second!r}"
            if ok:
                want_tree, want_err = tree_snapshot(reference_root, ref_manifest)
                got_tree, got_err = tree_snapshot(candidate_root, got_manifest)
                ok = want_tree is not None and got_tree == want_tree
                if not ok:
                    detail = want_err or got_err or "second run changed filesystem tree/bytes"
            record(f"seed{seed}-idempotent", ok, detail)

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
