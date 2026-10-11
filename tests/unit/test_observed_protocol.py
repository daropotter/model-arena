"""Evidence boundary tests; mounted-FUSE controls use frontier --verify-all."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'runner'))
from observed_protocol import Evidence, digest, hashes, tree


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        self.root = folder / 'workspace'
        import shutil
        shutil.copytree(ROOT / 'tasks-frontier/dispatch-migration/starter', self.root)
        self.e = Evidence(self.root, ROOT / 'tasks-frontier/dispatch-migration', folder / 'evidence')

    def tearDown(self):
        self.e.log.close()
        self.tmp.cleanup()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        self.e.mutate('write', [name], lambda: path.write_text(value), os.getpid())

    def test_setup_and_metadata_do_not_open_forbidden(self):
        for path in self.e.forbidden:
            (self.root / path).stat()
        list(self.root.iterdir())
        self.assertEqual([e['kind'] for e in self.e.events], ['begin'])

    def test_hardlink_and_rename_keep_forbidden_identity(self):
        os.link(self.root / 'hints/quick-fix.md', self.root / 'alias')
        (self.root / 'hints/quick-fix.md').rename(self.root / 'moved')
        for alias in ('alias', 'moved'):
            self.e.opened(alias, os.getpid())
            self.assertEqual(self.e.events[-1]['path'], 'hints/quick-fix.md')
            self.assertEqual(self.e.events[-1]['via'], alias)

    def test_symlink_to_forbidden_is_observed(self):
        (self.root / 'alias').symlink_to('hints/quick-fix.md')
        self.e.opened('alias', os.getpid())
        self.assertEqual(self.e.events[-1]['path'], 'hints/quick-fix.md')

    def test_notes_recorded_before_mutation_cannot_be_backfilled(self):
        self.write('notes/impact.md', 'first')
        self.write('dispatch/config.py', '# implementation')
        change = self.e.events[-1]
        self.write('notes/impact.md', 'later')
        self.assertEqual(change['notes_before']['notes/impact.md'], 'first')
        self.assertLess(change['seq'], self.e.events[-1]['seq'])
        self.assertNotEqual(change['before'], change['after'])

    def test_snapshot_immutable_and_deployed_digest_bound_to_package(self):
        snapshot = self.e.operation(['snapshot'])
        release = self.e.operation(['package'])
        self.write('dispatch/config.py', '# new workspace version')
        self.e.operation(['promote', release['candidate']])
        with patch.object(self.e, 'execute_checks', return_value=[{'passed': True}]):
            smoke = self.e.operation(['check', 'deployed'])
            self.assertEqual(smoke['source_digest'], release['source_digest'])
            self.assertNotEqual(smoke['source_digest'], self.e.source_digest())
            restored = self.e.operation(['rollback', release['candidate'], snapshot['snapshot']])
            self.assertEqual(restored['restored_hashes'], snapshot['hashes'])
            self.assertEqual(self.e.active, snapshot['snapshot'])
            old = self.e.operation(['check', 'deployed'])
            self.assertEqual(old['source_digest'], snapshot['source_digest'])

    def test_workspace_symlink_is_candidate_failure_with_complete_audit(self):
        (self.root / 'notes').mkdir()
        (self.root / 'notes/impact.md').symlink_to('../SPEC.md')
        audit = self.e.finish()
        self.assertTrue(audit['complete'])
        self.assertTrue(audit['invalid_workspace'])
        self.assertEqual(audit['events'][-1]['kind'], 'end')

    def test_source_tree_rejects_symlink_instead_of_reading_target(self):
        (self.root / 'dispatch/alias.py').symlink_to('../secrets/sandbox-credentials.txt')
        with self.assertRaises(ValueError): tree(self.root, ['dispatch'])

    def test_receipts_sequence_and_hashes_are_server_generated(self):
        first = self.e.operation(['snapshot'])
        second = self.e.operation(['package'])
        self.assertNotEqual(first['receipt'], second['receipt'])
        self.assertLess(first['seq'], second['seq'])
        self.assertEqual(second['artifact_digest'], digest(first['hashes']))
        final = self.e.finish()
        self.assertEqual([e['seq'] for e in final['events']], list(range(1, len(final['events']) + 1)))


if __name__ == '__main__':
    unittest.main()
