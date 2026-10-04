"""Shared helpers for model-arena tests (stdlib unittest only).

The project has no pytest dependency; every test module is runnable with
`python3 tests/run_all.py` or `python3 -m unittest`.
"""

import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUNNER = ROOT / "runner"
DOCKER_TIMEOUT = 60


def docker_available() -> bool:
    try:
        proc = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def require_docker(testcase) -> None:
    if not docker_available():
        testcase.skipTest("docker is not available")


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def docker_names(prefix: str) -> list:
    proc = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name={prefix}",
         "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=DOCKER_TIMEOUT,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


SECRET_GRADER = '''\
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from reference import ANSWER


def main():
    workspace = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "answer"
        try:
            proc = subprocess.run(
                [sys.executable, str(workspace / "answer.py"), str(marker)],
                capture_output=True, text=True, timeout=15,
            )
            rc = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired:
            rc, stdout, stderr = None, "", "timed out"
        got = marker.read_text(errors="replace").strip() if marker.exists() else None
    ok = rc == 0 and got == ANSWER
    result = {
        "passed": ok,
        "score": 1.0 if ok else 0.0,
        "detail": (f"rc={rc} answer={got!r} "
                   f"stdout={stdout[-400:]!r} stderr={stderr[-600:]!r}"),
    }
    out_path.write_text(json.dumps(result))


main()
'''


def make_secret_task(root: Path, answer: str, timeout: int = 60) -> Path:
    """Build a synthetic task whose hidden grader compares to `answer`.

    The answer only exists in `grader/reference.py`, which candidate code must
    never be able to read. The grader reports the candidate's stdout/stderr in
    `detail`, so tests can detect both leaks and forged results.
    """
    task = Path(root) / "secret"
    (task / "grader").mkdir(parents=True)
    (task / "starter").mkdir()
    (task / "meta.json").write_text(json.dumps({
        "name": "secret", "title": "synthetic secret task",
        "timeout": timeout, "protected": [],
    }))
    (task / "prompt.md").write_text("Write the secret to the answer file.\n")
    (task / "starter" / "README.md").write_text("synthetic starter\n")
    (task / "grader" / "reference.py").write_text(
        f"ANSWER = {json.dumps(answer)}\n")
    (task / "grader" / "grade.py").write_text(SECRET_GRADER)
    return task


def make_workspace(root: Path, answer_py: str) -> Path:
    workspace = Path(root) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "answer.py").write_text(answer_py)
    return workspace


def base_record(run_dir: Path, **overrides) -> dict:
    record = {
        "schema_version": 2,
        "run_id": "test-run",
        "batch_id": "test-batch",
        "repeat_index": 0,
        "model": "test/model",
        "task": "secret",
        "task_title": "synthetic secret task",
        "passed": False,
        "score": 0.0,
        "detail": "",
        "duration_s": 1.0,
        "exit_code": 0,
        "timed_out": False,
        "tokens": {"input": 10, "output": 10, "reasoning": 0},
        "steps": 1,
        "tool_calls": 1,
        "tool_errors": 0,
        "tool_names": {"bash": 1},
        "api_errors": 0,
        "run_outcome": "completed",
        "termination_reason": "completed",
        "valid_for_quality": True,
        "tamper": {"touched_protected": [], "untracked_files": [],
                   "tracked_files_changed": [], "removed_files": []},
        "run_dir": str(run_dir),
        "workspace": str(run_dir / "submission"),
        "finished_at": "2026-09-01T00:00:00+00:00",
    }
    record.update(overrides)
    return record


def write_record(run_dir: Path, record: dict = None, **overrides) -> dict:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    data = record if record is not None else base_record(run_dir, **overrides)
    (run_dir / "record.json").write_text(json.dumps(data, indent=2))
    return data


def provenance_for(task_dir: Path, suite_id: str = "model-arena-v2") -> dict:
    """Build a matching provenance block for tests/unit fixtures."""
    from runner import arena
    task_dir = Path(task_dir)
    return {
        "suite_id": suite_id,
        "task_digest": arena.tree_digest(task_dir),
        "starter_digest": arena.tree_digest(task_dir / "starter"),
        "grader_digest": arena.tree_digest(task_dir / "grader"),
        "prompt_digest": arena.file_digest(task_dir / "prompt.md"),
        "runner_digest": "test-runner",
        "docker_digest": "test-docker",
        "image": "test-image",
        "image_digest": "test-image-digest",
        "git_revision": "test-git",
        "submission_digest": "test-submission",
    }


class TempDirTestCase:
    """Mixin: per-test temporary directory via addCleanup."""

    def tmpdir(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="arena-test-"))
        self.addCleanup(__import__("shutil").rmtree, directory, True)
        return directory
