"""H2 (unit): deadline and termination classification.

supervise_agent is the product's watch loop with injectable backend actions and
clock, so every termination path is exercised deterministically with a real
child process but a controlled time source.
"""

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests import support  # noqa: E402

from runner import arena  # noqa: E402


class StepClock:
    """Deterministic clock: each call advances by `step` seconds."""

    def __init__(self, start=1000.0, step=30.0):
        self.t = start
        self.step = step

    def __call__(self):
        self.t += self.step
        return self.t


class SuperviseTests(unittest.TestCase):
    def setUp(self):
        self.children = []

    def tearDown(self):
        for proc in self.children:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def sleeper(self, seconds=30):
        proc = subprocess.Popen(
            [sys.executable, "-c",
             f"import time; time.sleep({seconds})"])
        self.children.append(proc)
        return proc

    def flags(self):
        return {"kill": 0, "stop": 0}

    def actions(self, proc, flags):
        def kill():
            flags["kill"] += 1
            proc.kill()
        def stop():
            flags["stop"] += 1
            proc.kill()
        return kill, stop

    def supervise(self, proc, events_path, start, timeout, idle_grace,
                  post_deadline, flags, step=30.0, poll_interval=0.01):
        kill, stop = self.actions(proc, flags)
        return arena.supervise_agent(
            proc, events_path, start, timeout, idle_grace, post_deadline,
            kill=kill, stop=stop, poll_interval=poll_interval,
            clock=StepClock(start, step))

    def test_hard_wall(self):
        events = Path(tempfile.mkdtemp(prefix="arena-ev-")) / "events.jsonl"
        proc = self.sleeper()
        flags = self.flags()
        rc, reason = self.supervise(proc, events, 1000.0, timeout=5,
                                    idle_grace=60, post_deadline=10,
                                    flags=flags)
        self.assertEqual(reason, "hard_wall")
        self.assertEqual(flags, {"kill": 1, "stop": 0})

    def test_no_events_timeout(self):
        # idle_grace (200s) is larger than the no-events threshold
        # (timeout + 120s), matching production defaults (900 vs 1920).
        events = Path(tempfile.mkdtemp(prefix="arena-ev-")) / "events.jsonl"
        proc = self.sleeper()
        flags = self.flags()
        rc, reason = self.supervise(proc, events, 1000.0, timeout=5,
                                    idle_grace=200, post_deadline=400,
                                    flags=flags)
        self.assertEqual(reason, "no_events_timeout")
        self.assertEqual(flags, {"kill": 1, "stop": 0})

    def test_idle_timeout_after_events(self):
        events = Path(tempfile.mkdtemp(prefix="arena-ev-")) / "events.jsonl"
        events.write_text("{}\n")
        proc = self.sleeper()
        flags = self.flags()
        rc, reason = self.supervise(proc, events, 1000.0, timeout=5,
                                    idle_grace=60, post_deadline=200,
                                    flags=flags)
        self.assertEqual(reason, "idle_timeout")
        self.assertEqual(flags, {"kill": 0, "stop": 1})

    def test_progress_before_deadline_completes_normally(self):
        events = Path(tempfile.mkdtemp(prefix="arena-ev-")) / "events.jsonl"
        proc = subprocess.Popen(
            [sys.executable, "-c",
             "import time, sys; time.sleep(0.05); "
             "open(sys.argv[1], 'w').write('{}\\n'); time.sleep(0.05)",
             str(events)])
        self.children.append(proc)
        flags = self.flags()
        rc, reason = arena.supervise_agent(
            proc, events, time.time(), timeout=30, idle_grace=60,
            post_deadline=300,
            kill=lambda: flags.__setitem__("kill", flags["kill"] + 1),
            stop=lambda: flags.__setitem__("stop", flags["stop"] + 1),
            poll_interval=0.01)
        self.assertEqual(reason, "completed")
        self.assertEqual(rc, 0)
        self.assertEqual(flags, {"kill": 0, "stop": 0})

    def test_completed_never_calls_backend(self):
        events = Path(tempfile.mkdtemp(prefix="arena-ev-")) / "events.jsonl"
        proc = self.sleeper(seconds=0.05)
        flags = self.flags()
        rc, reason = arena.supervise_agent(
            proc, events, time.time(), timeout=30, idle_grace=60,
            post_deadline=300,
            kill=lambda: flags.__setitem__("kill", flags["kill"] + 1),
            stop=lambda: flags.__setitem__("stop", flags["stop"] + 1),
            poll_interval=0.01)
        self.assertEqual(reason, "completed")
        self.assertEqual(flags, {"kill": 0, "stop": 0})


if __name__ == "__main__":
    unittest.main()
