#!/usr/bin/env python3
"""Schedule jobs on one machine. See SPEC.md for the contract."""

import json
import sys
from pathlib import Path


def schedule(payload: dict) -> dict:
    jobs = payload.get("jobs", [])
    # no validation of deadlines used — bug: deadlines are ignored entirely
    order = [job["id"] for job in jobs]
    finish = 0
    late = 0
    for job in jobs:
        finish += job["duration"]
        if finish > job["deadline"]:
            late += 1
    return {"order": order, "late": late}


def main() -> None:
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        payload = json.loads(Path(sys.argv[1]).read_text())
        result = schedule(payload)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
