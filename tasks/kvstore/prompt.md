You are working in /workspace.

`kv.py` is a crash-safe JSON key-value store backed by an append-only WAL.
It has bugs: it writes a snapshot file as its source of truth and appends the
WAL only after acknowledging the caller, so replaying the WAL alone loses the
last operation; it validates and applies batch operations one at a time, so
an invalid op leaves the earlier ops half-written; on recovery it silently
ignores every WAL error instead of telling a torn trailing record apart from
real corruption; it appends new records after a corrupt or partial tail
instead of overwriting the tail; and it reports a stored null as a missing
key.

Read SPEC.md — it defines the exact record format, batch atomicity, recovery
and error contract.

The visible tests cover a put/get round trip, delete, a batch happy path, and
a second process reading values. Hidden tests exercise WAL-only recovery,
restarts, batch atomicity, every truncation position of a torn trailing
record, and corrupted WAL records.

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix:

    python3 kv.py ./store put k '{"n": 1}'
    python3 kv.py ./store get k
    python3 tests/test_visible.py
