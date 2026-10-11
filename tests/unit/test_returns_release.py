"""Release measurement invariants independent of the reference implementation."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[2]
TASK=ROOT/'tasks-frontier/returns-release'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

behavior=load('returns_behavior',TASK/'grader/behavior.py')
previous=sys.modules.get('behavior');sys.modules['behavior']=behavior
try:grader=load('returns_grade',TASK/'grader/grade.py')
finally:
    if previous:sys.modules['behavior']=previous
    else:sys.modules.pop('behavior',None)
sys.path.insert(0,str(ROOT/'runner'))
from observed_protocol import OpsHandler


class ReturnsReleaseTests(unittest.TestCase):
    def test_failed_prerequisite_blocks_join_even_if_other_branch_passed(self):
        stages=[{'id':'a','depends_on':[]},{'id':'b','depends_on':[]},{'id':'c','depends_on':['a','b']},{'id':'d','depends_on':['c']}]
        result=grader.dependency_metrics(stages,{'a':True,'b':False,'c':True,'d':True})
        self.assertEqual(result['longest_valid_chain'],1)
        self.assertEqual(result['dependency_complete'],1)
        self.assertEqual(result['blocked'],['c','d'])
        self.assertEqual(result['max_chain'],3)

    def test_complete_graph_and_every_stage_matters_for_final_delivery(self):
        rows=json.loads((TASK/'requirements.json').read_text())['stages']
        self.assertEqual(len(rows),36)
        ancestors={}
        for row in rows:
            self.assertNotIn(row['id'],ancestors)
            self.assertTrue(set(row['depends_on'])<=ancestors.keys())
            ancestors[row['id']]=set(row['depends_on'])
            for d in row['depends_on']:ancestors[row['id']]|=ancestors[d]
        self.assertEqual(ancestors['S36'],{r['id'] for r in rows[:-1]})
        result=grader.dependency_metrics(rows,{r['id']:True for r in rows})
        self.assertEqual(result['dependency_complete'],36)
        self.assertEqual(result['chain_fraction'],1)

    def test_candidate_process_cannot_manufacture_operation_receipts(self):
        handler=OpsHandler.__new__(OpsHandler)
        handler.request=Mock()
        handler.request.getsockopt.return_value=struct.pack('3i',1234,1001,1001)
        handler.rfile=io.BytesIO(b'["build"]\n');handler.wfile=io.BytesIO()
        handler.server=Mock()
        handler.handle()
        result=json.loads(handler.wfile.getvalue())
        self.assertEqual(result['outcome'],'failed')
        handler.server.evidence.operation.assert_not_called()

    def test_agent_process_can_request_operations(self):
        handler=OpsHandler.__new__(OpsHandler)
        handler.request=Mock()
        handler.request.getsockopt.return_value=struct.pack('3i',1234,1000,1000)
        handler.rfile=io.BytesIO(b'["build"]\n');handler.wfile=io.BytesIO()
        handler.server=Mock()
        handler.server.evidence.operation.return_value={'outcome':'passed','receipt':'r1'}
        handler.handle()
        self.assertEqual(json.loads(handler.wfile.getvalue())['receipt'],'r1')
        handler.server.evidence.operation.assert_called_once_with(['build'])


if __name__=='__main__':unittest.main()
