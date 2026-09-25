"""cronlog CLI with the full concurrency contract (reference solution)."""

import json
import sys
from datetime import datetime, timezone

from .store import LockTimeout, Store, StoreError


def out(obj) -> None:
    print(json.dumps(obj))


def fail(message: str) -> int:
    out({"error": message})
    return 1


def parse_args(argv: list[str]):
    store_dir = None
    lock_timeout = 10.0
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == "--store":
            if i + 1 >= len(argv):
                raise ValueError("--store requires a directory")
            store_dir = argv[i + 1]
            i += 2
        elif argv[i] == "--lock-timeout":
            if i + 1 >= len(argv):
                raise ValueError("--lock-timeout requires a value")
            try:
                lock_timeout = float(argv[i + 1])
            except ValueError:
                raise ValueError("--lock-timeout must be a number")
            if lock_timeout < 0:
                raise ValueError("--lock-timeout must be >= 0")
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    if store_dir is None:
        raise ValueError("--store is required")
    if not rest:
        raise ValueError("missing command")
    return store_dir, lock_timeout, rest[0], rest[1:]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(fn):
    """Run fn(store) under the exclusive lock, re-reading the store first."""
    def wrapper(store: Store, args: list[str]):
        try:
            store._acquire(shared=False)
        except LockTimeout as exc:
            return {"error": str(exc)}
        try:
            store.reload()
            result = fn(store, args)
            if not (isinstance(result, dict) and "error" in result):
                store.save()
            return result
        finally:
            store.release()
    return wrapper


def _read(fn):
    def wrapper(store: Store, args: list[str]):
        try:
            store._acquire(shared=True)
        except LockTimeout as exc:
            return {"error": str(exc)}
        try:
            store.reload()
            return fn(store, args)
        finally:
            store.release()
    return wrapper


@_write
def cmd_add(store: Store, args: list[str]):
    if len(args) != 1:
        return {"error": "add requires exactly one name"}
    event = {"id": store.next_id(), "name": args[0], "ts": now_iso()}
    store.events.append(event)
    return event


@_read
def cmd_list(store: Store, args: list[str]):
    if args:
        return {"error": f"unexpected argument: {args[0]}"}
    return {"events": sorted(store.events, key=lambda e: e["id"])}


@_read
def cmd_stats(store: Store, args: list[str]):
    if args:
        return {"error": f"unexpected argument: {args[0]}"}
    by_name: dict[str, int] = {}
    for event in store.events:
        by_name[event["name"]] = by_name.get(event["name"], 0) + 1
    return {"total": len(store.events), "by_name": by_name}


@_write
def cmd_prune(store: Store, args: list[str]):
    before = None
    i = 0
    while i < len(args):
        if args[i] == "--before":
            if i + 1 >= len(args):
                return {"error": "--before requires a value"}
            before = args[i + 1]
            i += 2
        else:
            return {"error": f"unexpected argument: {args[i]}"}
    if before is None:
        return {"error": "prune requires --before"}
    try:
        datetime.strptime(before, "%Y-%m-%d")
    except ValueError:
        return {"error": "invalid --before date"}
    kept = [e for e in store.events if e["ts"][:10] >= before]
    removed = len(store.events) - len(kept)
    store.data["events"] = kept
    return {"removed": removed}


COMMANDS = {"add": cmd_add, "list": cmd_list, "stats": cmd_stats,
            "prune": cmd_prune}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        store_dir, lock_timeout, command, rest = parse_args(argv)
    except ValueError as exc:
        return fail(str(exc))

    handler = COMMANDS.get(command)
    if handler is None:
        return fail(f"unknown command: {command}")

    try:
        store = Store(store_dir, lock_timeout=lock_timeout)
        result = handler(store, rest)
    except StoreError as exc:
        return fail(str(exc))

    if isinstance(result, dict) and "error" in result:
        return fail(result["error"])
    out(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
