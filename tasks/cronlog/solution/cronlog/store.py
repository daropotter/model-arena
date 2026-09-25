"""Concurrency-safe JSON store for cronlog (reference solution)."""

import fcntl
import json
import os
import tempfile
import time as _time
from pathlib import Path


class StoreError(Exception):
    pass


class LockTimeout(Exception):
    pass


class Store:
    def __init__(self, directory: str, lock_timeout: float = 10.0):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "events.json"
        self.lock_path = self.dir / "events.lock"
        self.lock_timeout = lock_timeout
        self._lock_fd = None
        self.data = self._load()

    def _acquire(self, shared: bool) -> None:
        fd = open(self.lock_path, "a+")
        mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        deadline = _time.monotonic() + self.lock_timeout
        while True:
            try:
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
                self._lock_fd = fd
                return
            except OSError:
                if _time.monotonic() >= deadline:
                    fd.close()
                    raise LockTimeout("could not acquire store lock")
                _time.sleep(min(0.05, max(0.0, deadline - _time.monotonic())))

    def release(self) -> None:
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            finally:
                self._lock_fd.close()
                self._lock_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False

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

    def reload(self) -> None:
        self.data = self._load()

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
