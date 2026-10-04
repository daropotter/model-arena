"""Oracle tests for the filedock task.

The real oracle (reference.organize_reference) is tested directly, and the
grader is exercised through runner.verify_tasks.grade_locally: the shipped
solution must pass while a manifest-only cheat must fail.
"""

import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path

from tests.support import ROOT, TempDirTestCase

GRADER = ROOT / "tasks" / "filedock" / "grader"
if str(GRADER) not in sys.path:
    sys.path.insert(0, str(GRADER))

import grade as filedock_grade  # noqa: E402
import reference as filedock_reference  # noqa: E402


CHEAT_TEMPLATE = '''\
import hashlib
import json
import sys
from pathlib import Path

EXPECTED = __EXPECTED__


def main():
    inbox = Path(sys.argv[1])
    digest = hashlib.sha256()
    for path in sorted(inbox.iterdir(), key=lambda p: p.name):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\\x00")
            digest.update(path.read_bytes())
            digest.update(b"\\x00")
    manifest = EXPECTED.get(digest.hexdigest(),
                            {"moved": [], "duplicates": []})
    Path(sys.argv[2]).write_text(json.dumps(manifest))


main()
'''


def _fingerprint(inbox):
    digest = hashlib.sha256()
    for path in sorted(inbox.iterdir(), key=lambda p: p.name):
        if path.is_file():
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(path.read_bytes())
            digest.update(b"\x00")
    return digest.hexdigest()


class ReferenceOracleTests(TempDirTestCase, unittest.TestCase):
    def test_hand_built_inbox(self):
        base = self.tmpdir() / "base"
        inbox = base / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "report-20260115.txt").write_bytes(b"dup\n")
        (inbox / "report-20260116.txt").write_bytes(b"dup\n")
        (inbox / "notes.txt").write_bytes(b"ignored\n")
        (inbox / "report-20261301.txt").write_bytes(b"badmonth\n")
        (inbox / "report-20260230.txt").write_bytes(b"impossible\n")
        (inbox / "report-2026010.txt").write_bytes(b"badlen\n")
        (inbox / "report-20260115.csv").write_bytes(b"wrongext\n")
        (inbox / "report-20251231.txt").write_bytes(b"")

        manifest_path = base / "manifest.json"
        result = filedock_reference.organize_reference(inbox, manifest_path)

        self.assertEqual(result, {
            "moved": ["report-20251231.txt", "report-20260115.txt"],
            "duplicates": ["report-20260116.txt"],
        })
        self.assertEqual(json.loads(manifest_path.read_text()), result)
        self.assertEqual(
            (base / "reports" / "2025" / "12" /
             "report-20251231.txt").read_bytes(), b"")
        self.assertEqual(
            (base / "reports" / "2026" / "01" /
             "report-20260115.txt").read_bytes(), b"dup\n")
        self.assertFalse((base / "reports" / "2026" / "01" /
                          "report-20260116.txt").exists())
        self.assertEqual(sorted(p.name for p in inbox.iterdir()),
                         ["notes.txt", "report-2026010.txt",
                          "report-20260115.csv", "report-20260230.txt",
                          "report-20261301.txt"])

    def test_second_run_is_idempotent(self):
        base = self.tmpdir() / "base"
        inbox = base / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "report-20260115.txt").write_bytes(b"dup\n")
        (inbox / "report-20260116.txt").write_bytes(b"dup\n")
        manifest_path = base / "manifest.json"
        first = filedock_reference.organize_reference(inbox, manifest_path)
        second = filedock_reference.organize_reference(inbox, manifest_path)
        self.assertEqual(first, {"moved": ["report-20260115.txt"],
                                 "duplicates": ["report-20260116.txt"]})
        self.assertEqual(second, {"moved": [], "duplicates": []})


class GraderBehaviourTests(TempDirTestCase, unittest.TestCase):
    def _expected_by_fingerprint(self):
        entries = {}
        for seed in (7, 42):
            base = self.tmpdir() / f"oracle-seed{seed}"
            filedock_grade.build_inbox(base, seed)
            inbox = base / "inbox"
            fingerprint = _fingerprint(inbox)
            entries[fingerprint] = filedock_reference.organize_reference(
                inbox, base / "manifest.json")
        return entries

    def test_manifest_only_cheat_fails(self):
        from runner.verify_tasks import grade_locally
        entries = self._expected_by_fingerprint()
        workspace = self.tmpdir() / "cheat-workspace"
        workspace.mkdir()
        (workspace / "organize.py").write_text(
            CHEAT_TEMPLATE.replace("__EXPECTED__", repr(entries)))
        result = grade_locally(ROOT / "tasks" / "filedock", workspace)
        self.assertFalse(result["passed"], result)

    def test_shipped_solution_passes_grader(self):
        from runner.verify_tasks import grade_locally
        workspace = self.tmpdir() / "solution-workspace"
        shutil.copytree(ROOT / "tasks" / "filedock" / "solution", workspace,
                        ignore=shutil.ignore_patterns("__pycache__"))
        result = grade_locally(ROOT / "tasks" / "filedock", workspace)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
