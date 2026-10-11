"""Authoring invariants: no leaked navigation hints, unique intent, useful faults."""
import importlib.util,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];TASK=ROOT/'tasks-frontier/export-forensics'
spec=importlib.util.spec_from_file_location('export_behavior',TASK/'grader/behavior.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class ExportForensicsTests(unittest.TestCase):
    def render_profile(self,profile):
        script=(ROOT/'docker/agent_entry.sh').read_text()
        start=script.index('case "${ARENA_INSTRUCTION_PROFILE:-spec}" in')
        section=script[start:script.index('# Wrapper so the prompt',start)]
        with tempfile.TemporaryDirectory() as tmp:
            env=dict(os.environ,CONFIG_DIR=tmp)
            env.pop('ARENA_INSTRUCTION_PROFILE',None)
            if profile is not None:env['ARENA_INSTRUCTION_PROFILE']=profile
            run=subprocess.run(['sh'],input=section,text=True,capture_output=True,env=env)
            path=Path(tmp)/'AGENTS.md';return run.returncode,path.read_text() if path.exists() else ''
    def test_prompt_has_exactly_two_words_and_profile_is_neutral(self):
        self.assertEqual((TASK/'prompt.md').read_text().strip(),'Napraw eksport')
        self.assertFalse((TASK/'starter/SPEC.md').exists())
        code,body=self.render_profile('forensics');self.assertEqual(code,0)
        for clue in ('SPEC.md','support/','ticket','domain','instance','manifest','source','arena-ops'):
            self.assertNotIn(clue,body)
        self.assertIn('clarifying question',body)
    def test_ordinary_profile_still_requires_spec(self):
        code,body=self.render_profile(None);self.assertEqual(code,0);self.assertIn('Read SPEC.md completely',body)
        self.assertNotEqual(self.render_profile('unknown')[0],0)
    def test_intent_chain_has_one_current_ticket_and_exact_host(self):
        intent=b.intent();self.assertEqual(intent['ticket'],'INC-482');self.assertEqual(intent['instance'],'wk-a73')
        self.assertNotEqual(b.ROUTES['raporty.novara.test'],b.ROUTES['raporty-novara.test'])
        self.assertEqual(intent['entry'],'services/settlement-http/app.py')
        for path in intent['evidence_files']:self.assertTrue((TASK/'starter'/path).is_file())
    def test_genuinely_ambiguous_assignment_is_not_scored_as_agent_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'repo';shutil.copytree(TASK/'starter',root)
            queue=root/'support/queues/warsaw-evening.json';value=json.loads(queue.read_text());value['active_tickets']=['INC-482','INC-471'];queue.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'needs clarification'):b.intent(root)
    def test_every_fault_is_observable_on_contract_examples(self):
        payload=b.fixture('orders-edge.json')
        for mutant in b.MUTANTS:
            host='feed.novara.test' if mutant=='partner' else b.intent()['host']
            _,raw=b.expected(payload,b.CONFIGS[b.ROUTES[host]])
            self.assertNotEqual(raw,b.fault(raw,host,payload,mutant),mutant)
    def test_untriggered_fault_does_not_manufacture_a_failure(self):
        host=b.intent()['host'];payload={'columns':[{'key':'x','label':'X'}],'rows':[{'x':'nonempty'}]}
        _,raw=b.expected(payload,b.CONFIGS[b.ROUTES[host]])
        for mutant in ('position','zero','false','partner'):
            self.assertEqual(raw,b.fault(raw,host,payload,mutant))

if __name__=='__main__':unittest.main()
