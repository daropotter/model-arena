"""JSON store for cronlog. See SPEC.md, especially the concurrency contract."""

import json
import os
import tempfile
from pathlib import Path


class StoreError(Exception):
    pass


class Store:
    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.json"
        self.lock_path = self.dir / "events.lock"
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"events": []}
        with open(self.path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                raise StoreError(f"corrupted store: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise StoreError("corrupted store: missing events list")
        return data

    def save(self) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
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
    def events(self) -> list:
        return self.data["events"]

    def next_id(self) -> int:
        return max((e["id"] for e in self.events), default=0) + 1
