#!/usr/bin/env python3
"""Run a grader while keeping its source and result hidden from submissions."""

import base64
import json
import os
import shutil
import signal
import sys
import time
from pathlib import Path


def private_copy(source: Path, target: Path) -> None:
    shutil.copytree(source, target)
    shutil.copy2("/grader_sitecustomize.py", target / "sitecustomize.py")
    for path in [target, *target.rglob("*")]:
        path.chmod(0o700 if path.is_dir() else 0o600)


def wait_with_timeout(pid: int, timeout: float, grace: float = 5.0):
    """Wait for pid; kill it after timeout. Returns (exit_code, timed_out)."""
    deadline = time.monotonic() + timeout
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            return os.waitstatus_to_exitcode(status), False
        if time.monotonic() > deadline:
            break
        time.sleep(0.05)
    os.kill(pid, signal.SIGKILL)
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    return None, True


def main() -> int:
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    hidden = Path("/tmp/arena-hidden-grader")
    private_out = Path("/tmp/arena-private-result")
    private_copy(Path("/root/grader-src"), hidden)
    private_out.mkdir(mode=0o700)
    result_path = private_out / "result.json"

    pid = os.fork()
    if pid == 0:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(hidden)
        os.execve(
            sys.executable,
            [sys.executable, str(hidden / "grade.py"), "/submission", str(result_path)],
            env,
        )

    exit_code, timed_out = wait_with_timeout(pid, timeout)
    if timed_out:
        print("ARENA_GRADER_ERROR=timeout: grader exceeded its time limit")
        return 1
    try:
        raw = result_path.read_bytes()
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("result is not an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ARENA_GRADER_ERROR={type(exc).__name__}: {exc}")
        return exit_code or 1

    print("ARENA_RESULT_B64=" + base64.b64encode(raw).decode("ascii"))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
