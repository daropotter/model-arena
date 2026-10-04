# kvstore spec

This document is the authoritative contract. Where the implementation and
this document disagree, this document wins.

## CLI

```
python3 kv.py <store_dir> get <key>
python3 kv.py <store_dir> put <key> <json-value>
python3 kv.py <store_dir> delete <key>
python3 kv.py <store_dir> batch <ops.json>
```

`<store_dir>` is a directory. It may not exist yet; the first write creates
it. `put` and `delete` are single-op requests. A successful invocation prints
exactly one JSON object to stdout and exits 0:

- `get` -> `{"key": <key>, "found": true, "value": <decoded value>}` when the
  key is present, or `{"key": <key>, "found": false}` when it is not. A found
  key always has a `value` member (which may be JSON `null`); a missing key
  never does.
- `put`, `delete`, `batch` -> `{"ok": true, "applied": <integer>}` where
  `applied` is the number of operation objects written: 1 for `put` and
  `delete`, the batch length for `batch`. Deleting a missing key is a valid
  no-op op and is still counted.

A key is a non-empty string. A value is any JSON value, including `null`.
A missing key is distinct from a key whose stored value is `null`.

## Storage

All state lives in `<store_dir>/wal.log`: a single append-only file of
binary records, concatenated with no padding:

```
byte 0x4B ('K')
uint32 little-endian payload length L, 0 <= L <= 1048576 (1 MiB)
payload: exactly L bytes of UTF-8 JSON
uint32 little-endian crc32 (IEEE) of the payload bytes
```

The payload decodes to a JSON object `{"ops": [...]}` whose `ops` list holds
the same operation objects `batch` accepts, in order.

An absent `wal.log` is an empty store. No other file is required to recover
the state; the state is derived purely from `wal.log`.

## Recovery

Replay records in file order from the start. Each record's `ops` are applied
in order: `put` sets the key, `delete` removes it, and applying `delete` to a
missing key is a no-op.

A record is **complete** when at least `5 + L + 4` bytes remain at its start.
A file is scanned as follows:

- A **trailing incomplete record** (a suffix that cannot supply a full 5-byte
  header, or a full body + crc for a valid header) is a partial tail left by
  a crash. It is discarded: recovery returns the state produced by the
  complete records before it. The next write MUST overwrite the partial tail
  by appending at the offset where the last complete record ended, so that no
  later bytes can ever be read as a record.
- A **complete header** (5 or more bytes remain) whose first byte is not
  `0x4B` is corruption.
- A declared length `L > 1 MiB` is corruption, even if fewer than `L` bytes
  actually remain.
- A complete record whose crc32 does not match the payload, whose payload is
  not valid UTF-8, whose payload is not valid JSON, or whose payload does not
  decode to a valid ops list (see below) is corruption.

Corruption anywhere in `wal.log` is fatal for every invocation, including
`get`: print `error` to stderr and exit 1.

## Operations and validation

A `put` value argument and a `batch` file are parsed as JSON. Operations are
validated as:

- `{"op": "put", "key": <non-empty string>, "value": <any JSON value>}`. The
  `value` member must be present; `null` is a value, absence is an error.
- `{"op": "delete", "key": <non-empty string>}`.

Unknown `op` values, non-object ops, non-string/empty keys, and a missing
`value` member are invalid. Extra members are ignored. A `batch` file must be
a JSON array; a valid batch is appended as one record, and an empty array is
valid and writes a record with no ops.

**Batches are atomic.** The whole array is validated before anything is
written. If any op is invalid, the invocation prints `error` to stderr, exits
1, writes nothing, and leaves `wal.log` byte-for-byte unchanged. The same
holds for `put`/`delete` with invalid arguments or malformed JSON.

## Errors

On any error — unknown or missing command, wrong number of arguments, empty
or non-string key, malformed JSON, invalid op, unreadable batch file, corrupt
WAL — print exactly `error` on stderr, print nothing to stdout, and exit 1.

## Reference examples

`put k 1` then `get k` -> `{"key": "k", "found": true, "value": 1}`.

`get absent` -> `{"key": "absent", "found": false}`.

`put n null` then `get n` -> `{"key": "n", "found": true, "value": null}`.

`put u "héllo"`, `put u "世界"` then `get u` -> `{"key": "u", "found": true,
"value": "世界"}` (overwrite).

`delete x` -> `{"ok": true, "applied": 1}` even when `x` was never stored.

`batch [put a 1, put b 2, delete a]` -> `{"ok": true, "applied": 3}`; after it
`get a` is missing and `get b` is 2.
