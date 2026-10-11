"""Linux host-side observation of forbidden file opens during an agent run.

This is an opt-in building block, not yet wired into arena.py. Start AFTER
workspace preparation/hashing and stop BEFORE grading/snapshotting. Keep the
observer and its result on the host, outside all agent mounts.

IN_OPEN means a successful open, not necessarily a read or delivery to the
model. Directory enumeration/stat and mere path mentions are not violations.
inotify has no caller PID, can coalesce events, and does not reliably observe
all mmap access. This observer therefore implements a NO-OPEN contract, not
a byte-read counter or process-attributed security audit.
"""

import ctypes
import errno
import os
import select
import stat
import struct
import threading
import time
from pathlib import Path


IN_OPEN = 0x00000020
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_UNMOUNT = 0x00002000
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
HEADER = struct.Struct("iIII")


class FileAccessObserver:
    """Watch fixed regular files and their identities, including alias opens.

Results are available only after stop(). An incomplete observation must never
be interpreted as proof that no file was opened. Parent/identity changes are
reported separately; the eventual runner must distinguish agent tampering
from infrastructure failure rather than silently awarding compliance points.
    """

    def __init__(self, files, max_events=4096):
        if not files or max_events < 1:
            raise ValueError("nonempty file mapping and positive event limit required")
        self.files = {str(label): Path(path).absolute() for label, path in files.items()}
        self.max_events = max_events
        self.events = []
        self.errors = []
        self.opened = set()
        self._watches = {}
        self._identities = {}
        self._fd = None
        self._thread = None
        self._stop = threading.Event()
        self._finished = False
        self._started_ns = None

    def _error(self, reason):
        if reason not in self.errors:
            self.errors.append(reason)

    def _record(self, kind, label):
        if len(self.events) >= self.max_events:
            self._error("observer_event_capacity_exceeded")
            return
        self.events.append({"kind": kind, "path": label,
                            "observed_at_ns": time.monotonic_ns()})

    def start(self):
        if self._fd is not None or self._finished:
            raise RuntimeError("observer instances are single-use")
        # No file contents are read during setup or identity checks.
        for label, path in self.files.items():
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"watched path must be a regular file: {label}")
            self._identities[label] = (info.st_dev, info.st_ino)
        libc = ctypes.CDLL(None, use_errno=True)
        init = libc.inotify_init1
        init.argtypes = [ctypes.c_int]
        init.restype = ctypes.c_int
        add = libc.inotify_add_watch
        add.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        add.restype = ctypes.c_int
        self._fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
        if self._fd < 0:
            self._fd = None
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        try:
            for label, path in self.files.items():
                for target, role, mask in (
                    (path, "file", IN_OPEN | IN_MOVE_SELF | IN_DELETE_SELF),
                    (path.parent, "parent", IN_MOVED_FROM | IN_MOVED_TO |
                     IN_CREATE | IN_DELETE | IN_MOVE_SELF | IN_DELETE_SELF),
                ):
                    wd = add(self._fd, os.fsencode(target), mask)
                    if wd < 0:
                        raise OSError(ctypes.get_errno(), f"cannot watch {label}")
                    self._watches.setdefault(wd, []).append((label, role, path.name))
            self._check_identities()
            if self.errors:
                raise RuntimeError("file identity changed during observer setup")
            self._started_ns = time.monotonic_ns()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return self
        except BaseException:
            os.close(self._fd)
            self._fd = None
            self._finished = True
            raise

    def _consume(self, data):
        offset = 0
        while offset < len(data):
            if len(data) - offset < HEADER.size:
                self._error("truncated_inotify_header")
                return
            wd, mask, _cookie, size = HEADER.unpack_from(data, offset)
            offset += HEADER.size
            if size > len(data) - offset:
                self._error("truncated_inotify_name")
                return
            name = os.fsdecode(data[offset:offset + size].split(b"\0", 1)[0])
            offset += size
            if mask & IN_Q_OVERFLOW:
                self._error("inotify_queue_overflow")
                continue
            for label, role, basename in self._watches.get(wd, []):
                if mask & (IN_UNMOUNT | IN_IGNORED | IN_MOVE_SELF | IN_DELETE_SELF):
                    self._error(f"watch_lost_or_moved:{label}")
                    self._record("identity_changed", label)
                if role == "file" and mask & IN_OPEN:
                    self.opened.add(label)
                    self._record("open", label)
                if role == "parent" and name == basename and mask & (
                        IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE | IN_DELETE):
                    self._error(f"watched_path_changed:{label}")
                    self._record("path_changed", label)

    def _drain(self):
        # Bound each drain so a flooding process cannot block stop forever.
        for _ in range(256):
            try:
                data = os.read(self._fd, 65536)
            except BlockingIOError:
                return True
            except OSError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise
            if not data:
                self._error("inotify_unexpected_eof")
                return True
            self._consume(data)
        return False

    def _run(self):
        try:
            while not self._stop.is_set():
                readable, _, _ = select.select([self._fd], [], [], 0.05)
                if readable:
                    self._drain()
        except Exception as exc:
            self._error(f"observer_thread_failed:{type(exc).__name__}")

    def _check_identities(self):
        for label, path in self.files.items():
            try:
                info = path.lstat()
                same = stat.S_ISREG(info.st_mode) and (
                    info.st_dev, info.st_ino) == self._identities[label]
            except OSError:
                same = False
            if not same:
                self._error(f"final_identity_mismatch:{label}")

    def stop(self):
        if self._finished:
            return self.result()
        if self._fd is None:
            raise RuntimeError("observer was not started")
        self._stop.set()
        self._thread.join()
        try:
            if not self._drain():
                self._error("events_still_arriving_at_stop")
            self._check_identities()
        except Exception as exc:
            self._error(f"observer_stop_failed:{type(exc).__name__}")
        finally:
            os.close(self._fd)
            self._fd = None
            self._finished = True
        return self.result()

    def result(self):
        if not self._finished:
            raise RuntimeError("stop observation before consuming its result")
        return {
            "schema_version": 1,
            "mechanism": "linux-inotify-open",
            "started_at_ns": self._started_ns,
            "complete": self._started_ns is not None and not self.errors,
            "opened_paths": sorted(self.opened),
            "errors": list(self.errors),
            "events": [dict(event) for event in self.events],
        }

    def __enter__(self):
        return self.start()

    def __exit__(self, *_args):
        self.stop()
