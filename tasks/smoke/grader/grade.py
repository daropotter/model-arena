#!/usr/bin/env python3
"""Prescreen smoke grader: check answer.txt equals the sum of numbers.txt.

The starter has no answer.txt, so a model that does nothing fails.
"""

import json
import sys
from pathlib import Path


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)

    expected_sum = sum(
        int(line.strip()) for line in (workspace / "numbers.txt").read_text().splitlines()
        if line.strip()
    )
    answer_path = workspace / "answer.txt"

    if not answer_path.exists():
        result = {"passed": False, "score": 0.0,
                  "detail": "answer.txt was not created: the model did not act"}
    else:
        got = answer_path.read_text().strip()
        # accept a trailing newline, reject anything else
        if got == str(expected_sum):
            result = {"passed": True, "score": 1.0, "detail": "correct sum"}
        else:
            result = {"passed": False, "score": 0.0,
                      "detail": f"answer.txt = {got!r}, expected {expected_sum}"}

    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
