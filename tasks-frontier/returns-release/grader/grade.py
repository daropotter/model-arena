"""Completion, dependency closure, journeys and evidence on the shipped binary."""
import base64
import hashlib
import json
from pathlib import Path
import behavior as b


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(raw):return hashlib.sha256(raw).hexdigest()

def dependency_metrics(stages,passed):
    depth={};maximum={};closed={}
    for stage in stages:
        key=stage['id'];deps=stage['depends_on']
        maximum[key]=1+max((maximum[d] for d in deps),default=0)
        closed[key]=bool(passed[key] and all(closed[d] for d in deps))
        depth[key]=1+max((depth[d] for d in deps),default=0) if closed[key] else 0
    longest=max(depth.values(),default=0);possible=max(maximum.values(),default=0)
    return dict(longest_valid_chain=longest,max_chain=possible,chain_fraction=longest/possible if possible else 0,dependency_complete=sum(closed.values()),blocked=[k for k in closed if passed[k] and not closed[k]])


def grade(workspace,audit,requirements):
    stages=requirements['stages'];events=audit.get('events',[])
    if audit.get('protocol')!='observed-fuse-v1' or not audit.get('complete') or not events or events[0]['kind']!='begin' or events[-1]['kind']!='end' or [e['seq'] for e in events]!=list(range(1,len(events)+1)):
        return dict(passed=False,score=0,groups={},grader_error=True,detail='missing or invalid trusted audit')
    values={r['id']:False for r in stages};details={};final=events[-1]
    operations=[e for e in events if e['kind']=='operation']
    receipts={e['receipt']:e for e in operations}
    def ops(op):return [e for e in operations if e['operation']==op and e['outcome']=='passed']
    def source(mapping):return {p:h for p,h in mapping.items() if p=='build.py' or p.startswith('src/')}
    initial=digest(source(audit['initial']));current=final['source_digest']
    active=next((e for e in ops('build') if e['receipt']==final.get('active')),None)
    baselines=[e for e in ops('baseline') if e['source_digest']==initial]
    values['S01']=bool(baselines)
    backups=[e for e in ops('backup') if any(e.get('baseline')==r['receipt'] for r in baselines)]
    values['S02']=bool(backups)
    raw=None;behavior=[]
    if active:
        try:
            raw=base64.b64decode(active['artifact_b64'],validate=True)
            if sha(raw)!=active['artifact_digest']:raise ValueError('artifact hash mismatch')
            behavior=b.evaluate(raw)
        except (ValueError,KeyError) as exc:details['S27']=str(exc)
    for stage in stages:
        if stage['group']=='release':continue
        cases=[c for c in behavior if c['id']==stage['id']]
        values[stage['id']]=bool(cases) and all(c['passed'] for c in cases)
        details[stage['id']]='; '.join(c['detail'] for c in cases if not c['passed']) or ('no active built artifact' if not cases else '')
    if active and raw:
        try:
            rebuilt=b.build(workspace)
            preserved=all(final.get('workspace_hashes',{}).get(p)==h for p,h in audit['initial'].items() if p not in source(audit['initial']))
            values['S27']=bool(active['source_digest']==current and active.get('reproducible') and rebuilt==raw and preserved)
        except (OSError,ValueError) as exc:details['S27']=str(exc)[:200]
    def bound(e):return bool(active and e.get('candidate')==active['candidate'] and e.get('artifact_digest')==active['artifact_digest'] and e.get('source_digest')==current)
    checks=[e for e in ops('verify') if bound(e)]
    deploys=[e for e in ops('deploy') if bound(e)]
    journeys=[e for e in ops('journey') if bound(e)]
    journey=journeys[-1] if journeys else None
    first_deploy=next((e for e in reversed(deploys) if journey and e['seq']<journey['seq']),None)
    values['S28']=bool(first_deploy and all(any(e.get('group')==g and e['seq']<first_deploy['seq'] for e in checks) for g in b.GROUPS))
    values['S29']=bool(first_deploy)
    values['S30']=bool(journey and first_deploy)
    checkpoints=[e for e in ops('checkpoint') if bound(e) and journey and e['seq']>journey['seq'] and e.get('journey_id')==journey.get('proof',{}).get('return',{}).get('id')]
    checkpoint=checkpoints[-1] if checkpoints else None
    values['S31']=bool(checkpoint)
    rollbacks=[e for e in ops('rollback') if active and e.get('previous')==active['candidate'] and checkpoint and e['seq']>checkpoint['seq'] and e.get('database_before')==e.get('database_after')==checkpoint['database_digest'] and any(x['receipt']==e.get('backup') for x in backups)]
    rollback=rollbacks[-1] if rollbacks else None
    values['S32']=bool(rollback)
    probes=[e for e in ops('rollback-check') if rollback and e.get('candidate')==rollback['candidate'] and e['seq']>rollback['seq'] and e.get('database_before')==e.get('database_after')==checkpoint['database_digest']]
    probe=probes[-1] if probes else None
    values['S33']=bool(probe)
    redeploys=[e for e in deploys if probe and e['seq']>probe['seq'] and e.get('database_before')==e.get('database_after')==checkpoint['database_digest']]
    redeploy=redeploys[-1] if redeploys else None
    values['S34']=bool(redeploy)
    smokes=[e for e in ops('smoke') if bound(e) and redeploy and e['seq']>redeploy['seq'] and e.get('proof')==journey.get('proof')]
    smoke=smokes[-1] if smokes else None
    runtime=next((e for e in reversed(events) if e['kind']=='runtime_final'),{})
    values['S35']=bool(smoke and bound(runtime) and runtime.get('database_digest')==checkpoint['database_digest'])
    notes=final.get('notes',{})
    try:manifest=json.loads(notes.get('reports/release.json','null'))
    except ValueError:manifest=None
    expected=dict(candidate=active['candidate'],artifact_digest=active['artifact_digest'],source_digest=current,deploy_receipt=redeploy['receipt'],journey_receipt=journey['receipt'],checkpoint_receipt=checkpoint['receipt'],rollback_receipt=rollback['receipt'],rollback_check_receipt=probe['receipt'],smoke_receipt=smoke['receipt']) if all((active,redeploy,journey,checkpoint,rollback,probe,smoke)) else {}
    valid_manifest=bool(expected and isinstance(manifest,dict) and all(manifest.get(k)==v for k,v in expected.items()))
    if valid_manifest:
        mapping=manifest.get('verification',{})
        valid_manifest=isinstance(mapping,dict) and all(any(e.get('group')==g and e['receipt']==mapping.get(g) for e in checks) for g in b.GROUPS)
        valid_manifest=valid_manifest and isinstance(manifest.get('limitations'),list)
    handover=notes.get('reports/handover.md','')
    values['S36']=bool(valid_manifest and handover.strip() and active['artifact_digest'] in handover and 'rollback' in handover.lower())
    if audit.get('invalid_workspace'):
        values={k:False for k in values};details['S27']='invalid candidate filesystem'
    metrics=dependency_metrics(stages,values)
    complete=sum(values.values());groups={}
    for group in ('release',*b.GROUPS):
        ids=[r['id'] for r in stages if r['group']==group]
        groups[group]=dict(passed=sum(values[i] for i in ids),total=len(ids))
    failures=[k for k,v in values.items() if not v]
    scenarios={name:all(values[f'S{i:02}'] for i in ids) for name,ids in {
        'customer_refund':[6,8,9,11,13,14], 'partial_refunds':[14,15,16],
        'cancel_and_reject':[8,10,12], 'concurrent_retries':[17,18],
        'access_control':[19,20,21], 'client_and_accounting':[22,23,24,25],
        'durable_release':[26,29,30,31,32,33,34,35]}.items()}
    return dict(passed=not failures,score=round(complete/len(stages),6),completion_fraction=complete/len(stages),completed_stages=complete,total_stages=len(stages),**metrics,
        user_scenarios=scenarios,scenario_fraction=sum(scenarios.values())/len(scenarios),final_artifact_verified=values['S27'] and values['S28'],
        groups=groups,detail='all release stages passed' if not failures else 'failed: '+', '.join(failures),
        cases=[dict(id=r['id'],status='pass' if values[r['id']] else 'fail',detail=details.get(r['id'],'')) for r in stages],behavior_cases=behavior)
