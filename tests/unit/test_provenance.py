"""H3: suite comparability and task-file provenance matching."""

import copy
import unittest

from runner import reporting
from tests import support

REQUIRED_DIGESTS = ["task_digest", "starter_digest", "grader_digest",
                    "prompt_digest", "runner_digest", "docker_digest"]


class ProvenanceTests(support.TempDirTestCase, unittest.TestCase):
    def setUp(self):
        self.tmp = self.tmpdir()
        self.task_dir = support.make_secret_task(self.tmp / "tasks", "s3cret")
        self.record = support.base_record(self.tmp / "run", model="test/model",
                                          task="secret")
        self.record["provenance"] = support.provenance_for(self.task_dir)

    def test_full_provenance_is_comparable(self):
        self.assertTrue(reporting.is_comparable(self.record))

    def test_schema_version_required(self):
        missing = copy.deepcopy(self.record)
        missing.pop("schema_version")
        self.assertFalse(reporting.is_comparable(missing))

        legacy = copy.deepcopy(self.record)
        legacy["schema_version"] = 1
        self.assertFalse(reporting.is_comparable(legacy))

    def test_provenance_block_required(self):
        missing = copy.deepcopy(self.record)
        missing.pop("provenance")
        self.assertFalse(reporting.is_comparable(missing))

        wrong_type = copy.deepcopy(self.record)
        wrong_type["provenance"] = "not-a-dict"
        self.assertFalse(reporting.is_comparable(wrong_type))

    def test_suite_mismatch_not_comparable(self):
        record = copy.deepcopy(self.record)
        record["provenance"]["suite_id"] = "other-suite"
        self.assertFalse(reporting.is_comparable(record))

    def test_every_required_digest_key(self):
        for key in REQUIRED_DIGESTS:
            with self.subTest(key=key):
                record = copy.deepcopy(self.record)
                record["provenance"].pop(key)
                self.assertFalse(reporting.is_comparable(record))

    def test_provenance_matches_fresh_task(self):
        record = {"provenance": support.provenance_for(self.task_dir)}
        self.assertTrue(reporting.provenance_matches(record, self.task_dir))

    def test_provenance_mismatch_after_starter_edit(self):
        record = {"provenance": support.provenance_for(self.task_dir)}
        (self.task_dir / "starter" / "README.md").write_text(
            "edited starter\n")
        self.assertFalse(reporting.provenance_matches(record, self.task_dir))

    def test_wrong_suite_never_matches(self):
        record = {"provenance": support.provenance_for(
            self.task_dir, suite_id="other-suite")}
        self.assertFalse(reporting.provenance_matches(record, self.task_dir))


if __name__ == "__main__":
    unittest.main()
