#!/usr/bin/env python3
"""Encode a JSON object into a binary frame. See SPEC.md for the layout."""

import json
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"MC"


def encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def encode(in_path: Path, out_path: Path) -> None:
    obj = json.loads(in_path.read_text())
    if not isinstance(obj, dict) or set(obj.keys()) != {"text"} \
            or not isinstance(obj.get("text"), str):
        raise ValueError("input must be {\"text\": str}")
    payload = json.dumps(obj).encode("utf-8")
    if len(payload) > 2 ** 32 - 1:
        raise ValueError("payload too large")
    length = encode_varint(len(payload))
    crc = zlib.crc32(payload)
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
