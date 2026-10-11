"""Authoring, evidence semantics, shortcut controls and lazy asset isolation."""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];TASK=ROOT/'tasks-frontier/dossier'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec)
    sys.modules[name]=value;spec.loader.exec_module(value);return value


sys.path.insert(0,str(TASK))
try:build=module('dossier_builder_test',TASK/'build_corpus.py')
finally:sys.path.pop(0)
grade=module('dossier_grade_test',TASK/'grader/grade.py')
baseline=module('dossier_baseline_test',TASK/'solution/baselines.py')
regrade=module('dossier_copy_test',ROOT/'runner/frontier_regrade_container.py')


class DossierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.path=Path(cls.tmp.name)
        cls.manifest=build.generate(cls.path,target=1,seed=315,minimum=4)
        cls.oracle=json.loads((cls.path/'oracle.json').read_text());cls.rows=[x['answer'] for x in cls.oracle['rows']]

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def evaluate(self,rows):return grade.evaluate(build.table(rows),self.oracle)

    def test_reviewed_semantic_pairs(self):
        # Independently reviewed outcomes: 0 = master, 1 = proposed term,
        # 2 = competing term, None = genuinely indeterminate.
        expected={
            'execution':(0,1),'authority':(0,1),'condition':(0,1),'sunset':(0,1),
            'scope':(0,1),'priority':(2,1),'conflict':(None,1),'missing-schedule':(None,1),
            'partial-assent':(0,1),'correction':(0,1),'novation':(1,1),'rescission':(0,1),
            'silence':(0,1),'receipt':(0,1),'trial':(0,1),'conjunction':(None,1),
            'incorporation':(2,1),'future':(0,1),'renewal':(0,1),'nested-exception':(0,1),
            'delegation':(0,1),'counteroffer':(0,1),'survival':(0,1),'translation':(2,1),
        }
        context=dict(terms=['retain for a year','erase after a quarter','retain until account closure'],exception='legal-hold',scope='Atlas production in EEA',other_scope='Beacon production in EEA',instrument='V-A',other_instrument='V-B',base_date='2024-02-01',start_date='2025-06-15',expiry_date='2026-03-01',successor='LE-NEW')
        self.assertEqual(set(expected),set(build.FAMILIES))
        for family,outcomes in expected.items():
            for polarity in (False,True):
                with self.subTest(family=family,polarity=polarity):
                    s=build.story(family,polarity,context)
                    self.assertEqual(s.value,outcomes[polarity])
                    self.assertEqual(s.state,'unresolved' if outcomes[polarity] is None else 'bound')
                    self.assertTrue(all(s.text))
                    if family=='novation':self.assertEqual(s.owner,'successor' if polarity else 'original')
                    if outcomes[polarity] is None:self.assertEqual((s.exception,s.since),('?','?'))
                    elif outcomes[polarity]==1:self.assertEqual(s.exception,'legal-hold')
                    else:self.assertEqual(s.exception,'none')

    def test_all_oracle_paragraphs_exist_and_every_document_serves_a_scored_scope(self):
        references=self.oracle['references'];used=set()
        files={p.name:p.read_text() for p in (self.path/'workspace/corpus').glob('*.md')}
        for item in self.oracle['rows']:
            used.update(item['allowed_evidence'])
            for group in item['evidence_groups']:
                for ref in group:
                    source=references[ref]
                    self.assertIn('['+ref+']',files[Path(source['path']).name])
        self.assertEqual({v['document'] for v in references.values()},{ref.split('#')[0] for ref in used})
        self.assertEqual(self.manifest['corpus_bytes'],sum(p.stat().st_size for p in (self.path/'workspace/corpus').glob('*.md')))

    def test_reference_and_alternate_evidence_have_full_score(self):
        result=self.evaluate(self.rows);self.assertTrue(result['passed']);self.assertEqual(result['score'],1.)
        rows=copy.deepcopy(self.rows)
        for row,item in zip(rows,self.oracle['rows']):
            row['Evidence']='; '.join(f'[{g[-1]}](../document-index.csv)' for g in item['evidence_groups'])
        self.assertTrue(self.evaluate(list(reversed(rows)))['passed'])

    def test_unknown_everywhere_and_stale_rules_lose_substantial_credit(self):
        unknown=copy.deepcopy(self.rows);stale=copy.deepcopy(self.rows)
        for row,item,old in zip(unknown,self.oracle['rows'],stale):
            row.update(State='unresolved',Rule='?',Exception='?',Since='?',Basis='scope-unknown')
            old.update(State='bound',Rule=item['initial_rule'],Exception='none',Since=item['initial_since'],Basis='baseline-controls')
        self.assertLess(self.evaluate(unknown)['score'],.35)
        self.assertGreater(self.evaluate(unknown)['metrics']['unnecessary_unknown_rate'],.5)
        self.assertFalse(self.evaluate(stale)['conditions']['C05'])

    def test_supported_general_basis_is_not_an_arbitrary_label_failure(self):
        rows=copy.deepcopy(self.rows)
        for row,item in zip(rows,self.oracle['rows']):
            if row['State']=='bound':row['Basis']='baseline-controls' if row['Rule']==item['initial_rule'] else 'executed-change'
        self.assertTrue(self.evaluate(rows)['passed'])
        wrong=copy.deepcopy(self.rows)
        for row,item in zip(wrong,self.oracle['rows']):
            if row['State']=='bound':row['Basis']='executed-change' if row['Rule']==item['initial_rule'] else 'baseline-controls'
        self.assertFalse(self.evaluate(wrong)['passed'])

    def test_identity_can_be_proven_by_master_or_executed_novation(self):
        rows=copy.deepcopy(self.rows)
        for row in rows:row['Evidence']='; '.join(row['Evidence'].split('; ')[1:])
        self.assertTrue(self.evaluate(rows)['passed'])
        for row in rows:row['Legal entity']='LE-000000000000'
        self.assertFalse(self.evaluate(rows)['passed'])

    def test_more_specific_truthful_basis_codes_are_accepted(self):
        rows=copy.deepcopy(self.rows)
        for row,item in zip(rows,self.oracle['rows']):
            if item['polarity'] and item['family']=='conflict':row['Basis']='specific-prevails'
            if item['polarity'] and item['family']=='missing-schedule':row['Basis']='incorporated-term'
        self.assertTrue(self.evaluate(rows)['passed'])

    def test_evidence_shotgun_and_fabrication_are_not_success(self):
        for field in ('invented','shotgun','unrelated','authority-omitted'):
            rows=copy.deepcopy(self.rows)
            for n,row in enumerate(rows):
                if field=='invented':row['Evidence']='D-000000000000#p2; D-111111111111#p2'
                elif field=='shotgun':row['Evidence']='; '.join(self.oracle['references'])
                elif field=='unrelated':row['Evidence']=self.rows[(n+1)%len(rows)]['Evidence']
                else:row['Evidence']='; '.join(row['Evidence'].split('; ')[:3])
            result=self.evaluate(rows)
            self.assertFalse(result['conditions']['C03'],field)
            self.assertLess(result['metrics']['evidence_accuracy'],1.,field)

    def test_duplicates_and_invented_scopes_do_not_increase_score(self):
        duplicate=self.evaluate(self.rows+[self.rows[0]])
        invented=self.evaluate(self.rows+[dict(self.rows[0],Matter='M-000000000000')])
        self.assertFalse(duplicate['conditions']['C01']);self.assertFalse(invented['conditions']['C01'])
        self.assertLess(duplicate['score'],1.);self.assertLess(invented['score'],1.)

    def test_public_only_shortcuts_fail_on_paired_semantics(self):
        for mode in ('keyword','latest','regex'):
            rows=baseline.solve(self.path/'workspace',mode);result=self.evaluate(rows)
            self.assertLess(result['metrics']['resolution_accuracy'],.15,mode)
            self.assertLess(result['score'],.50,mode)

    def test_cache_reuse_tampering_and_private_public_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);first,built=build.ensure_assets(root,target=1,seed=10,minimum=1)
            self.assertTrue(built);mtime=(root/'assets/manifest.json').stat().st_mtime_ns
            second,built=build.ensure_assets(root,target=1,seed=10,minimum=1)
            self.assertFalse(built);self.assertEqual(first,second);self.assertEqual((root/'assets/manifest.json').stat().st_mtime_ns,mtime)
            names={str(p.relative_to(root/'assets/workspace')) for p in (root/'assets/workspace').rglob('*') if p.is_file()}
            self.assertFalse(any('oracle' in p or 'solution' in p or 'authoring' in p for p in names))
            (root/'assets/workspace/questions.csv').write_text('changed')
            with self.assertRaisesRegex(ValueError,'cache changed'):build.ensure_assets(root,target=1,seed=10,minimum=1)

    def test_reproducible_generation_and_answer_does_not_follow_sorted_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            other=build.generate(tmp,target=1,seed=315,minimum=4)
            self.assertEqual(self.manifest,other)
        self.assertEqual(len({r['Matter'] for r in self.rows}),4)
        self.assertNotEqual([r['Matter'] for r in self.rows],sorted(r['Matter'] for r in self.rows))

    def test_composition_requires_lineage_and_rider_evidence(self):
        for layer in ('composed','rider'):
            subset=[x for x in self.oracle['rows'] if x[layer]]
            self.assertTrue(subset)
            for item in subset:
                # The old five/six-record chain cannot earn full evidence
                # credit after independent source/scope operators are added.
                row=copy.deepcopy(item['answer'])
                row['Evidence']='; '.join(g[0] for g in item['evidence_groups'][:-1])
                one=dict(self.oracle,rows=[item])
                result=grade.evaluate(build.table([row]),one)
                self.assertLess(result['metrics']['evidence_accuracy'],1.)
                self.assertFalse(result['passed'])

    def test_private_oracle_is_not_loaded_from_candidate_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'answer').mkdir()
            (root/'answer/obligations.md').symlink_to(self.path/'oracle.json')
            with self.assertRaisesRegex(ValueError,'symlink'):grade.safe_read(root,'answer/obligations.md')

    def test_grading_copy_excludes_large_indexes_and_rejects_symlink_ancestors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';(source/'answer').mkdir(parents=True)
            (source/'answer/obligations.md').write_text('table')
            (source/'index.json').write_text('large working index')
            regrade.copy_grade_input(source,root/'grade',TASK)
            self.assertEqual((root/'grade/answer/obligations.md').read_text(),'table')
            self.assertFalse((root/'grade/index.json').exists())
            linked=root/'linked';linked.mkdir();(linked/'answer').symlink_to(source/'answer',target_is_directory=True)
            regrade.copy_grade_input(linked,root/'grade-linked',TASK)
            self.assertFalse((root/'grade-linked/answer/obligations.md').exists())


if __name__=='__main__':unittest.main()
