#!/usr/bin/env python3
"""Crash-safe JSON key-value store. See SPEC.md.

BUGGY:
  * a snapshot file is written first and treated as the source of truth, so
    when a snapshot exists the WAL is never replayed, and WAL replay alone
    drops the final record (it reserves the last byte for a possible torn
    write);
  * batch ops are validated and applied one at a time, so an invalid op
    leaves the earlier ops half-written;
  * WAL replay silently ignores every error;
  * appends go after a partial or corrupt tail instead of overwriting it;
  * a stored null is reported as a missing key.
"""

import json
import struct
import sys
import zlib
from pathlib import Path

MAGIC = 0x4B
MAX_PAYLOAD = 1024 * 1024
HEADER = 5
TRAILER = 4


def snapshot_path(store_dir: Path) -> Path:
    return store_dir / "snapshot.json"


def wal_path(store_dir: Path) -> Path:
    return store_dir / "wal.log"


def apply_op(state: dict, op: dict) -> None:
    if op["op"] == "put":
        state[op["key"]] = op["value"]
    else:
        state.pop(op["key"], None)


def load_state(store_dir: Path) -> dict:
    state = {}
    snap = snapshot_path(store_dir)
    if snap.exists():
        try:
            loaded = json.loads(snap.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = loaded
        except Exception:
            pass
        # BUG: the snapshot is assumed complete, so the WAL is ignored.
        return state
    wal = wal_path(store_dir)
    if wal.exists():
        try:
            data = wal.read_bytes()
            # BUG: reserve the final byte in case the last append was torn;
            # this drops the last complete record of the WAL.
            data = data[:-1]
            offset = 0
            while offset + HEADER <= len(data):
                if data[offset] != MAGIC:
                    break
                (length,) = struct.unpack_from("<I", data, offset + 1)
                if length > MAX_PAYLOAD \
                        or offset + HEADER + length + TRAILER > len(data):
                    break
                payload = data[offset + HEADER:offset + HEADER + length]
                # BUG: the crc32 trailer is never verified.
                record = json.loads(payload.decode("utf-8"))
                for op in record["ops"]:
                    apply_op(state, op)
                offset += HEADER + length + TRAILER
        except Exception:
            # BUG: partial tails and corruption are treated the same and
            # swallowed.
            pass
    return state


def write_snapshot(store_dir: Path, state: dict) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    tmp = store_dir / "snapshot.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(snapshot_path(store_dir))


def append_record(store_dir: Path, ops: list) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"ops": ops}, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    record = (bytes([MAGIC]) + struct.pack("<I", len(payload)) + payload
              + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))
    # BUG: append after whatever tail is already there; a partial or corrupt
    # tail is never truncated away.
    with open(wal_path(store_dir), "ab") as fh:
        fh.write(record)


def validate_key(key) -> str:
    if not isinstance(key, str) or key == "":
        raise ValueError("bad key")
    return key


def parse_value(text: str):
    return json.loads(text)


def persist(store_dir: Path, state: dict, ops: list) -> None:
    write_snapshot(store_dir, state)
    append_record(store_dir, ops)


def main(argv: list) -> None:
    if len(argv) < 2:
        print("error", file=sys.stderr)
        sys.exit(1)
    store_dir = Path(argv[0])
    command = argv[1]
    rest = argv[2:]
    try:
        if command == "get" and len(rest) == 1:
            key = validate_key(rest[0])
            state = load_state(store_dir)
            if key in state and state[key] is not None:
                result = {"key": key, "found": True, "value": state[key]}
            else:
                # BUG: a stored null is indistinguishable from a missing key.
                result = {"key": key, "found": False}
        elif command == "put" and len(rest) == 2:
            key = validate_key(rest[0])
            value = parse_value(rest[1])
            state = load_state(store_dir)
            state[key] = value
            # BUG: state is persisted to the snapshot (and acknowledged)
            # before the WAL record is appended.
            persist(store_dir, state, [{"op": "put", "key": key,
                                        "value": value}])
            result = {"ok": True, "applied": 1}
        elif command == "delete" and len(rest) == 1:
            key = validate_key(rest[0])
            state = load_state(store_dir)
            state.pop(key, None)
            persist(store_dir, state, [{"op": "delete", "key": key}])
            result = {"ok": True, "applied": 1}
        elif command == "batch" and len(rest) == 1:
            ops = json.loads(Path(rest[0]).read_text(encoding="utf-8"))
            if not isinstance(ops, list):
                raise ValueError("batch is not a list")
            state = load_state(store_dir)
            applied = 0
            for op in ops:
                # BUG: validate and apply op by op, persisting each one, so
                # an invalid later op leaves the earlier ops behind.
                if not isinstance(op, dict):
                    raise ValueError("op is not an object")
                key = validate_key(op.get("key"))
                if op.get("op") == "put":
                    if "value" not in op:
                        raise ValueError("put without value")
                    apply_op(state, {"op": "put", "key": key,
                                     "value": op["value"]})
                    persist(store_dir, state,
                            [{"op": "put", "key": key, "value": op["value"]}])
                elif op.get("op") == "delete":
                    apply_op(state, {"op": "delete", "key": key})
                    persist(store_dir, state,
                            [{"op": "delete", "key": key}])
                else:
                    raise ValueError("unknown op")
                applied += 1
            result = {"ok": True, "applied": applied}
        else:
            raise ValueError("bad command")
    except Exception:
        print("error", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
