#!/usr/bin/env python3
"""Hidden grader for filedock.

Generates unseen inboxes (deterministic seeds) and compares the produced
manifest + directory layout against the reference implementation of
README.md.
"""

import json
import random
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import organize_reference  # noqa: E402

HEADER = "report-"
PATTERN_FILES = [
    "report-20260230.txt",   # impossible date (Feb 30)
    "report-20251301.txt",   # month 13
    "report-20260099.txt",   # day 99
    "report-2026010.txt",    # bad length
    "report-20260115a.txt",  # trailing junk
    "report-20260115.csv",   # wrong extension
    "notes.txt",             # no pattern at all
    "REPORT-20260115.TXT",   # uppercase
]

VALID_DATES = [date(2025, 3, 15), date(2024, 12, 31),
               date(2023, 2, 28), date(2026, 1, 1),
               date(2026, 6, 30), date(2022, 11, 5)]


def build_inbox(base: Path, seed: int) -> list[str]:
    """Create an inbox; return the filenames placed there."""
    rng = random.Random(seed)
    inbox = base / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    placed: list[str] = []

    def put(name: str, content: str):
        (inbox / name).write_text(content)
        placed.append(name)

    for d in VALID_DATES:
        put(f"report-{d.strftime('%Y%m%d')}.txt",
            f"content-{rng.randrange(1000)}\n")

    put("report-20240229.txt", "leap\n")  # 2024 is a leap year — valid
    put("report-20230229.txt", "notleap\n")  # 2023 is not — invalid
    put("report-20260230.txt", "impossible\n")
    put("report-20261301.txt", "badmonth\n")
    put("report-2026010.txt", "badlen\n")
    put("report-20260115.csv", "wrongext\n")
    put("notes.txt", "ignored\n")
    put("REPORT-20260101.TXT", "uppercase\n")

    put("report-20260101.txt", "")  # empty file, valid
    put("report-20260102.txt", "dup-content\n")
    put("report-20260404.txt", "dup-content\n")  # same content, other date
    put("report-20260405.txt", "dup-content\n")  # third copy

    put("report-20251201.txt", "same-date-a\n")
    put("report-20251201-b.txt", "")  # non-matching name, valid content?

    put("report-20250101.txt", "same-name-collision\n")
    put("report-20250101-b.txt", "other\n")

    return placed


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    results = []
    total = 0.0
    earned = 0.0

    for seed in (7, 42):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inbox = tmp / "inbox"
            build_inbox(tmp, seed)
            manifest = tmp / "manifest.json"
            want = organize_reference(inbox, manifest)

            # reference mutated the inbox; build a fresh one for the submission
            sub_inbox = tmp / "sub-inbox"
            build_inbox(tmp / "sub", seed)
            sub_inbox = tmp / "sub" / "inbox"
            got_manifest = tmp / "got-manifest.json"
            try:
                proc = subprocess.run(
                    [sys.executable, str(workspace / "organize.py"),
                     str(sub_inbox), str(got_manifest)],
                    capture_output=True, text=True, timeout=120,
                )
                rc, err = proc.returncode, proc.stderr
            except FileNotFoundError:
                results.append({"case": f"seed{seed}", "passed": False,
                                "detail": "organize.py missing"})
                total += 1
                continue

            total += 1
            if rc != 0:
                results.append({"case": f"seed{seed}", "passed": False,
                                "detail": f"exit {rc}: {err[-200:]}"})
                continue

            try:
                got = json.loads(got_manifest.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                results.append({"case": f"seed{seed}", "passed": False,
                                "detail": f"manifest unreadable: {exc}"})
                continue

            want_manifest = json.loads(manifest.read_text())
            ok = (got.get("moved") == want_manifest.get("moved")
                  and got.get("duplicates") == want_manifest.get("duplicates"))
            detail = ""
            if not ok:
                detail = (f"moved {got.get('moved')} != "
                          f"{want_manifest.get('moved')}; duplicates "
                          f"{got.get('duplicates')} != "
                          f"{want_manifest.get('duplicates')}")
            results.append({"case": f"seed{seed}", "passed": ok,
                            "detail": detail})
            if ok:
                earned += 1

        # idempotency check on the same (now processed) inbox
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            inbox = tmp / "inbox"
            placed = build_inbox(tmp, seed)
            manifest = tmp / "manifest.json"
            organize_reference(inbox, manifest)  # first pass with reference
            again = tmp / "again.json"
            total += 1
            try:
                proc = subprocess.run(
                    [sys.executable, str(workspace / "organize.py"),
                     str(inbox), str(again)],
                    capture_output=True, text=True, timeout=120,
                )
                got = json.loads(again.read_text())
            except Exception as exc:  # noqa: BLE001
                results.append({"case": f"idempotent-{seed}", "passed": False,
                                "detail": str(exc)})
                continue
            ok = got == {"moved": [], "duplicates": []}
            results.append({"case": f"idempotent-{seed}", "passed": ok,
                            "detail": "" if ok else f"got {got}"})
            if ok:
                earned += 1

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
