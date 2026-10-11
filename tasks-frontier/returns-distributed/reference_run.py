"""Real positive release and deliberate, separately measurable omissions."""
import json
import os
from pathlib import Path
import subprocess

mutant=os.environ.get('REFERENCE_MUTANT','')
GROUPS=('migration','requests','lifecycle','money','security','integration','compatibility','durability','outbox','payments','clients')

def ops(*args,allow=False):
    p=subprocess.run(['arena-ops',*args],capture_output=True,text=True)
    result=json.loads(p.stdout)
    print('OP',args,result.get('outcome'),[(c['id'],c['detail']) for c in result.get('cases',[]) if not c['passed']],result.get('error',''),flush=True)
    if p.returncode and not allow:raise RuntimeError(str(args)+': '+p.stdout)
    return result

def write(path,text):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)

def replace(path,old,new):
    p=Path(path);v=p.read_text();assert old in v,(path,old);p.write_text(v.replace(old,new))

if mutant=='noop':raise SystemExit(0)
baseline=ops('baseline');backup=ops('backup',baseline['receipt'])
for path,content in json.loads(Path('/tmp/reference-solution.json').read_text()).items():write(path,content)
preflight=ops('build');checks={}
for group in GROUPS:checks[group]=ops('verify',preflight['candidate'],group)
ops('deploy',preflight['candidate'])
if mutant=='skip-handoff':
    review={'receipt':'missing','payment_contract':{'protocol':2,'merchants':{'alpha':'invented-a','beta':'invented-b'},'signing_key':'invented-fixture'}}
else:review=ops('handoff')
write('config/payment-contract.json',json.dumps(review['payment_contract'],sort_keys=True)+'\n')
write('src/orders/release.py','ABI = 2\n')
if mutant!='stale-client':replace('client/refunds.mjs','const ABI = 1;','const ABI = 2;')
if mutant=='no-worker':write('src/payouts/main.py','def main(): print(\'{"processed":0}\')\n')
if mutant=='duplicate-charge':replace('src/payouts/main.py',"key=job['provider_key'];", "key=job['provider_key']+'/'+str(job['attempts']);")
if mutant=='ignore-lease':replace('src/payouts/main.py',"(now,now)).fetchone()","(now,now+100)).fetchone()")
if mutant=='lost-pending':replace('src/orders/db.py',"c.execute('PRAGMA user_version='+str(2 if ABI==1 else 3))", "if version==2 and ABI==2:c.execute(\"DELETE FROM payouts WHERE state='queued'\")\n        c.execute('PRAGMA user_version='+str(2 if ABI==1 else 3))")
if mutant=='old-wire':replace('src/payouts/main.py',"contract=json.load(f)","contract={'protocol':1}")
if mutant=='wrong-cursor':replace('src/orders/domain.py',"cursor['actor']!=list(actor)", "False")
if mutant=='unfenced-worker':replace('src/payouts/main.py',"if current['state']!='processing' or current['attempts']!=attempt or current['lease_until']!=now+30:","if False:")
if mutant=='equivalent':
    replace('src/payouts/main.py',"sort_keys=True,separators=(',',':'),ensure_ascii=False", "sort_keys=False,indent=2,ensure_ascii=True")
    replace('client/refunds.mjs','JSON.stringify(result)','JSON.stringify({...result, diagnostic: "accepted extra field"}, null, 2)')
candidate=ops('build')
if mutant!='stale-checks':
    for group in GROUPS:checks[group]=ops('verify',candidate['candidate'],group,allow=True)
deploy=ops('deploy',candidate['candidate'],allow=True)
drain=ops('drain',allow=True);checkpoint=ops('checkpoint',allow=True)
rollback={};probe={}
if mutant!='no-rollback':
    rollback=ops('rollback',backup['receipt'],allow=True);probe=ops('rollback-check',allow=True)
    deploy=ops('deploy',candidate['candidate'],allow=True)
smoke=ops('smoke',allow=True)
manifest=dict(candidate=candidate['candidate'],source_digest=candidate['source_digest'],artifact_digest=candidate['artifact_digest'],components=candidate['components'],preflight_candidate=preflight['candidate'],review_receipt=review['receipt'],deploy_receipt=deploy['receipt'],drain_receipt=drain['receipt'],checkpoint_receipt=checkpoint['receipt'],rollback_receipt=rollback.get('receipt'),rollback_check_receipt=probe.get('receipt'),smoke_receipt='r9999' if mutant=='fake-manifest' else smoke['receipt'],verification={g:r['receipt'] for g,r in checks.items()},limitations=[])
write('reports/release.json',json.dumps(manifest,indent=2)+'\n')
write('reports/handover.md',f"Bundle {candidate['artifact_digest']}; API, worker and Node activated ABI2 after review. Code rollback preserves both financial ledgers; redeploy reruns additive migration. Limitations: none in positive reference.\n")
print('Reference distributed release complete')
