#!/usr/bin/env python3
"""Reference implementation of README.md. Used only by the hidden grader."""

import json
import re
from datetime import date
from pathlib import Path

PATTERN = re.compile(r"report-(\d{8})\.txt$")


def valid_date(stamp: str) -> bool:
    try:
        date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        return True
    except ValueError:
        return False


def organize_reference(inbox: Path, manifest_path: Path) -> dict:
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

    result = {"moved": sorted(moved), "duplicates": sorted(duplicates)}
    manifest_path.write_text(json.dumps(result, indent=2) + "\n")
    return result
