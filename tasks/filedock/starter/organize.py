#!/usr/bin/env python3
"""Organize inbox report files and write a manifest. See README.md."""

import json
import re
import sys
from pathlib import Path

PATTERN = re.compile(r"report-(\d{8})\.txt$")


def organize(inbox: Path, manifest_path: Path) -> None:
    moved, duplicates = [], []

    files = sorted(p for p in inbox.iterdir() if p.is_file())
    seen: dict[tuple, Path] = {}
    for path in files:
        match = PATTERN.match(path.name)
        if not match:
            continue
        stamp = match.group(1)
        # (the date validity check is missing — a bug)
        content = path.read_bytes()
        key = (content, stamp)  # duplicates only within the same date — a bug
        if key in seen:
            duplicates.append(path.name)
            path.unlink()
        else:
            seen[key] = path

    for path in seen.values():
        stamp = PATTERN.match(path.name).group(1)
        dest = inbox.parent / "reports" / stamp[:4] / stamp[4:6] / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        path.rename(dest)
        moved.append(path.name)

    manifest_path.write_text(json.dumps(
        {"moved": sorted(moved), "duplicates": sorted(duplicates)},
        indent=2) + "\n")


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: organize.py <inbox_dir> <manifest_path>",
              file=sys.stderr)
        sys.exit(1)
    organize(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
