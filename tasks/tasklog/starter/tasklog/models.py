"""Task model helpers."""

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_task(task_id: int, title: str) -> dict:
    stamp = now_iso()
    return {
        "id": task_id,
        "title": title,
        "status": "open",
        "tags": [],
        "due": None,
        "created_at": stamp,
        "updated_at": stamp,
    }
