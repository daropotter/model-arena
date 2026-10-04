"""Serialize benchmark entry points sharing the same host and GPU."""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def exclusive(root: Path, name=".arena-execution.lock", blocking=True):
    directory = Path(os.environ.get("ARENA_LOCK_ROOT", root)) / "results"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / name).open("a") as handle:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(handle, flags)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
