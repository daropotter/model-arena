"""Behavioral probes for the proposed no-open benchmark observer."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runner.file_access_observer import FileAccessObserver, HEADER, IN_Q_OVERFLOW


@unittest.skipUnless(sys.platform == "linux", "inotify requires Linux")
class FileAccessObserverTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="arena-observer-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.secret = self.root / "forbidden.txt"
        self.secret.write_text("FAKE BENCHMARK DATA ONLY\n")
        self.safe = self.root / "safe.txt"
        self.safe.write_text("normal input\n")

    def observer(self, **kwargs):
        return FileAccessObserver({"forbidden.txt": self.secret}, **kwargs)

    def test_mentions_listing_and_stat_do_not_count(self):
        with self.observer() as observer:
            list(self.root.iterdir())
            self.secret.stat()
            self.safe.write_text(str(self.secret))
        result = observer.result()
        self.assertTrue(result["complete"])
        self.assertEqual(result["opened_paths"], [])

    def test_shell_open_is_seen_without_path_in_parent_command(self):
        with self.observer() as observer:
            subprocess.run([sys.executable, "-c",
                            "import os; open(os.environ['PROBE_FILE']).read()"],
                           env={**os.environ, "PROBE_FILE": str(self.secret)},
                           check=True, capture_output=True)
        self.assertEqual(observer.result()["opened_paths"], ["forbidden.txt"])
        self.assertTrue(observer.result()["complete"])

    def test_open_without_read_counts_and_is_drained_on_stop(self):
        observer = self.observer().start()
        fd = os.open(self.secret, os.O_RDONLY)
        try:
            result = observer.stop()
        finally:
            os.close(fd)
        self.assertEqual(result["opened_paths"], ["forbidden.txt"])
        self.assertTrue(result["complete"])

    def test_reads_before_and_after_window_do_not_count(self):
        self.secret.read_text()
        with self.observer() as observer:
            self.safe.read_text()
        self.secret.read_text()
        self.assertEqual(observer.result()["opened_paths"], [])
        self.assertTrue(observer.result()["complete"])

    def test_symlink_and_hardlink_aliases_are_seen(self):
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                alias = self.root / kind
                if kind == "symlink":
                    alias.symlink_to(self.secret)
                else:
                    os.link(self.secret, alias)
                with self.observer() as observer:
                    alias.read_text()
                self.assertEqual(observer.result()["opened_paths"], ["forbidden.txt"])
                self.assertTrue(observer.result()["complete"])

    @unittest.skipUnless(shutil.which("rg"), "ripgrep is unavailable")
    def test_rg_exclusion_is_safe_but_broad_content_search_opens_file(self):
        for excluded in (True, False):
            with self.subTest(excluded=excluded):
                command = ["rg", "--no-ignore", "--files-with-matches", "BENCHMARK"]
                if excluded:
                    command += ["--glob", "!forbidden.txt"]
                with self.observer() as observer:
                    proc = subprocess.run(command + [str(self.root)], capture_output=True)
                self.assertIn(proc.returncode, (0, 1))
                self.assertTrue(observer.result()["complete"])
                self.assertEqual(observer.result()["opened_paths"],
                                 [] if excluded else ["forbidden.txt"])

    def test_atomic_replacement_cannot_produce_clean_observation(self):
        replacement = self.root / "replacement"
        replacement.write_text("replacement\n")
        with self.observer() as observer:
            os.replace(replacement, self.secret)
            self.secret.read_text()
        self.assertFalse(observer.result()["complete"])
        self.assertTrue(observer.result()["errors"])

    def test_multiple_files_in_shared_and_separate_directories(self):
        other_dir = self.root / "nested"
        other_dir.mkdir()
        other = other_dir / "other.txt"
        other.write_text("another synthetic input\n")
        files = {"one": self.secret, "two": self.safe, "three": other}
        with FileAccessObserver(files) as observer:
            self.secret.read_text()
            other.read_text()
            (self.root / "unrelated.txt").write_text("allowed\n")
        self.assertTrue(observer.result()["complete"])
        self.assertEqual(observer.result()["opened_paths"], ["one", "three"])

    def test_parent_directory_move_cannot_produce_clean_observation(self):
        parent = self.root / "watched-parent"
        parent.mkdir()
        watched = parent / "watched.txt"
        watched.write_text("synthetic input\n")
        with FileAccessObserver({"watched": watched}) as observer:
            parent.rename(self.root / "moved-parent")
        self.assertFalse(observer.result()["complete"])

    def test_rename_and_restore_is_detected_even_if_final_inode_matches(self):
        temporary = self.root / "moved"
        with self.observer() as observer:
            self.secret.rename(temporary)
            temporary.rename(self.secret)
        self.assertFalse(observer.result()["complete"])

    def test_missing_path_and_symlink_are_rejected_at_setup(self):
        with self.assertRaises(FileNotFoundError):
            FileAccessObserver({"missing": self.root / "missing"}).start()
        alias = self.root / "alias"
        alias.symlink_to(self.secret)
        with self.assertRaises(ValueError):
            FileAccessObserver({"alias": alias}).start()

    def test_queue_overflow_and_capacity_never_award_clean_result(self):
        # Force overflow records: reproducing a kernel queue overflow reliably
        # would depend on the host's sysctl and scheduler.
        with self.observer() as observer:
            pass
        observer._consume(HEADER.pack(-1, IN_Q_OVERFLOW, 0, 0))
        self.assertFalse(observer.result()["complete"])
        self.assertIn("inotify_queue_overflow", observer.result()["errors"])
        with self.observer(max_events=1) as limited:
            pass
        limited._record("open", "forbidden.txt")
        limited._record("open", "forbidden.txt")
        self.assertFalse(limited.result()["complete"])

    def test_results_contain_no_file_contents_and_are_serializable(self):
        with self.observer() as observer:
            self.secret.read_text()
        raw = json.dumps(observer.result())
        self.assertNotIn("FAKE BENCHMARK DATA", raw)
        self.assertEqual(observer.stop(), observer.result())


if __name__ == "__main__":
    unittest.main()
