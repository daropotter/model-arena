"""Executable positive and negative controls through the real operation service."""
import json
import os
from pathlib import Path
import subprocess

mutant=os.environ.get('REFERENCE_MUTANT','')

def ops(*args,allow=False):
    p=subprocess.run(['arena-ops',*args],capture_output=True,text=True)
    result=json.loads(p.stdout)
    if p.returncode and not allow:raise RuntimeError(str(args)+': '+p.stdout)
    return result

def write(path,text):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)

if mutant=='noop':raise SystemExit(0)
baseline=ops('baseline');backup=ops('backup',baseline['receipt'])
solution=json.loads(Path('/tmp/reference-solution.json').read_text())
for path,content in solution.items():
    write('prototypes/'+path if mutant=='dead-code' else path,content)
if mutant=='broken-client':write('src/orders/client.py','def run(args): raise SystemExit(1)\n')
if mutant=='duplicate-refund':
    p=Path('src/orders/domain.py');p.write_text(p.read_text().replace("if row['status']==target:return 200,view(c,row)","if row['status']==target:\n        if action=='settle':c.execute('UPDATE refund_ledger SET amount_cents=amount_cents*2 WHERE tenant=? AND return_id=?',(tenant,rid))\n        return 200,view(c,row)"))
if mutant=='lost-state':
    p=Path('src/orders/db.py');p.write_text(p.read_text().replace("c.execute('PRAGMA user_version=2')","if version==2:\n            for table in ('returns','return_items','return_events','refund_ledger'):c.execute('DELETE FROM '+table)\n        c.execute('PRAGMA user_version=2')"))
candidate=ops('build');checks={}
for group in ('migration','requests','lifecycle','money','security','integration','compatibility','durability'):
    checks[group]=ops('verify',candidate['candidate'],group,allow=True)
if mutant in ('stale-build','stale-check'):
    with Path('src/orders/domain.py').open('a') as f:f.write('\n# source changed after the green checks\n')
    if mutant=='stale-check':candidate=ops('build')
deploy=ops('deploy',candidate['candidate'],allow=True)
journey=ops('journey',allow=True);checkpoint=ops('checkpoint',allow=True)
rollback={};probe={}
if mutant!='no-rollback':
    rollback=ops('rollback',backup['receipt'],allow=True);probe=ops('rollback-check',allow=True)
    deploy=ops('deploy',candidate['candidate'],allow=True)
smoke=ops('smoke',allow=True)
manifest=dict(candidate=candidate['candidate'],source_digest=candidate['source_digest'],artifact_digest=candidate['artifact_digest'],deploy_receipt=deploy['receipt'],journey_receipt=journey['receipt'],checkpoint_receipt=checkpoint['receipt'],rollback_receipt=rollback.get('receipt'),rollback_check_receipt=probe.get('receipt'),smoke_receipt='r9999' if mutant=='fake-report' else smoke['receipt'],verification={g:r['receipt'] for g,r in checks.items()},limitations=[])
write('reports/release.json',json.dumps(manifest,indent=2)+'\n')
write('reports/handover.md',f"Artifact {candidate['artifact_digest']}; code rollback retains the additive database, redeploy reruns migrations. Limitations: none in the reference.\n")
print('Reference release complete')
