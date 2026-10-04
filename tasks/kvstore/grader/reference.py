#!/usr/bin/env python3
"""Reference WAL codec and key-value semantics. Used only by the hidden grader.

Record format (see SPEC.md):

    byte 0x4B | uint32 LE payload length | payload (UTF-8 JSON) | uint32 LE crc32
"""

import json
import struct
import zlib

MAGIC = 0x4B
MAX_PAYLOAD = 1024 * 1024
HEADER = 5
TRAILER = 4


def canonical_ops(ops):
    clean = []
    for op in ops:
        if op["op"] == "put":
            clean.append({"op": "put", "key": op["key"], "value": op["value"]})
        else:
            clean.append({"op": "delete", "key": op["key"]})
    return clean


def encode_record(ops):
    payload = json.dumps({"ops": canonical_ops(ops)}, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    return (bytes([MAGIC]) + struct.pack("<I", len(payload)) + payload
            + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))


def encode_raw(payload):
    return (bytes([MAGIC]) + struct.pack("<I", len(payload)) + payload
            + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))


def validate_ops(ops):
    if not isinstance(ops, list):
        raise ValueError("ops is not a list")
    clean = []
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError("op is not an object")
        kind = op.get("op")
        key = op.get("key")
        if not isinstance(key, str) or key == "":
            raise ValueError("bad key")
        if kind == "put":
            if "value" not in op:
                raise ValueError("put without value")
            clean.append({"op": "put", "key": key, "value": op["value"]})
        elif kind == "delete":
            clean.append({"op": "delete", "key": key})
        else:
            raise ValueError("unknown op")
    return clean


def apply_ops(state, ops):
    for op in ops:
        if op["op"] == "put":
            state[op["key"]] = op["value"]
        else:
            state.pop(op["key"], None)


def parse_wal(data):
    """Parse WAL bytes strictly.

    Returns (state, valid_end). A trailing partial record is tolerated and
    reported via valid_end; a complete record that is malformed raises
    ValueError.
    """
    state = {}
    offset = 0
    size = len(data)
    while offset < size:
        if size - offset < HEADER:
            break
        if data[offset] != MAGIC:
            raise ValueError("bad magic")
        (length,) = struct.unpack_from("<I", data, offset + 1)
        if length > MAX_PAYLOAD:
            raise ValueError("oversized record")
        if size - offset < HEADER + length + TRAILER:
            break
        payload = data[offset + HEADER:offset + HEADER + length]
        (crc,) = struct.unpack_from("<I", data, offset + HEADER + length)
        if crc != zlib.crc32(payload) & 0xFFFFFFFF:
            raise ValueError("bad crc")
        try:
            record = json.loads(payload.decode("utf-8"))
            ops = validate_ops(record["ops"])
        except (UnicodeError, ValueError, KeyError, TypeError):
            raise ValueError("bad payload")
        apply_ops(state, ops)
        offset += HEADER + length + TRAILER
    return state, offset
