#!/usr/bin/env python3
"""Encode a JSON object into a binary frame. See SPEC.md for the layout."""

import json
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"MC"


def encode(in_path: Path, out_path: Path) -> None:
    obj = json.loads(in_path.read_text())
    payload = json.dumps(obj).encode("utf-8")
    length = struct.pack("<B", len(payload))  # single byte — bug
    crc = zlib.crc32(MAGIC + length + payload)  # wrong bytes — bug
    out_path.write_bytes(MAGIC + length + payload + struct.pack("<I", crc))


def main() -> None:
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        encode(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
