# tasklog CLI specification

This document is the authoritative contract. Where the implementation and this
document disagree, this document wins.

## Model

A task has:

- `id`: integer, unique, assigned by `add` as `max(existing ids) + 1`
  (or `1` when the store is empty).
- `title`: string.
- `status`: `open` or `done`.
- `tags`: list of strings, no duplicates, order preserved.
- `due`: `YYYY-MM-DD` or `null`.
- `priority`: integer 1..5, default 3.
- `snoozes`: integer, default 0.
- `created_at`, `updated_at`: ISO 8601 UTC strings.

## Store format

The store is a JSON file whose path is given by `--store PATH` (there is no
default; every command requires it). Two formats exist:

### Version 1

```json
{
  "tasks": [
    {"id": 1, "title": "x", "status": "open", "tags": ["a"], "due": null}
  ]
}
```

Version 1 has no `version` key, no `priority`, `snoozes`, `created_at` or
`updated_at`.

### Version 2

```json
{
  "version": 2,
  "tasks": [
    {"id": 1, "title": "x", "status": "open", "tags": ["a"], "due": null,
     "priority": 3, "snoozes": 0,
     "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
  ]
}
```

### Migration

Any command may encounter a version 1 store. Before doing its work, the CLI
must migrate it **in place**:

- Set `version` to `2`.
- Add missing per-task fields with defaults: `priority` 3, `snoozes` 0.
- `created_at` and `updated_at` are set to the current UTC time (there is no
  historical value to recover).
- Unknown extra fields are preserved as-is.

After any command, the store on disk must be version 2. A version 2 store is
never touched by migration (existing timestamps and values are preserved
exactly).

## CLI contract

All commands print a single JSON object to stdout and exit 0 on success.
On any user error (unknown command, missing id, invalid argument, corrupted
store, bad date) print a single JSON object `{"error": "<message>"}` to stdout
and exit 1. Never write a traceback to stderr.

Commands (first positional argument):

```
tasklog --store PATH add TITLE [--tag TAG]... [--due DATE] [--priority N]
tasklog --store PATH list [--status open|done] [--tag TAG] [--json]
tasklog --store PATH done ID
tasklog --store PATH snooze ID
tasklog --store PATH show ID
tasklog --store PATH summary
```

- `--store PATH` may appear anywhere in the argument list (before or after the
  command), exactly once.
- `--tag` may be repeated; tags are deduplicated preserving order.

### add

Creates a task with `status` `open`, `snoozes` 0, and `created_at` /
`updated_at` set to now. `--priority` must be an integer 1..5; anything else
is an error. `--due` must be a valid `YYYY-MM-DD` date; anything else is an
error. Output: the created task object as JSON.

### list

Prints a JSON array of tasks by default, sorted by `id` ascending. `--status`
and `--tag` filter. `--json` is accepted but changes nothing (JSON is always
the output).

### done

Sets the task's `status` to `done` and `updated_at` to now. Output: the task
object. Already-done tasks are a no-op success.

### snooze

Increments the task's `snoozes` by 1 and sets `updated_at` to now. **If the
task has a `due` date, that date is pushed forward by the number of days equal
to the task's new `snoozes` value** (so the first snooze adds 1 day, the second
2 more, by the third the due date has moved 6 days from the original). Tasks
without a due date are unaffected apart from the counter. Output: the task
object.

### show

Prints the task object for the given id, or an error if it does not exist.

### summary

Prints:

```json
{
  "total": 0,
  "open": 0,
  "done": 0,
  "with_due": 0,
  "overdue": 0,
  "by_priority": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
}
```

- `total`: all tasks.
- `open` / `done`: by status.
- `with_due`: tasks that have a non-null `due`.
- `overdue`: **open** tasks whose `due` is strictly before today's UTC date.
- `by_priority`: counts for every priority key 1..5 (always all five keys,
  even when zero).

## Robustness

- A corrupted store (not valid JSON, or JSON without a `tasks` list) is a user
  error: `{"error": ...}`, exit 1.
- The store file must never be rewritten when an error occurs.
- Writes are atomic enough that a crash cannot leave a truncated JSON file:
  write to a temporary file in the same directory and `os.replace` it.
