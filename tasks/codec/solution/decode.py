#!/usr/bin/env python3
"""Decode a binary frame into JSON. See SPEC.md for the layout."""

import json
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"MC"


def decode_varint(raw: bytes, pos: int):
    value = 0
    shift = 0
    count = 0
    while True:
        if pos >= len(raw):
            raise ValueError("truncated varint")
        if count >= 5:
            raise ValueError("varint too long")
        byte = raw[pos]
        pos += 1
        count += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def decode(in_path: Path, out_path: Path) -> None:
    raw = in_path.read_bytes()
    if raw[:2] != MAGIC:
        raise ValueError("bad magic")
    length, pos = decode_varint(raw, 2)
    if length > 2 ** 32 - 1:
        raise ValueError("length out of range")
    payload = raw[pos:pos + length]
    if len(payload) != length:
        raise ValueError("length mismatch")
    crc_pos = pos + length
    if len(raw) - crc_pos != 4:
        raise ValueError("bad crc field")
    crc_got = struct.unpack("<I", raw[crc_pos:crc_pos + 4])[0]
    if crc_got != zlib.crc32(payload):
        raise ValueError("crc mismatch")
    obj = json.loads(payload.decode("utf-8"))
    if not isinstance(obj, dict) or set(obj.keys()) != {"text"} \
            or not isinstance(obj.get("text"), str):
        raise ValueError("payload must be {\"text\": str}")
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
