#!/usr/bin/env python3
"""Reference implementation of SPEC.md. Used only by the hidden grader."""

import json
import struct
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


def encode_reference(in_path: Path, out_path: Path) -> None:
    obj = json.loads(in_path.read_text())
    if not isinstance(obj, dict) or set(obj.keys()) != {"text"} \
            or not isinstance(obj.get("text"), str):
        raise ValueError("input must be {\"text\": str}")
    payload = json.dumps(obj).encode("utf-8")
    length = encode_varint(len(payload))
    crc = zlib.crc32(payload)
    out_path.write_bytes(MAGIC + length + payload + struct.pack("<I", crc))


def decode_reference(in_path: Path, out_path: Path) -> None:
    raw = in_path.read_bytes()
    if raw[:2] != MAGIC:
        raise ValueError("bad magic")
    length, pos = decode_varint(raw, 2)
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
