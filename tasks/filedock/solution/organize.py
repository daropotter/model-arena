#!/usr/bin/env python3
"""Organize inbox report files and write a manifest. See README.md."""

import json
import re
import sys
from datetime import date
from pathlib import Path

PATTERN = re.compile(r"report-(\d{8})\.txt$")


def valid_date(stamp: str) -> bool:
    try:
        date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        return True
    except ValueError:
        return False


def organize(inbox: Path, manifest_path: Path) -> None:
    moved, duplicates = [], []

    files = sorted(p for p in inbox.iterdir() if p.is_file())
    seen: dict[bytes, Path] = {}
    for path in files:
        match = PATTERN.match(path.name)
        if not match or not valid_date(match.group(1)):
            continue
        content = path.read_bytes()
        if content in seen:
            duplicates.append(path.name)
            path.unlink()
        else:
            seen[content] = path

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
