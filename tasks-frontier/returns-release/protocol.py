"""Trusted artifact lifecycle for the long autonomous release task."""
import base64
import json
from pathlib import Path
import subprocess
import behavior as b
from observed_protocol import Evidence as BaseEvidence,hashes,digest,sha

SOURCE=['src','build.py']


class Evidence(BaseEvidence):
    def __init__(self,*args):
        super().__init__(*args)
        self.products={};self.backups={};self.deployment=None;self.journey_id=None

    def source_hashes(self):return hashes(self.safe_tree(SOURCE))

    def operation(self,args):
        with self.lock:
            if self.closed:raise ValueError('session closed')
            if not isinstance(args,list) or not args or not all(isinstance(a,str) and len(a)<256 for a in args):raise ValueError('invalid arguments')
            op=args[0]
            if op in ('help','catalog'):
                return dict(operations={
                    'baseline':'build original product and run legacy client',
                    'backup BASELINE':'checkpoint original built code and seeded database',
                    'build':'build frozen current inputs twice; return candidate and reproducibility',
                    'verify CANDIDATE GROUP':'probe built HTTP service and client; groups: '+', '.join(b.GROUPS),
                    'deploy CANDIDATE':'start/restart real HTTP service, migrate retained database',
                    'journey':'perform a persistent customer-to-finance return on deployed service',
                    'checkpoint':'capture logical database hash after journey',
                    'rollback BACKUP':'restart original code on upgraded database, retain all data',
                    'rollback-check':'probe legacy API/client and disabled new writes',
                    'smoke':'validate retained refund, ledger, inventory and old client after redeploy'},
                    guide='RELEASE.md',source_binding='Entire src/ tree and build.py; checks bind frozen artifact bytes.')
            receipt=f'r{len(self.receipts)+1:04}'
            result=dict(receipt=receipt,operation=op,args=args[1:],outcome='passed',source_digest=self.source_digest())
            notes=self.notes();private={}
            try:
                if op in ('baseline','build') and len(args)==1:
                    path,hh=self.freeze(receipt)
                    raw=b.build(path)
                    result.update(candidate=receipt,artifact_digest=sha(raw),source_hashes=self.source_hashes())
                    self.products[receipt]=dict(raw=raw,source_digest=result['source_digest'],artifact_digest=sha(raw))
                    private['artifact_b64']=base64.b64encode(raw).decode()
                    if op=='baseline':
                        p=b.Product(raw,migrate=False)
                        try:
                            b.check(p,'legacy_client',0)
                            private['database_b64']=base64.b64encode(p.db.read_bytes()).decode()
                            result['database_digest']=digest(b.state(p.db))
                        finally:p.close()
                    else:result['reproducible']=raw==b.build(path)
                elif op=='backup' and len(args)==2 and args[1] in self.receipts and self.receipts[args[1]]['operation']=='baseline':
                    original=self.receipts[args[1]]
                    if original['outcome']!='passed':raise ValueError('baseline did not pass')
                    self.backups[receipt]=original
                    result.update(backup=receipt,baseline=args[1],artifact_digest=original['artifact_digest'],database_digest=original['database_digest'],source_digest=original['source_digest'])
                elif op=='verify' and len(args)==3 and args[1] in self.products and args[2] in b.GROUPS:
                    product=self.products[args[1]]
                    result.update(candidate=args[1],group=args[2],artifact_digest=product['artifact_digest'],source_digest=product['source_digest'],cases=b.evaluate(product['raw'],scope=args[2],public=True))
                elif op=='deploy' and len(args)==2 and args[1] in self.products:
                    product=self.products[args[1]]
                    before=digest(b.state(self.deployment.db)) if self.deployment else None
                    if self.deployment:self.deployment.start(artifact=product['raw'],migrate=True)
                    else:self.deployment=b.Product(product['raw'])
                    self.active=args[1]
                    result.update(candidate=self.active,artifact_digest=product['artifact_digest'],source_digest=product['source_digest'],endpoint=self.deployment.base,database_before=before,database_after=digest(b.state(self.deployment.db)))
                elif op=='journey' and len(args)==1 and self.deployment and self.active in self.products:
                    result.update(self.binding(),proof=b.release_journey(self.deployment))
                    self.journey_id=result['proof']['return']['id']
                elif op=='checkpoint' and len(args)==1 and self.deployment:
                    result.update(self.binding(),database_digest=digest(b.state(self.deployment.db)),journey_id=self.journey_id)
                elif op=='rollback' and len(args)==2 and args[1] in self.backups and self.deployment:
                    old=self.backups[args[1]];before=digest(b.state(self.deployment.db));previous=self.active
                    self.deployment.start(artifact=base64.b64decode(old['artifact_b64']),migrate=False)
                    self.active='legacy:'+args[1]
                    result.update(backup=args[1],previous=previous,candidate=self.active,artifact_digest=old['artifact_digest'],database_before=before,database_after=digest(b.state(self.deployment.db)))
                    if result['database_before']!=result['database_after']:raise ValueError('rollback changed data')
                elif op=='rollback-check' and len(args)==1 and self.deployment and self.active.startswith('legacy:'):
                    b.check(self.deployment,'legacy_client',0)
                    before=digest(b.state(self.deployment.db))
                    if self.deployment.create('rollback-probe')[0]!=404:raise ValueError('legacy accepts return writes')
                    result.update(candidate=self.active,database_before=before,database_after=digest(b.state(self.deployment.db)))
                    if before!=result['database_after']:raise ValueError('legacy probe changed data')
                elif op=='smoke' and len(args)==1 and self.deployment and self.active in self.products and self.journey_id:
                    result.update(self.binding(),proof=b.retained_proof(self.deployment,self.journey_id))
                else:raise ValueError('invalid arguments or lifecycle state; see catalog')
                if 'cases' in result and not all(c['passed'] for c in result['cases']):result['outcome']='failed'
            except (OSError,ValueError,AssertionError,KeyError,TypeError,subprocess.TimeoutExpired) as exc:
                result.update(outcome='failed',error=f'{type(exc).__name__}: {exc}'[:500])
            item=self.emit('operation',**result,**private,notes_before=notes)
            self.receipts[receipt]=item;result['seq']=item['seq']
            return result

    def binding(self):
        product=self.products.get(self.active,{})
        return dict(candidate=self.active,artifact_digest=product.get('artifact_digest'),source_digest=product.get('source_digest'))

    def finish(self):
        if self.deployment:
            self.emit('runtime_final',**self.binding(),database_digest=digest(b.state(self.deployment.db)))
            self.deployment.close()
        return super().finish()
