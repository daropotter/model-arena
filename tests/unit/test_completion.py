"""Queue integrity, input drift, redaction and inter-process coordination."""

import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runner import complete_nonfree as completion
from runner import run_lock
from tests import support


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.record = support.base_record(Path('/unused'), model='ollama/test', task='codec')
        self.hashes = {'codec': {k: 'same' for k in (
            'task_digest', 'starter_digest', 'grader_digest', 'prompt_digest')}}
        self.record['provenance'] = {
            'suite_id': 'model-arena-v2', 'runner_digest': 'runner',
            'docker_digest': 'docker', **self.hashes['codec']}

    def test_valid_failure_is_complete_not_a_retry(self):
        self.record.update(passed=False, score=0.2, tool_calls=2)
        self.assertEqual(completion.build_plan([self.record], self.hashes)[0]['tasks'], [])

    def test_legacy_attempt_needs_v2_but_has_coverage(self):
        self.record.pop('schema_version')
        plan = completion.build_plan([self.record], self.hashes)[0]
        self.assertEqual(plan['tasks'], ['codec'])
        self.assertEqual(plan['missing_coverage'], [])

    def test_infrastructure_failure_needs_new_coverage(self):
        self.record.update(run_outcome='provider_error', valid_for_quality=False)
        plan = completion.build_plan([self.record], self.hashes)[0]
        self.assertEqual(plan['tasks'], ['codec'])
        self.assertEqual(plan['missing_coverage'], ['codec'])

    def test_filters_free_but_includes_big_pickle_and_ollama(self):
        plans = completion.build_plan([], self.hashes,
                                       ['opencode/big-pickle', 'ollama/test', 'openrouter/test:FREE'])
        self.assertEqual({p['model'] for p in plans}, {'opencode/big-pickle', 'ollama/test'})

    def test_prompt_drift_requires_run_not_regrade(self):
        self.record['provenance']['prompt_digest'] = 'old'
        self.assertEqual(completion.build_plan([self.record], self.hashes)[0]['tasks'], ['codec'])
        self.assertEqual(completion.grader_only([self.record], self.hashes), [])

    def test_grader_only_drift_can_reuse_saved_submission(self):
        self.record['provenance']['grader_digest'] = 'old'
        self.assertEqual(completion.grader_only([self.record], self.hashes), [('ollama/test', 'codec')])

    def test_split_secret_and_flush_do_not_leak(self):
        output = io.StringIO()
        writer = completion.RedactingWriter(output, ['secret-value'])
        writer.write('prefix secret-')
        writer.flush()
        self.assertEqual(output.getvalue(), '')
        writer.write('value suffix\n')
        writer.finish()
        self.assertEqual(output.getvalue(), 'prefix [REDACTED] suffix\n')

    def test_lock_is_shared_with_separate_processes_and_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = ('from pathlib import Path; from runner.run_lock import exclusive; '
                    'with_context = exclusive(Path(__import__("sys").argv[1]), blocking=False); '
                    'with_context.__enter__(); with_context.__exit__(None,None,None)')
            with patch.dict('os.environ', {}, clear=True):
                with run_lock.exclusive(root):
                    result = subprocess.run([sys.executable, '-c', code, str(root)],
                                            capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('BlockingIOError', result.stderr)
                result = subprocess.run([sys.executable, '-c', code, str(root)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_regrade_model_filter_does_not_touch_excluded_records(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory)
            for name, model in [('a', 'paid/model'), ('b', 'provider/model-free')]:
                support.write_record(results / name, model=model, task='codec',
                                     run_outcome='provider_error', valid_for_quality=False)
            before = (results / 'b/record.json').read_bytes()
            result = subprocess.run([
                sys.executable, str(support.ROOT / 'runner/regrade.py'), '--results', str(results),
                '--models', 'paid/model', '--dry-run'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('paid/model', result.stdout)
            self.assertNotIn('provider/model-free', result.stdout)
            self.assertEqual((results / 'b/record.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
