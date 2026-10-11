"""Authoring consistency checks for the larger, independently versioned task."""
import collections
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / 'tasks-frontier/dispatch-minefield'


class MinefieldContractTests(unittest.TestCase):
    def test_all_obligations_have_a_visible_source_and_unique_id(self):
        document = json.loads((TASK / 'requirements.json').read_text())
        rows = document['requirements']
        self.assertEqual(len(rows), 192)
        self.assertEqual(len({r['id'] for r in rows}), 192)
        self.assertEqual(collections.Counter(r['category'] for r in rows), {
            'functional': 48, 'process': 60, 'artifacts': 34,
            'tools': 14, 'negative': 24, 'regression': 12})
        for row in rows:
            path = TASK / row['source']
            if not path.exists(): path = TASK / 'starter' / row['source']
            self.assertIn(' '.join(row['anchor'].split()), ' '.join(path.read_text().split()), row['id'])

    def test_all_forbidden_files_exist_and_are_disclosed(self):
        meta = json.loads((TASK / 'meta.json').read_text())
        prompt = (TASK / 'prompt.md').read_text()
        self.assertEqual(len(meta['forbidden']), 24)
        for name in meta['forbidden']:
            self.assertTrue((TASK / 'starter' / name).is_file(), name)
            self.assertIn(name, prompt)

    def test_cohort_ids_and_policies_are_valid_and_not_interchangeable(self):
        base = TASK / 'starter/fixtures/cohorts'
        owners = json.loads((base / 'owners.json').read_text())
        self.assertEqual(len(owners), 8)
        policies = set()
        for tenant in owners:
            config = json.loads((base / tenant / 'config.json').read_text())
            event = json.loads((base / tenant / 'event.json').read_text())
            policy = json.loads((base / tenant / 'policy.json').read_text())
            ids = {c['id'] for c in config['contacts']}
            self.assertEqual(config['tenant'], tenant)
            self.assertEqual(event['tenant'], tenant)
            self.assertEqual(policy.pop('tenant'), tenant)
            self.assertTrue(set(event['audience']) <= ids)
            self.assertTrue(set(policy['denied_ids']) <= ids)
            self.assertTrue(set(config['extensions']['consented_ids']) <= ids)
            policies.add(json.dumps(policy, sort_keys=True))
        self.assertEqual(len(policies), 8)

    def test_v1_remains_a_distinct_64_obligation_contract(self):
        old = ROOT / 'tasks-frontier/dispatch-migration'
        rows = json.loads((old / 'requirements.json').read_text())['requirements']
        self.assertEqual(len(rows), 64)
        self.assertEqual(json.loads((old / 'meta.json').read_text())['name'], 'dispatch-migration')
        self.assertNotEqual((old / 'prompt.md').read_bytes(), (TASK / 'prompt.md').read_bytes())


if __name__ == '__main__':
    unittest.main()
