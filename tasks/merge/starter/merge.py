#!/usr/bin/env python3
"""Three-way text merge. See SPEC.md.

BUGGY: diffs ours vs theirs directly (ignores base), so a one-sided change
still becomes a conflict, and conflicts are emitted line-by-line rather than
as contiguous blocks.
"""

import json
import sys
from pathlib import Path


def merge(base, ours, theirs):
    # BUG: ignore base entirely and diff ours vs theirs line-by-line.
    out = []
    n = max(len(ours), len(theirs))
    for i in range(n):
        o = ours[i] if i < len(ours) else None
        t = theirs[i] if i < len(theirs) else None
        if o == t:
            if o is not None:
                out.append(o)
        else:
            # BUG: one-sided change still treated as a conflict, and
            # conflicts are one line at a time (no block grouping).
            out.append("<<<<<<<")
            if o is not None:
                out.append(o)
            out.append("=======")
            if t is not None:
                out.append(t)
            out.append(">>>>>>>")
    return out


def main():
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(Path(sys.argv[1]).read_text())
        base = data["base"]
        ours = data["ours"]
        theirs = data["theirs"]
        if not all(isinstance(x, list) and
                   all(isinstance(s, str) for s in x)
                   for x in (base, ours, theirs)):
            raise ValueError("not lists of strings")
        result = merge(base, ours, theirs)
        Path(sys.argv[2]).write_text(json.dumps(result) + "\n")
    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
