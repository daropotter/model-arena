"""tasklog command line interface. See SPEC.md."""

import json
import sys
from datetime import datetime, timezone

from .models import new_task, now_iso
from .store import Store, StoreError


def out(obj) -> None:
    print(json.dumps(obj))


def fail(message: str) -> int:
    out({"error": message})
    return 1


def parse_args(argv: list[str]):
    """Split argv into (store_path, command, rest)."""
    store_path = None
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == "--store":
            if i + 1 >= len(argv):
                raise ValueError("--store requires a path")
            store_path = argv[i + 1]
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    if store_path is None:
        raise ValueError("--store is required")
    if not rest:
        raise ValueError("missing command")
    return store_path, rest[0], rest[1:]


def cmd_add(store: Store, args: list[str]) -> dict:
    title = None
    tags: list[str] = []
    due = None
    priority = 3
    i = 0
    while i < len(args):
        if args[i] == "--tag":
            if i + 1 >= len(args):
                return {"error": "--tag requires a value"}
            tags.append(args[i + 1])
            i += 2
        elif args[i] == "--due":
            if i + 1 >= len(args):
                return {"error": "--due requires a value"}
            due = args[i + 1]
            i += 2
        elif args[i] == "--priority":
            if i + 1 >= len(args):
                return {"error": "--priority requires a value"}
            try:
                priority = int(args[i + 1])
            except ValueError:
                return {"error": "priority must be an integer 1..5"}
            i += 2
        elif title is None:
            title = args[i]
            i += 1
        else:
            return {"error": f"unexpected argument: {args[i]}"}

    if title is None:
        return {"error": "add requires a title"}
    if not 1 <= priority <= 5:
        return {"error": "priority must be an integer 1..5"}

    task = new_task(store.next_id(), title)
    seen = set()
    task["tags"] = [t for t in tags if not (t in seen or seen.add(t))]
    task["due"] = due
    task["priority"] = priority
    task["snoozes"] = 0
    store.tasks.append(task)
    store.save()
    return task


def cmd_list(store: Store, args: list[str]) -> list:
    status = None
    tag = None
    i = 0
    while i < len(args):
        if args[i] == "--status":
            if i + 1 >= len(args):
                return {"error": "--status requires a value"}
            status = args[i + 1]
            i += 2
        elif args[i] == "--tag":
            if i + 1 >= len(args):
                return {"error": "--tag requires a value"}
            tag = args[i + 1]
            i += 2
        elif args[i] == "--json":
            i += 1
        else:
            return {"error": f"unexpected argument: {args[i]}"}

    tasks = sorted(store.tasks, key=lambda t: t["id"])
    if status is not None:
        tasks = [t for t in tasks if t["status"] == status]
    if tag is not None:
        tasks = [t for t in tasks if tag in t["tags"]]
    return tasks


def cmd_done(store: Store, args: list[str]) -> dict:
    if len(args) != 1:
        return {"error": "done requires exactly one id"}
    try:
        task_id = int(args[0])
    except ValueError:
        return {"error": "id must be an integer"}
    task = store.find(task_id)
    if task is None:
        return {"error": f"no task with id {task_id}"}
    task["status"] = "done"
    task["updated_at"] = now_iso()
    store.save()
    return task


def cmd_show(store: Store, args: list[str]) -> dict:
    if len(args) != 1:
        return {"error": "show requires exactly one id"}
    try:
        task_id = int(args[0])
    except ValueError:
        return {"error": "id must be an integer"}
    task = store.find(task_id)
    if task is None:
        return {"error": f"no task with id {task_id}"}
    return task


def cmd_summary(store: Store, args: list[str]) -> dict:
    if args:
        return {"error": f"unexpected argument: {args[0]}"}
    today = datetime.now(timezone.utc).date().isoformat()
    tasks = store.tasks
    return {
        "total": len(tasks),
        "open": sum(1 for t in tasks if t["status"] == "open"),
        "done": sum(1 for t in tasks if t["status"] == "done"),
        "with_due": sum(1 for t in tasks if t.get("due")),
        "overdue": sum(
            1 for t in tasks
            if t["status"] == "open" and t.get("due") and t["due"] < today
        ),
    }


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "done": cmd_done,
    "show": cmd_show,
    "summary": cmd_summary,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        store_path, command, rest = parse_args(argv)
    except ValueError as exc:
        return fail(str(exc))

    handler = COMMANDS.get(command)
    if handler is None:
        return fail(f"unknown command: {command}")

    try:
        store = Store(store_path)
    except StoreError as exc:
        return fail(str(exc))

    result = handler(store, rest)
    if isinstance(result, dict) and "error" in result:
        return fail(result["error"])
    out(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
