#!/usr/bin/env python3
"""Hidden grader for billingreview: scores review.json against the problems
planted in the change (issues.json). Scoring lives in reviewlib.py."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reviewlib  # noqa: E402

if __name__ == "__main__":
    sys.exit(reviewlib.main(sys.argv, HERE / "issues.json"))
