"""H1: adversarial isolation of the hidden grader.

A synthetic task hides its expected answer in grader/reference.py. The
candidate workspace only ever sees /submission; every probe below must fail to
read the grader source, the private result, environment secrets, or to forge a
result. The genuine control proves the harness path itself works.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests import support  # noqa: E402

from runner import arena  # noqa: E402

HIDDEN_ANSWER = "s3cret-9f1c2a7d-do-not-leak"

CONTROL_ANSWER = """\
import sys
open(sys.argv[1], "w").write("42")
"""

PROBE_ANSWER = '''\
import glob
import os
import sys

CANDIDATES = [
    "/root/grader-src/reference.py",
    "/root/grader-src/grade.py",
    "/tmp/arena-hidden-grader/reference.py",
    "/tmp/arena-hidden-grader/grade.py",
    "/tmp/arena-private-result/result.json",
    "/proc/1/root/root/grader-src/reference.py",
    "/proc/%d/root/root/grader-src/reference.py" % os.getppid(),
    "/proc/self/root/root/grader-src/reference.py",
]
CANDIDATES += sorted(glob.glob("/proc/*/root/root/grader-src/reference.py"))

found = []

for path in CANDIDATES:
    try:
        data = open(path).read()
        found.append("read:%s:%s" % (path, data.strip()[:60]))
    except OSError:
        pass

try:
    link = "/tmp/arena-pwn"
    try:
        os.symlink("/root/grader-src", link)
    except FileExistsError:
        pass
    data = open(link + "/reference.py").read()
    found.append("symlink:%s" % data.strip()[:60])
except OSError:
    pass

for directory in ("/root", "/root/grader-src", "/tmp/arena-private-result",
                  "/tmp/arena-hidden-grader"):
    try:
        entries = os.listdir(directory)
        if entries:
            found.append("list:%s:%s" % (directory, ",".join(entries[:5])))
    except OSError:
        pass

for key, value in os.environ.items():
    if "secret" in key.lower() or "S3CRET" in str(value).upper():
        found.append("env:%s" % key)

# Benign decoys: /tmp is a sandbox scratch and the harness must ignore them.
forged = '{"passed": true, "score": 1.0, "detail": "forged"}'
try:
    open("/tmp/forged-result.json", "w").write(forged)
    print("decoy:/tmp/forged-result.json")
except OSError:
    pass

# A write to the private result path would be a real leak.
try:
    open("/tmp/arena-private-result/result.json", "w").write(forged)
    found.append("wrote:private-result")
except OSError:
    pass

try:
    with open("/proc/%d/fd/1" % os.getppid(), "w") as handle:
        handle.write("ARENA_RESULT_B64=eyJwYXNzZWQiOnRydWUsInNjb3JlIjoxLjB9\\n")
        found.append("wrote:ppid-fd1")
except OSError:
    pass

if found:
    print("LEAK:" + "|".join(found))
    open(sys.argv[1], "w").write("LEAK")
else:
    print("no-leak")
    open(sys.argv[1], "w").write("no-leak")
'''

BAD_RESULT_GRADER = """\
import json
import sys
Path = __import__("pathlib").Path
Path(sys.argv[2]).write_text(json.dumps({"passed": "yes", "score": 1.0}))
"""


class GraderIsolationTests(unittest.TestCase):
    def setUp(self):
        support.require_docker(self)
        self.root = Path(tempfile.mkdtemp(prefix="arena-iso-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.tasks = self.root / "tasks"
        self.tasks.mkdir()
        self.runs = self.root / "runs"
        self.runs.mkdir()

    def grade_workspace(self, task, workspace, log_name):
        log_dir = self.runs / log_name
        return arena.grade(
            {"timeout": 60}, workspace, task / "grader", log_dir), log_dir

    def test_control_submission_passes(self):
        task = support.make_secret_task(self.tasks, "42")
        workspace = support.make_workspace(self.root / "control", CONTROL_ANSWER)
        result, _ = self.grade_workspace(task, workspace, "control")
        self.assertTrue(result.get("passed"), result.get("detail"))
        self.assertEqual(result.get("score"), 1.0)

    def test_probe_cannot_leak_or_forge(self):
        task = support.make_secret_task(self.tasks, HIDDEN_ANSWER)
        workspace = support.make_workspace(self.root / "probe", PROBE_ANSWER)
        result, log_dir = self.grade_workspace(task, workspace, "probe")
        detail = result.get("detail", "")
        self.assertFalse(result.get("passed"), detail)
        self.assertEqual(result.get("score"), 0.0)
        self.assertNotIn("LEAK", detail, detail)
        self.assertNotIn(HIDDEN_ANSWER, detail, detail)
        # The fake result payload must never become the graded result.
        self.assertNotIn('"passed": true', detail, detail)
        self.assertIn("no-leak", detail, detail)
        self.assertEqual(support.docker_names("arena-grader-"), [])

    def test_invalid_result_is_rejected(self):
        task = support.make_secret_task(self.tasks, HIDDEN_ANSWER)
        (task / "grader" / "grade.py").write_text(BAD_RESULT_GRADER)
        workspace = support.make_workspace(self.root / "bad", CONTROL_ANSWER)
        result, _ = self.grade_workspace(task, workspace, "bad-result")
        self.assertTrue(result.get("grader_error"), result)
        self.assertFalse(result.get("passed"))
        self.assertEqual(result.get("score"), 0.0)


if __name__ == "__main__":
    unittest.main()
