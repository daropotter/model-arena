#!/usr/bin/env python3
"""Decode a binary frame into JSON. See SPEC.md for the layout."""

import json
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"MC"


def decode(in_path: Path, out_path: Path) -> None:
    raw = in_path.read_bytes()
    if raw[:2] != MAGIC:
        raise ValueError("bad magic")
    length = raw[2]  # single byte — bug
    payload = raw[3:3 + length]
    crc_got = struct.unpack("<I", raw[3 + length:3 + length + 4])[0]
    if crc_got != zlib.crc32(MAGIC + bytes([length]) + payload):  # wrong bytes
        raise ValueError("crc mismatch")
    obj = json.loads(payload.decode("utf-8"))
    out_path.write_text(json.dumps(obj, indent=2) + "\n")


def main() -> None:
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        decode(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, json.JSONDecodeError, struct.error) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
