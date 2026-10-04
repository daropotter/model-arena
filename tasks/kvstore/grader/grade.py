#!/usr/bin/env python3
"""Hidden grader for kvstore.

Drives the submission through the contract's semantics, atomic batches,
WAL-only restarts, torn-tail recovery (every truncation byte position),
corrupted records and continuation. Corruption/truncation fixtures are
constructed here directly from bytes; the candidate is never asked to
produce corrupt input.
"""

import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import (encode_record, encode_raw, parse_wal,  # noqa: E402
                       MAX_PAYLOAD, MAGIC)

TIMEOUT = 10


def run(cli, store_dir, *args):
    """Run the candidate; never raises. Returns (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            [sys.executable, str(cli), str(store_dir), *[str(a) for a in args]],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, "", "timed out"
    except OSError as exc:
        return None, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def expect_ok(rc, out, err, want):
    if rc is None:
        return False, err or "no result"
    if rc != 0:
        return False, f"exit {rc}"
    try:
        got = json.loads(out)
    except ValueError:
        return False, "stdout is not JSON"
    if got != want:
        return False, f"got {gp(got)}"
    return True, ""


def expect_error(rc, out, err):
    if rc is None:
        return False, err or "no result"
    if rc != 1:
        return False, f"exit {rc}"
    if out.strip():
        return False, "stdout not empty"
    if err.strip() != "error":
        return False, "stderr is not 'error'"
    return True, ""


def gp(value, limit=120):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "..."


def call_ok(cli, store, *args, want):
    rc, out, err = run(cli, store, *args)
    return expect_ok(rc, out, err, want)


def call_error(cli, store, *args):
    rc, out, err = run(cli, store, *args)
    return expect_error(rc, out, err)


def write_wal(store, data):
    store.mkdir(parents=True, exist_ok=True)
    (store / "wal.log").write_bytes(data)


def read_wal(store):
    return (store / "wal.log").read_bytes()


def write_ops(tmp, name, payload):
    path = tmp / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def require_state(store, want, allow_tail=False):
    """Strictly parse the WAL on disk; the whole file must be records."""
    data = read_wal(store)
    try:
        state, end = parse_wal(data)
    except ValueError as exc:
        return False, f"wal unreadable: {exc}"
    if not allow_tail and end != len(data):
        return False, "wal has a partial tail"
    if state != want:
        return False, f"state {gp(state)}"
    return True, ""


# --- group 1: semantics -----------------------------------------------------

def case_sem_overwrite(cli, tmp):
    store = tmp / "store"
    for value in ("1", '"two"', "3.5", "true"):
        ok, detail = call_ok(cli, store, "put", "k", value,
                             want={"ok": True, "applied": 1})
        if not ok:
            return False, f"put {value}: {detail}"
    ok, detail = call_ok(cli, store, "get", "k",
                         want={"key": "k", "found": True, "value": True})
    if not ok:
        return False, f"get after overwrite: {detail}"
    return True, ""


def case_sem_delete(cli, tmp):
    store = tmp / "store"
    ok, detail = call_ok(cli, store, "put", "k", "5",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put: {detail}"
    ok, detail = call_ok(cli, store, "delete", "k",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"delete: {detail}"
    ok, detail = call_ok(cli, store, "get", "k",
                         want={"key": "k", "found": False})
    if not ok:
        return False, f"get after delete: {detail}"
    ok, detail = call_ok(cli, store, "delete", "k",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"delete of missing: {detail}"
    ok, detail = call_ok(cli, store, "get", "k",
                         want={"key": "k", "found": False})
    if not ok:
        return False, f"get after delete of missing: {detail}"
    return True, ""


def case_sem_unicode(cli, tmp):
    store = tmp / "store"
    key = "café☕/ключ✅"
    value = {"msg": "héllo → 世界", "emoji": "🚀", "n": [-0.5, "ß"]}
    ok, detail = call_ok(cli, store, "put", key, json.dumps(value),
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put: {detail}"
    ok, detail = call_ok(cli, store, "get", key,
                         want={"key": key, "found": True, "value": value})
    if not ok:
        return False, f"get: {detail}"
    ok, detail = call_ok(cli, store, "put", "ключ", '"значение"',
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put unicode value: {detail}"
    ok, detail = call_ok(cli, store, "get", "ключ",
                         want={"key": "ключ", "found": True, "value": "значение"})
    if not ok:
        return False, f"get unicode value: {detail}"
    return True, ""


def case_sem_null_vs_missing(cli, tmp):
    store = tmp / "store"
    ok, detail = call_ok(cli, store, "get", "absent",
                         want={"key": "absent", "found": False})
    if not ok:
        return False, f"get absent: {detail}"
    ok, detail = call_ok(cli, store, "put", "n", "null",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put null: {detail}"
    ok, detail = call_ok(cli, store, "get", "n",
                         want={"key": "n", "found": True, "value": None})
    if not ok:
        return False, f"get stored null: {detail}"
    ok, detail = call_ok(cli, store, "delete", "n",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"delete null: {detail}"
    ok, detail = call_ok(cli, store, "get", "n",
                         want={"key": "n", "found": False})
    if not ok:
        return False, f"get after deleting null: {detail}"
    return True, ""


def case_sem_falsey_and_nested(cli, tmp):
    store = tmp / "store"
    values = {"zero": "0", "empty": '""', "false": "false",
              "empty_list": "[]", "empty_obj": "{}"}
    for key, raw in values.items():
        ok, detail = call_ok(cli, store, "put", key, raw,
                             want={"ok": True, "applied": 1})
        if not ok:
            return False, f"put {key}: {detail}"
        want_value = json.loads(raw)
        ok, detail = call_ok(cli, store, "get", key,
                             want={"key": key, "found": True,
                                   "value": want_value})
        if not ok:
            return False, f"get {key}: {detail}"
    nested = {"a": [1, None, {"b": [True, "x", 2.5]}], "c": {"d": {}}}
    ok, detail = call_ok(cli, store, "put", "nested", json.dumps(nested),
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put nested: {detail}"
    ok, detail = call_ok(cli, store, "get", "nested",
                         want={"key": "nested", "found": True, "value": nested})
    if not ok:
        return False, f"get nested: {detail}"
    return True, ""


# --- group 2: batch atomicity ----------------------------------------------

def case_batch_valid_order(cli, tmp):
    store = tmp / "store"
    ops = [
        {"op": "put", "key": "a", "value": 1},
        {"op": "put", "key": "b", "value": {"n": [1, 2]}},
        {"op": "put", "key": "a", "value": 3},
        {"op": "delete", "key": "a"},
        {"op": "put", "key": "c", "value": "last"},
    ]
    path = write_ops(tmp, "good.json", ops)
    ok, detail = call_ok(cli, store, "batch", path,
                         want={"ok": True, "applied": 5})
    if not ok:
        return False, f"batch: {detail}"
    ok, detail = call_ok(cli, store, "get", "a",
                         want={"key": "a", "found": False})
    if not ok:
        return False, f"get a: {detail}"
    ok, detail = call_ok(cli, store, "get", "b",
                         want={"key": "b", "found": True,
                               "value": {"n": [1, 2]}})
    if not ok:
        return False, f"get b: {detail}"
    ok, detail = call_ok(cli, store, "get", "c",
                         want={"key": "c", "found": True, "value": "last"})
    if not ok:
        return False, f"get c: {detail}"
    return True, ""


def case_batch_atomic(cli, tmp):
    store = tmp / "store"
    ok, detail = call_ok(cli, store, "put", "x", "1",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"seed put: {detail}"
    before = read_wal(store)
    invalids = [
        [{"op": "put", "key": "y", "value": 2},
         {"op": "put", "key": "z"}],
        [{"op": "put", "key": "y", "value": 2},
         {"op": "bogus", "key": "z", "value": 3}],
        [{"op": "put", "key": "y", "value": 2},
         {"op": "delete"}],
        [{"op": "put", "key": "y", "value": 2},
         {"op": "put", "key": "", "value": 3}],
        [{"op": "put", "key": "y", "value": 2}, "nope"],
    ]
    for index, ops in enumerate(invalids):
        path = write_ops(tmp, f"bad{index}.json", ops)
        ok, detail = call_error(cli, store, "batch", path)
        if not ok:
            return False, f"invalid batch {index}: {detail}"
        if read_wal(store) != before:
            return False, f"invalid batch {index}: wal changed"
        ok, detail = call_ok(cli, store, "get", "y",
                             want={"key": "y", "found": False})
        if not ok:
            return False, f"invalid batch {index}: partial write: {detail}"
    ok, detail = call_ok(cli, store, "get", "x",
                         want={"key": "x", "found": True, "value": 1})
    if not ok:
        return False, f"original value lost: {detail}"
    return True, ""


# --- group 3: restart -------------------------------------------------------

def case_restart_same_store(cli, tmp):
    store = tmp / "store"
    ok, detail = call_ok(cli, store, "put", "a", "1",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put: {detail}"
    ok, detail = call_ok(cli, store, "get", "a",
                         want={"key": "a", "found": True, "value": 1})
    if not ok:
        return False, f"new process get: {detail}"
    return True, ""


def case_restart_wal_only(cli, tmp):
    store = tmp / "store"
    ok, detail = call_ok(cli, store, "put", "a", "1",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put a: {detail}"
    ok, detail = call_ok(cli, store, "put", "b", '"two"',
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put b: {detail}"
    ops = [{"op": "put", "key": "c", "value": 3},
           {"op": "delete", "key": "a"}]
    path = write_ops(tmp, "ops.json", ops)
    ok, detail = call_ok(cli, store, "batch", path,
                         want={"ok": True, "applied": 2})
    if not ok:
        return False, f"batch: {detail}"
    fresh = tmp / "fresh"
    fresh.mkdir()
    shutil.copy(store / "wal.log", fresh / "wal.log")
    ok, detail = call_ok(cli, fresh, "get", "a",
                         want={"key": "a", "found": False})
    if not ok:
        return False, f"get a from wal only: {detail}"
    ok, detail = call_ok(cli, fresh, "get", "b",
                         want={"key": "b", "found": True, "value": "two"})
    if not ok:
        return False, f"get b from wal only: {detail}"
    ok, detail = call_ok(cli, fresh, "get", "c",
                         want={"key": "c", "found": True, "value": 3})
    if not ok:
        return False, f"get c from wal only: {detail}"
    return True, ""


# --- group 4: torn-tail truncation -----------------------------------------

def case_partial_tail_sweep(cli, tmp):
    seed_a = encode_record([{"op": "put", "key": "a", "value": 1}])
    last = encode_record([{"op": "put", "key": "b", "value": 2}])
    base = seed_a + last
    positions = 0
    for removed in range(1, len(last)):
        positions += 1
        store = tmp / f"t{removed}"
        write_wal(store, base[:len(base) - removed])
        ok, detail = call_ok(cli, store, "get", "b",
                             want={"key": "b", "found": False})
        if not ok:
            return False, f"cut {removed}: recovery: {detail}"
        ok, detail = call_ok(cli, store, "put", "d", "4",
                             want={"ok": True, "applied": 1})
        if not ok:
            return False, f"cut {removed}: put after recovery: {detail}"
        ok, detail = require_state(store, {"a": 1, "d": 4})
        if not ok:
            return False, f"cut {removed}: after put: {detail}"
        ok, detail = call_ok(cli, store, "get", "d",
                             want={"key": "d", "found": True, "value": 4})
        if not ok:
            return False, f"cut {removed}: restart: {detail}"
        ok, detail = call_ok(cli, store, "get", "b",
                             want={"key": "b", "found": False})
        if not ok:
            return False, f"cut {removed}: discarded record resurrected: {detail}"
    if positions == 0:
        return False, "no truncation positions"
    return True, ""


# --- group 5: corruption ----------------------------------------------------

def case_corrupt_crc(cli, tmp):
    store = tmp / "store"
    record = bytearray(encode_record([{"op": "put", "key": "a", "value": 1}]))
    record[-1] ^= 0x01
    write_wal(store, bytes(record))
    ok, detail = call_error(cli, store, "get", "a")
    if not ok:
        return False, f"flipped crc: {detail}"
    return True, ""


def case_corrupt_json(cli, tmp):
    store = tmp / "store"
    write_wal(store, encode_raw(b'{"ops": [this is not json'))
    ok, detail = call_error(cli, store, "get", "a")
    if not ok:
        return False, f"bad json: {detail}"
    return True, ""


def case_corrupt_utf8(cli, tmp):
    store = tmp / "store"
    write_wal(store, encode_raw(b'{"ops": [\xff\xfe]}'))
    ok, detail = call_error(cli, store, "get", "a")
    if not ok:
        return False, f"bad utf-8: {detail}"
    return True, ""


def case_corrupt_oversized(cli, tmp):
    store = tmp / "store"
    data = bytes([MAGIC]) + struct.pack("<I", MAX_PAYLOAD + 1) + b"\x00" * 16
    write_wal(store, data)
    ok, detail = call_error(cli, store, "get", "a")
    if not ok:
        return False, f"oversized length: {detail}"
    return True, ""


def case_corrupt_magic(cli, tmp):
    store = tmp / "store"
    payload = b'{"ops": []}'
    data = (b"\x00" + struct.pack("<I", len(payload)) + payload
            + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))
    write_wal(store, data)
    ok, detail = call_error(cli, store, "get", "a")
    if not ok:
        return False, f"bad magic: {detail}"
    return True, ""


# --- group 6: continuation --------------------------------------------------

def case_continuation(cli, tmp):
    store = tmp / "store"
    write_wal(store, encode_record([{"op": "put", "key": "a", "value": 1}])
              + encode_record([{"op": "put", "key": "b", "value": 2}]))
    ok, detail = call_ok(cli, store, "put", "c", "3",
                         want={"ok": True, "applied": 1})
    if not ok:
        return False, f"put after recovery: {detail}"
    ok, detail = require_state(store, {"a": 1, "b": 2, "c": 3})
    if not ok:
        return False, f"wal after append: {detail}"
    ok, detail = call_ok(cli, store, "get", "c",
                         want={"key": "c", "found": True, "value": 3})
    if not ok:
        return False, f"restart get c: {detail}"
    return True, ""


def case_continuation_batch(cli, tmp):
    store = tmp / "store"
    write_wal(store, encode_record([
        {"op": "put", "key": "a", "value": 1},
        {"op": "delete", "key": "a"},
        {"op": "put", "key": "b", "value": {"x": 1}},
    ]))
    ops = [{"op": "delete", "key": "b"},
           {"op": "put", "key": "c", "value": 3}]
    path = write_ops(tmp, "ops.json", ops)
    ok, detail = call_ok(cli, store, "batch", path,
                         want={"ok": True, "applied": 2})
    if not ok:
        return False, f"batch after recovery: {detail}"
    ok, detail = require_state(store, {"c": 3})
    if not ok:
        return False, f"wal after batch: {detail}"
    ok, detail = call_ok(cli, store, "get", "c",
                         want={"key": "c", "found": True, "value": 3})
    if not ok:
        return False, f"restart get c: {detail}"
    return True, ""


# --- errors -----------------------------------------------------------------

def case_err_put_bad_json(cli, tmp):
    store = tmp / "store"
    ok, detail = call_error(cli, store, "put", "k", "{oops")
    if not ok:
        return False, f"malformed value: {detail}"
    return True, ""


def case_err_empty_key(cli, tmp):
    store = tmp / "store"
    for args in (("get", ""), ("put", "", "1"), ("delete", "")):
        ok, detail = call_error(cli, store, *args)
        if not ok:
            return False, f"{args[0]} empty key: {detail}"
    return True, ""


def case_err_usage(cli, tmp):
    store = tmp / "store"
    cases = [(), ("frobnicate", "k"), ("get",), ("get", "a", "b"),
             ("put", "k"), ("delete",), ("batch",)]
    for args in cases:
        ok, detail = call_error(cli, store, *args)
        if not ok:
            return False, f"usage {args}: {detail}"
    return True, ""


def case_err_batch_file(cli, tmp):
    store = tmp / "store"
    ok, detail = call_error(cli, store, "batch", tmp / "missing.json")
    if not ok:
        return False, f"missing file: {detail}"
    bad = tmp / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    ok, detail = call_error(cli, store, "batch", bad)
    if not ok:
        return False, f"not json: {detail}"
    not_array = tmp / "obj.json"
    not_array.write_text('{"op": "put", "key": "a", "value": 1}',
                         encoding="utf-8")
    ok, detail = call_error(cli, store, "batch", not_array)
    if not ok:
        return False, f"not an array: {detail}"
    return True, ""


def case_err_batch_ops(cli, tmp):
    store = tmp / "store"
    invalids = [
        [{"op": "put", "key": "k"}],
        [{"op": "delete"}],
        [{"op": "put", "key": "", "value": 1}],
        [{"op": "put", "key": 5, "value": 1}],
        [{"op": "nope", "key": "k", "value": 1}],
        ["x"],
        [1],
    ]
    for index, ops in enumerate(invalids):
        path = write_ops(tmp, f"bad{index}.json", ops)
        ok, detail = call_error(cli, store, "batch", path)
        if not ok:
            return False, f"invalid ops {index}: {detail}"
        if (store / "wal.log").exists():
            return False, f"invalid ops {index}: wrote a wal"
    return True, ""


CASES = [
    ("sem_overwrite", case_sem_overwrite),
    ("sem_delete", case_sem_delete),
    ("sem_unicode", case_sem_unicode),
    ("sem_null_vs_missing", case_sem_null_vs_missing),
    ("sem_falsey_and_nested", case_sem_falsey_and_nested),
    ("batch_valid_order", case_batch_valid_order),
    ("batch_atomic", case_batch_atomic),
    ("restart_same_store", case_restart_same_store),
    ("restart_wal_only", case_restart_wal_only),
    ("partial_tail_sweep", case_partial_tail_sweep),
    ("corrupt_crc", case_corrupt_crc),
    ("corrupt_json", case_corrupt_json),
    ("corrupt_utf8", case_corrupt_utf8),
    ("corrupt_oversized", case_corrupt_oversized),
    ("corrupt_magic", case_corrupt_magic),
    ("continuation", case_continuation),
    ("continuation_batch", case_continuation_batch),
    ("err_put_bad_json", case_err_put_bad_json),
    ("err_empty_key", case_err_empty_key),
    ("err_usage", case_err_usage),
    ("err_batch_file", case_err_batch_file),
    ("err_batch_ops", case_err_batch_ops),
]


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)
    cli = workspace / "kv.py"

    results = []
    earned = 0
    for name, case in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                ok, detail = case(cli, Path(tmp))
            except Exception as exc:  # grader must never crash on a bad submission
                ok, detail = False, f"case error: {type(exc).__name__}"
        if ok:
            earned += 1
        results.append({"case": name, "passed": ok,
                        "detail": "" if ok else str(detail)[:200]})

    total = len(CASES)
    score = earned / total if total else 0.0
    passed = earned == total
    detail = "all hidden cases passed" if passed else "; ".join(
        f"{r['case']}: {r['detail']}" for r in results if not r["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
