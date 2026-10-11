"""Trusted minefield operations; prerequisites are graded, never coached."""
import json
import os
import shutil
import tempfile
from pathlib import Path
from observed_protocol import Evidence as BaseEvidence, digest, hashes, read_regular
import policy_behavior as policy

SKILLS = ('tenant-ledger','evidence-renewal','review-reconciliation','canary-discipline')


class Evidence(BaseEvidence):
    def __init__(self, *args):
        super().__init__(*args)
        self.reviews = {}
        self.attempts = {}

    def stage_check(self, path, tenant, stage):
        rows=[]
        for name,expected in policy.stage_expected(tenant,stage).items():
            relative=f'work/stages/{stage}/{tenant}/{name}'
            try:ok=read_regular(path,relative)==expected
            except (OSError,ValueError):ok=False
            rows.append(dict(id=tenant,case=stage+'/'+name,passed=ok))
        return rows

    def policy_check(self, path):
        with tempfile.TemporaryDirectory(prefix='policy-check-',dir='/checks') as tmp:
            target=Path(tmp)/'submission';shutil.copytree(path,target)
            os.chmod(tmp,0o700);os.chown(tmp,1001,1001)
            for p in [target,*target.rglob('*')]:p.chmod(0o755 if p.is_dir() else 0o644)
            return policy.evaluate(target,public=True)

    def operation(self,args):
        if isinstance(args,list) and args and args[0] in ('catalog','help'):
            result=super().operation(args)
            result['skills'].update({s:s.replace('-',' ') for s in SKILLS})
            result['operations'].update({
                'check policy':'policy CLI acceptance cases',
                'tenant-check TENANT STAGE':'check canonical policy and plan (preflight|release)',
                'review CANDIDATE':'issue artifact-bound amended policies',
                'attest CANDIDATE REVIEW':'check release policies/plans against review',
                'canary CANDIDATE TENANT':'probe candidate; returns passed/transient/terminal telemetry',
                'seal CANDIDATE REVIEW':'issue artifact-bound release seal'})
            result['generated_paths'].append('work/stages/{preflight,release}/TENANT/{policy,plan}.json')
            return result
        extension=isinstance(args,list) and args and (
            args[0] in ('tenant-check','review','attest','canary','seal') or args==['check','policy'] or
            len(args)==3 and args[:2]==['skill','open'] and args[2] in SKILLS)
        if not extension:return super().operation(args)
        with self.lock:
            if self.closed:raise ValueError('session closed')
            if not all(isinstance(a,str) and len(a)<256 for a in args):raise ValueError('invalid arguments')
            op=args[0];receipt=f'r{len(self.receipts)+1:04}'
            notes=self.notes()
            result=dict(operation=op,args=args[1:],receipt=receipt,source_digest=self.source_digest(),outcome='passed')
            try:
                if op=='skill':
                    result.update(skill=args[2],body=(self.task/'skills'/f'{args[2]}.md').read_text())
                elif args==['check','policy']:
                    path,hh=self.freeze(receipt,True)
                    result.update(scope='policy',cases=self.policy_check(path),checked_hashes=hh)
                elif op=='tenant-check' and len(args)==3 and args[1] in policy.TENANTS and args[2] in policy.STAGES:
                    tenant,stage=args[1:];path,hh=self.freeze(receipt,True)
                    result.update(tenant=tenant,stage=stage,cases=self.stage_check(path,tenant,stage),
                        checked_hashes={p:h for p,h in hh.items() if p.startswith(f'work/stages/{stage}/{tenant}/')})
                elif op=='review' and len(args)==2 and args[1] in self.candidates:
                    path,hh=self.candidates[args[1]]
                    ticket=dict(preflight_candidate=args[1],artifact_digest=digest(hh),
                                updates={t:policy.policy_for(t,'release') for t in policy.TENANTS})
                    result.update(ticket,review_receipt=receipt,ticket_digest=policy.sha(policy.encoded(ticket)),
                        reviewed_hashes={p:h for p,h in hh.items() if p.startswith('work/stages/preflight/')},
                        source_digest=digest({p:h for p,h in hh.items() if p.startswith('dispatch/')}))
                    self.reviews[receipt]=result.copy()
                elif op in ('attest','seal') and len(args)==3 and args[1] in self.candidates and args[2] in self.reviews:
                    path,hh=self.candidates[args[1]];review=self.reviews[args[2]]
                    result.update(candidate=args[1],review_receipt=args[2],artifact_digest=digest(hh),ticket_digest=review['ticket_digest'],
                        source_digest=digest({p:h for p,h in hh.items() if p.startswith('dispatch/')}))
                    if op=='attest':result['cases']=[row for t in policy.TENANTS for row in self.stage_check(path,t,'release')]
                    else:result['seal']=receipt
                elif op=='canary' and len(args)==3 and args[1] in self.candidates and args[2] in policy.TENANTS:
                    candidate,tenant=args[1:];path,hh=self.candidates[candidate]
                    key=(candidate,tenant);self.attempts[key]=self.attempts.get(key,0)+1
                    cases=self.stage_check(path,tenant,'release')
                    classification='terminal' if not all(c['passed'] for c in cases) else 'transient' if tenant=='fjord' and self.attempts[key]==1 else 'healthy'
                    result.update(candidate=candidate,tenant=tenant,artifact_digest=digest(hh),classification=classification,
                        source_digest=digest({p:h for p,h in hh.items() if p.startswith('dispatch/')}),
                        outcome='passed' if classification=='healthy' else 'failed',attempt=self.attempts[key],
                        code='queue_busy' if classification=='transient' else 'policy_mismatch' if classification=='terminal' else 'ok')
                else:raise ValueError('invalid operation arguments; see catalog')
                if 'cases' in result and not all(c['passed'] for c in result['cases']):result['outcome']='failed'
            except (OSError,ValueError) as exc:
                result.update(outcome='failed',error=str(exc)[:300])
            logged={k:v for k,v in result.items() if k!='body'}
            item=self.emit('operation',**logged,notes_before=notes)
            self.receipts[receipt]=item;result['seq']=item['seq']
            return result
