# cronlog specification

This document is the authoritative contract. Where the implementation and this
document disagree, this document wins.

## Store

The store is a directory given by `--store DIR` (required on every command).
It contains:

- `events.json`: JSON object `{"events": [...]}`. Each event is
  `{"id": int, "name": str, "ts": "YYYY-MM-DDTHH:MM:SSZ"}`.
- `events.lock`: the lock file (see concurrency rules). It may exist at any
  time; it is never deleted.

An empty or missing `events.json` means no events. A store file that is not
valid JSON, or valid JSON without an `events` list, is a user error.

## Concurrency contract

cronlog is invoked concurrently by many processes sharing one store directory.
The following rules are mandatory and are what makes that safe:

1. **Writer exclusion.** Every command that modifies the store (`add`,
   `prune`) must hold an **exclusive `flock`** on `events.lock` for the whole
   read-modify-write cycle, from reading `events.json` until the new content
   has been written. It must not hold the lock at any other time.

2. **Reader lock.** Every command that reads the store (`list`, `stats`, and
   also the read phase of writers) must hold an **`flock`**, exclusive for
   writers and **shared** for pure readers (`list`, `stats`), on the same lock
   file. Two readers may proceed concurrently; a reader and a writer may not.

3. **Lock timeout.** A global `--lock-timeout SECONDS` option (float,
   `>= 0`, default `10`) may appear anywhere in the argument list. Waiting for
   the lock must give up after that many seconds and fail with
   `{"error": "..."}`, exit code 1, leaving the store untouched. The wait must
   be a retry loop, not an unbounded blocking call, so the timeout is
   honored. Acquiring the lock is never allowed to be skipped: if the lock is
   held by another process, the command waits (or times out), it never
   proceeds without the lock.

4. **Atomic replacement.** `events.json` is replaced by writing a temporary
   file in the same directory and `os.replace`-ing it. A concurrent reader
   must never observe truncated or partially written JSON.

5. **No lock leaking.** The lock is released on every exit path, including
   errors.

## CLI

All commands print a single JSON object to stdout and exit 0 on success; on
user error they print `{"error": "<message>"}` and exit 1.

```
cronlog --store DIR [--lock-timeout SECONDS] add NAME
cronlog --store DIR [--lock-timeout SECONDS] list
cronlog --store DIR [--lock-timeout SECONDS] stats
cronlog --store DIR [--lock-timeout SECONDS] prune --before YYYY-MM-DD
```

- `add NAME`: appends an event with the next id (`max + 1`, or 1 when empty)
  and current UTC time. Output: the new event object.
- `list`: prints `{"events": [...]}` sorted by `id` ascending.
- `stats`: prints `{"total": N, "by_name": {"name": count, ...}}`. `by_name`
  contains every name present, order-insensitive.
- `prune --before DATE`: removes events whose `ts` date is strictly before
  `DATE` (compare the first 10 characters of `ts` with `DATE`). Output:
  `{"removed": N}`. Invalid `DATE` is an error. `--before` is required.
