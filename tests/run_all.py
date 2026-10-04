#!/usr/bin/env python3
"""Run the model-arena test suite (stdlib unittest, no pytest needed).

Usage:
  python3 tests/run_all.py             # everything
  python3 tests/run_all.py unit        # tests/unit only
  python3 tests/run_all.py integration oracles
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GROUPS = {"unit", "integration", "oracles"}


def main(argv):
    groups = [arg for arg in argv[1:] if arg in GROUPS] or sorted(GROUPS)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for group in groups:
        start = ROOT / "tests" / group
        if not start.exists():
            continue
        suite.addTests(loader.discover(
            str(start), pattern="test_*.py", top_level_dir=str(ROOT)))
    if suite.countTestCases() == 0:
        print("no tests found", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
