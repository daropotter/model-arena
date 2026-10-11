"""Benchmark contract invariants, independent provider and release graph."""
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
TASK=ROOT/'tasks-frontier/returns-distributed'
spec=importlib.util.spec_from_file_location('distributed_provider',TASK/'grader/provider.py')
provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)


class DistributedContractTests(unittest.TestCase):
    def test_graph_all_48_milestones_reach_delivery(self):
        rows=json.loads((TASK/'requirements.json').read_text())['stages'];ancestors={};depth={}
        self.assertEqual(len(rows),48)
        for r in rows:
            key=r['id'];deps=r['depends_on']
            self.assertNotIn(key,ancestors)
            self.assertTrue(set(deps)<=ancestors.keys())
            ancestors[key]=set(deps)
            for d in deps:ancestors[key]|=ancestors[d]
            depth[key]=1+max((depth[d] for d in deps),default=0)
        self.assertEqual(ancestors['S48'],{r['id'] for r in rows[:-1]})
        self.assertEqual(depth['S48'],33)
        visible=(TASK/'starter/STAGES.md').read_text()
        for row in rows:self.assertIn(row['id'],visible)

    def test_provider_replay_keeps_charge_across_protocol_cutover(self):
        p=provider.Provider({'protocol':1},serve=False)
        try:
            raw=json.dumps(dict(tenant='alpha',key='alpha/one',amount_cents=333,currency='PLN')).encode()
            p.mode='drop_once'
            code,_,drop,_=p.handle('/refunds',raw,{})
            self.assertEqual(code,200);self.assertTrue(drop);before=p.snapshot()
            p.contract={'protocol':2,'merchants':{'alpha':'a','beta':'b'},'signing_key':'test-fixture'}
            raw2=json.dumps({'merchant':'a','request_id':'alpha/one','money':{'value':'3.33','currency':'PLN'}}).encode()
            signature=hmac.new(b'test-fixture',raw2,hashlib.sha256).hexdigest()
            code,value,_,_=p.handle('/v2/refunds',raw2,{'X-Signature':signature})
            self.assertEqual(code,200);self.assertEqual(value['result']['id'],before[0]['receipt'])
            self.assertEqual(p.snapshot(),before)
            altered=raw2.replace(b'3.33',b'3.34')
            signature=hmac.new(b'test-fixture',altered,hashlib.sha256).hexdigest()
            self.assertEqual(p.handle('/v2/refunds',altered,{'X-Signature':signature})[0],409)
            self.assertEqual(p.snapshot(),before)
        finally:p.close()

    def test_invalid_signatures_and_declines_never_create_money(self):
        p=provider.Provider({'protocol':2,'merchants':{'alpha':'a'},'signing_key':'fixture'},serve=False)
        try:
            raw=json.dumps({'merchant':'a','request_id':'alpha/test','money':{'value':'0.10','currency':'EUR'}}).encode()
            self.assertEqual(p.handle('/v2/refunds',raw,{'X-Signature':'bad'})[0],400)
            sig=hmac.new(b'fixture',raw,hashlib.sha256).hexdigest();p.mode='decline'
            self.assertEqual(p.handle('/v2/refunds',raw,{'X-Signature':sig})[0],422)
            self.assertEqual(p.snapshot(),[])
        finally:p.close()


if __name__=='__main__':unittest.main()
