"""Trusted two-phase runtime, with independent retained payment ledger."""
import base64
import json
import sqlite3
import subprocess
import behavior as b
from observed_protocol import Evidence as BaseEvidence,hashes,digest,sha

SOURCE=['src','client','config','build.py']


class Evidence(BaseEvidence):
    def __init__(self,*args):
        super().__init__(*args)
        self.products={};self.backups={};self.deployment=None
        self.review=None;self.prepared=None;self.drained=None

    def source_hashes(self):return hashes(self.safe_tree(SOURCE))
    def binding(self):
        product=self.products.get(self.active,{})
        return dict(candidate=self.active,artifact_digest=product.get('artifact_digest'),source_digest=product.get('source_digest'))

    def both(self):
        return dict(database_digest=digest(b.state(self.deployment.db)),provider_digest=digest(self.deployment.provider.snapshot()))

    def operation(self,args):
        with self.lock:
            if self.closed:raise ValueError('session closed')
            if not isinstance(args,list) or not args or not all(isinstance(a,str) and len(a)<256 for a in args):raise ValueError('invalid arguments')
            op=args[0]
            if op in ('help','catalog'):
                return dict(operations={
                    'baseline':'build original product and run old client',
                    'backup BASELINE':'retain original code and seeded database',
                    'build':'build four components twice and freeze candidate',
                    'verify CANDIDATE GROUP':'groups: '+', '.join(b.GROUPS),
                    'deploy CANDIDATE':'start built API and migrate retained DB',
                    'handoff':'checked ABI1 -> paid + pending returns; receive ABI2 payment_contract',
                    'drain':'pay old pending intent through ABI2 exactly once',
                    'checkpoint':'hash application and provider ledgers',
                    'rollback BACKUP':'start original code on same upgraded DB',
                    'rollback-check':'old client works, new writes unavailable',
                    'smoke':'verify retained journey, worker and both clients'},guide='RELEASE.md')
            receipt=f'r{len(self.receipts)+1:04}'
            result=dict(receipt=receipt,operation=op,args=args[1:],outcome='passed',source_digest=self.source_digest())
            notes=self.notes();private={}
            try:
                if op in ('baseline','build') and len(args)==1:
                    path,_=self.freeze(receipt);raw=b.build(path)
                    parts=b.unpack(raw)
                    result.update(candidate=receipt,artifact_digest=sha(raw),source_hashes=self.source_hashes(),components={n:sha(v) for n,v in parts.items()},review_receipt=self.review['receipt'] if self.review else None)
                    self.products[receipt]=dict(raw=raw,source_digest=result['source_digest'],artifact_digest=sha(raw))
                    private['artifact_b64']=base64.b64encode(raw).decode()
                    if op=='baseline':
                        p=b.Product(raw,migrate=False)
                        try:
                            b.old.check(p,'legacy_client',0)
                            private['database_b64']=base64.b64encode(p.db.read_bytes()).decode()
                            result['database_digest']=digest(b.state(p.db))
                        finally:p.close()
                    else:result['reproducible']=raw==b.build(path)
                elif op=='backup' and len(args)==2 and args[1] in self.receipts:
                    original=self.receipts[args[1]]
                    if original['operation']!='baseline' or original['outcome']!='passed':raise ValueError('passing baseline required')
                    self.backups[receipt]=original
                    result.update(backup=receipt,baseline=args[1],artifact_digest=original['artifact_digest'],database_digest=original['database_digest'],source_digest=original['source_digest'])
                elif op=='verify' and len(args)==3 and args[1] in self.products and args[2] in b.GROUPS:
                    product=self.products[args[1]];phase=2 if self.review else 1
                    result.update(candidate=args[1],group=args[2],phase=phase,review_receipt=self.review['receipt'] if self.review else None,artifact_digest=product['artifact_digest'],source_digest=product['source_digest'],cases=b.evaluate(product['raw'],scope=args[2],public=True,phase=phase,contract=self.review['payment_contract'] if self.review else None))
                elif op=='deploy' and len(args)==2 and args[1] in self.products:
                    product=self.products[args[1]];before=self.both() if self.deployment else None
                    if self.deployment:self.deployment.start(artifact=product['raw'],migrate=True)
                    else:self.deployment=b.Product(product['raw'])
                    self.active=args[1]
                    result.update(self.binding(),endpoint=self.deployment.base,before=before,after=self.both())
                    if self.review:
                        result['review_receipt']=self.review['receipt']
                        if not self.drained:
                            b.success(self.deployment.req('GET','/health')[1].get('release_abi')==2,'deploy ABI2 after handoff')
                            b.success(b.release_proof(self.deployment,self.prepared['ids'])==self.prepared,'upgrade lost or changed queued/paid data')
                            result['upgrade_preserved']=True
                elif op=='handoff' and len(args)==1 and self.deployment and self.active in self.products:
                    if self.review:raise ValueError('handoff already issued: '+self.review['receipt'])
                    checks=[e for e in self.receipts.values() if e['operation']=='verify' and e['outcome']=='passed' and e.get('candidate')==self.active and e.get('phase')==1]
                    b.success(all(any(e.get('group')==g for e in checks) for g in b.GROUPS),'all 11 ABI1 groups must pass before handoff')
                    b.success(self.source_digest()==self.products[self.active]['source_digest'],'source changed since preflight build')
                    self.prepared=b.release_prepare(self.deployment)
                    contract=b.contract2(self.products[self.active]['artifact_digest'])
                    result.update(self.binding(),proof=self.prepared,payment_contract=contract,review_receipt=receipt,**self.both())
                    self.review=dict(receipt=receipt,payment_contract=contract)
                    self.deployment.provider.contract=contract
                elif op=='drain' and len(args)==1 and self.deployment and self.review:
                    b.success(self.deployment.req('GET','/health')[1].get('release_abi')==2,'ABI2 required')
                    if self.drained:proof=b.release_smoke(self.deployment,self.drained)
                    else:proof=b.release_drain(self.deployment,self.prepared)
                    self.drained=proof
                    result.update(self.binding(),review_receipt=self.review['receipt'],proof=proof,**self.both())
                elif op=='checkpoint' and len(args)==1 and self.deployment and self.drained:
                    result.update(self.binding(),proof=b.release_smoke(self.deployment,self.drained),**self.both())
                elif op=='rollback' and len(args)==2 and args[1] in self.backups and self.deployment:
                    old=self.backups[args[1]];before=self.both();previous=self.active
                    self.deployment.start(artifact=base64.b64decode(old['artifact_b64']),migrate=False)
                    self.active='legacy:'+args[1]
                    result.update(backup=args[1],previous=previous,candidate=self.active,artifact_digest=old['artifact_digest'],before=before,after=self.both())
                    b.success(result['before']==result['after'],'rollback changed either ledger')
                elif op=='rollback-check' and len(args)==1 and self.deployment and self.active.startswith('legacy:'):
                    before=self.both();b.old.check(self.deployment,'legacy_client',0)
                    b.success(self.deployment.create('rollback-probe')[0]==404,'legacy accepts new writes')
                    result.update(candidate=self.active,before=before,after=self.both());b.success(before==result['after'])
                elif op=='smoke' and len(args)==1 and self.deployment and self.active in self.products and self.drained:
                    result.update(self.binding(),proof=b.release_smoke(self.deployment,self.drained),**self.both())
                else:raise ValueError('invalid arguments or lifecycle state; see catalog')
                if 'cases' in result and not all(c['passed'] for c in result['cases']):result['outcome']='failed'
            except (OSError,ValueError,AssertionError,KeyError,IndexError,TypeError,sqlite3.Error,subprocess.TimeoutExpired) as exc:
                result.update(outcome='failed',error=f'{type(exc).__name__}: {exc}'[:500])
            item=self.emit('operation',**result,**private,notes_before=notes)
            self.receipts[receipt]=item;result['seq']=item['seq']
            return result

    def finish(self):
        if self.deployment:
            self.emit('runtime_final',**self.binding(),**self.both())
            self.deployment.close()
        return super().finish()
