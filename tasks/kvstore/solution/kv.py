#!/usr/bin/env python3
"""Crash-safe JSON key-value store. See SPEC.md for the contract."""

import json
import os
import struct
import sys
import zlib
from pathlib import Path

MAGIC = 0x4B
MAX_PAYLOAD = 1024 * 1024
HEADER = 5
TRAILER = 4


def wal_path(store_dir: Path) -> Path:
    return store_dir / "wal.log"


def validate_key(key) -> str:
    if not isinstance(key, str) or key == "":
        raise ValueError("bad key")
    return key


def validate_ops(ops) -> list:
    if not isinstance(ops, list):
        raise ValueError("ops is not a list")
    clean = []
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError("op is not an object")
        key = validate_key(op.get("key"))
        if op.get("op") == "put":
            if "value" not in op:
                raise ValueError("put without value")
            clean.append({"op": "put", "key": key, "value": op["value"]})
        elif op.get("op") == "delete":
            clean.append({"op": "delete", "key": key})
        else:
            raise ValueError("unknown op")
    return clean


def apply_ops(state: dict, ops: list) -> None:
    for op in ops:
        if op["op"] == "put":
            state[op["key"]] = op["value"]
        else:
            state.pop(op["key"], None)


def scan_wal(data: bytes):
    """Return (state, valid_end).

    A trailing partial record stops the scan and is reported by valid_end;
    any other malformed content raises ValueError.
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
        except ValueError:
            raise ValueError("bad payload")
        except (KeyError, TypeError, UnicodeError) as exc:
            raise ValueError(f"bad payload: {exc}") from exc
        apply_ops(state, ops)
        offset += HEADER + length + TRAILER
    return state, offset


def load_state(store_dir: Path) -> dict:
    path = wal_path(store_dir)
    if not path.exists():
        return {}
    state, _ = scan_wal(path.read_bytes())
    return state


def append_ops(store_dir: Path, ops: list) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    path = wal_path(store_dir)
    if path.exists():
        data = path.read_bytes()
        _, valid_end = scan_wal(data)
        if valid_end != len(data):
            path.write_bytes(data[:valid_end])
    payload = json.dumps({"ops": ops}, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("record too large")
    record = (bytes([MAGIC]) + struct.pack("<I", len(payload)) + payload
              + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))
    with open(path, "ab") as fh:
        fh.write(record)
        fh.flush()
        os.fsync(fh.fileno())


def main(argv: list) -> None:
    if len(argv) < 2:
        print("error", file=sys.stderr)
        sys.exit(1)
    store_dir = Path(argv[0])
    command = argv[1]
    rest = argv[2:]
    try:
        if command == "get":
            if len(rest) != 1:
                raise ValueError("usage")
            key = validate_key(rest[0])
            state = load_state(store_dir)
            if key in state:
                result = {"key": key, "found": True, "value": state[key]}
            else:
                result = {"key": key, "found": False}
        elif command == "put":
            if len(rest) != 2:
                raise ValueError("usage")
            key = validate_key(rest[0])
            value = json.loads(rest[1])
            state = load_state(store_dir)
            state[key] = value
            append_ops(store_dir, [{"op": "put", "key": key, "value": value}])
            result = {"ok": True, "applied": 1}
        elif command == "delete":
            if len(rest) != 1:
                raise ValueError("usage")
            key = validate_key(rest[0])
            state = load_state(store_dir)
            state.pop(key, None)
            append_ops(store_dir, [{"op": "delete", "key": key}])
            result = {"ok": True, "applied": 1}
        elif command == "batch":
            if len(rest) != 1:
                raise ValueError("usage")
            ops = validate_ops(json.loads(
                Path(rest[0]).read_text(encoding="utf-8")))
            append_ops(store_dir, ops)
            result = {"ok": True, "applied": len(ops)}
        else:
            raise ValueError("unknown command")
    except Exception:
        print("error", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
