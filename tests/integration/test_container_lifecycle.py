"""H2 (integration): container lifecycle, limits, timeouts and cleanup.

Uses small synthetic graders so each scenario is bounded; asserts that the
named containers never survive and that resource limits are really applied.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests import support  # noqa: E402

from runner import arena  # noqa: E402

SLEEPING_GRADER = "import time\ntime.sleep(60)\n"

SLOW_VALID_GRADER = """\
import json
import sys
import time
time.sleep(6)
open(sys.argv[2], "w").write(json.dumps(
    {"passed": True, "score": 1.0, "detail": "slow but valid"}))
"""


def make_task(root: Path, grader_py: str, timeout: int) -> Path:
    task = root / "slowtask"
    (task / "grader").mkdir(parents=True)
    (task / "starter").mkdir()
    (task / "meta.json").write_text(json.dumps({
        "name": "slowtask", "title": "slow synthetic task",
        "timeout": timeout, "protected": [],
    }))
    (task / "prompt.md").write_text("do nothing\n")
    (task / "grader" / "grade.py").write_text(grader_py)
    return task


class ContainerLifecycleTests(unittest.TestCase):
    def setUp(self):
        support.require_docker(self)
        self.root = Path(tempfile.mkdtemp(prefix="arena-life-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.tasks = self.root / "tasks"
        self.tasks.mkdir()
        self.runs = self.root / "runs"
        self.runs.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        leftover = support.docker_names("arena-")
        for name in leftover:
            subprocess.run(["docker", "rm", "-f", name],
                           capture_output=True, timeout=60)

    def test_grader_timeout_is_classified_and_cleans_up(self):
        task = make_task(self.tasks, SLEEPING_GRADER, timeout=2)
        start = time.monotonic()
        result = arena.grade({"timeout": 2}, self.workspace,
                             task / "grader", self.runs / "timeout-case")
        elapsed = time.monotonic() - start
        self.assertTrue(result.get("grader_error"), result)
        self.assertEqual(result.get("score"), 0.0)
        self.assertIn("timeout", result.get("detail", "").lower())
        self.assertLess(elapsed, 30)
        self.assertEqual(support.docker_names("arena-grader-"), [])

    def test_grader_container_resource_limits(self):
        task = make_task(self.tasks, SLOW_VALID_GRADER, timeout=30)
        log_dir = self.runs / "limits-case"
        outcome = {}

        def run():
            outcome["result"] = arena.grade(
                {"timeout": 30}, self.workspace, task / "grader", log_dir)

        thread = threading.Thread(target=run)
        thread.start()
        name = "arena-grader-limits-case"
        inspect = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            proc = subprocess.run(
                ["docker", "inspect", "--format",
                 "{{.HostConfig.PidsLimit}} {{.HostConfig.Memory}} "
                 "{{.HostConfig.NetworkMode}} {{.HostConfig.ReadonlyRootfs}}",
                 name],
                capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                inspect = proc.stdout.strip()
                break
            time.sleep(0.2)
        thread.join(60)
        self.assertFalse(thread.is_alive())
        self.assertIsNotNone(inspect, "grader container never appeared")
        pids, memory, network, readonly = inspect.split()
        self.assertEqual(int(pids), 128)
        self.assertEqual(int(memory), 1024 * 1024 * 1024)
        self.assertEqual(network, "none")
        self.assertEqual(readonly, "true")
        self.assertTrue(outcome["result"].get("passed"),
                        outcome["result"].get("detail"))

    def test_agent_tmpfs_allows_exec(self):
        """Regression: entry.sh writes /tmp/run_opencode.sh and runs it.

        Docker tmpfs defaults to noexec, which silently broke every hosted
        run until the agent /tmp spec gained `exec`.
        """
        cmd = ["docker", "run", "--rm", "--user", "1000:1000", "--read-only"]
        for spec in arena.AGENT_TMPFS:
            cmd += ["--tmpfs", spec]
        cmd += [arena.IMAGE, "sh", "-c",
                "printf '#!/bin/sh\\necho OK\\n' > /tmp/w.sh; "
                "chmod +x /tmp/w.sh; /tmp/w.sh"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "OK")

    def test_agent_run_leaves_no_containers(self):
        scratch = self.root / "scratch"
        scratch.mkdir()
        log_dir = self.root / "agent-log"
        log_dir.mkdir()
        arena.ensure_network(arena.NETWORK)
        outcome = {}

        def run():
            outcome["result"] = arena.run_agent(
                "ollama/definitely-not-a-model", scratch, "say hi", 20, log_dir)

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(120)
        if thread.is_alive():
            for name in support.docker_names("arena-"):
                subprocess.run(["docker", "rm", "-f", name],
                               capture_output=True, timeout=60)
            self.fail("run_agent did not return within 120s")
        self.assertIn("result", outcome)
        rc, duration, termination = outcome["result"]
        self.assertLess(duration, 110)
        self.assertIn(termination, {"completed", "no_events_timeout",
                                    "idle_timeout", "hard_wall"})
        self.assertEqual(support.docker_names("arena-"), [])


if __name__ == "__main__":
    unittest.main()
