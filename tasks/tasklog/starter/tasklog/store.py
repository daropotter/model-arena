"""Persistent JSON store. See SPEC.md for the format and migration rules."""

import json
import os
import tempfile
from pathlib import Path


class StoreError(Exception):
    pass


class Store:
    def __init__(self, path: str):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"tasks": []}
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise StoreError(f"corrupted store: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
            raise StoreError("corrupted store: missing tasks list")
        return data

    def save(self) -> None:
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self.data, f, indent=2)
                f.write("\n")
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    @property
    def tasks(self) -> list:
        return self.data["tasks"]

    def find(self, task_id: int):
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None

    def next_id(self) -> int:
        return max((t["id"] for t in self.tasks), default=0) + 1
