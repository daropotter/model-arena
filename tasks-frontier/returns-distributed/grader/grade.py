"""48-stage evaluation of shipped bytes and two-phase release evidence."""
import base64
import json
import behavior as b
from legacy_grade import dependency_metrics,digest,sha


def grade(workspace,audit,requirements):
    stages=requirements['stages'];events=audit.get('events',[])
    if audit.get('protocol')!='observed-fuse-v1' or not audit.get('complete') or not events or events[0]['kind']!='begin' or events[-1]['kind']!='end' or [e['seq'] for e in events]!=list(range(1,len(events)+1)):
        return dict(passed=False,score=0,groups={},grader_error=True,detail='missing or invalid trusted audit')
    values={r['id']:False for r in stages};details={};final=events[-1]
    operations=[e for e in events if e['kind']=='operation']
    def ops(op):return [e for e in operations if e['operation']==op and e['outcome']=='passed']
    def source(mapping):return {p:h for p,h in mapping.items() if p=='build.py' or p.startswith(('src/','client/','config/'))}
    def last(rows):return rows[-1] if rows else None
    initial=digest(source(audit['initial']));current=final['source_digest']
    active=next((e for e in ops('build') if e['receipt']==final.get('active')),None)
    baselines=[e for e in ops('baseline') if e['source_digest']==initial]
    values['S01']=bool(baselines)
    backups=[e for e in ops('backup') if any(e.get('baseline')==r['receipt'] for r in baselines)]
    values['S02']=bool(backups)
    review=last(ops('handoff'))
    raw=None;behavior=[]
    if active:
        try:
            raw=base64.b64decode(active['artifact_b64'],validate=True)
            if sha(raw)!=active['artifact_digest']:raise ValueError('artifact hash mismatch')
            behavior=b.evaluate(raw,phase=2,contract=review['payment_contract'] if review else None)
        except (ValueError,KeyError) as exc:details['S39']=str(exc)
    for stage in stages:
        if stage['group']=='release':continue
        cases=[c for c in behavior if c['id']==stage['id']]
        values[stage['id']]=bool(cases) and all(c['passed'] for c in cases)
        details[stage['id']]='; '.join(c['detail'] for c in cases if not c['passed']) or ('no active built artifact' if not cases else '')
    def for_candidate(e,c):
        return bool(c and e.get('candidate')==c['candidate'] and e.get('artifact_digest')==c['artifact_digest'] and e.get('source_digest')==c['source_digest'])
    def all_checks(c,phase,before=None):
        checks=[e for e in ops('verify') if for_candidate(e,c) and e.get('phase')==phase and (before is None or e['seq']<before) and (phase==1 or review and e.get('review_receipt')==review['receipt'] and e['seq']>review['seq'])]
        return all(any(e.get('group')==g for e in checks) for g in b.GROUPS)
    preflight=next((e for e in reversed(ops('build')) if (not review or e['candidate']==review['candidate']) and all_checks(e,1,review['seq'] if review else None)),None)
    values['S37']=bool(preflight)
    predeploy=last([e for e in ops('deploy') if for_candidate(e,preflight) and review and e['seq']<review['seq']])
    values['S38']=bool(review and preflight and predeploy)
    if active and raw:
        try:
            rebuilt=b.build(workspace)
            preserved=all(final.get('workspace_hashes',{}).get(p)==h for p,h in audit['initial'].items() if p not in source(audit['initial']))
            changed=bool(preflight and active['source_digest']!=preflight['source_digest'] and all(active['components'][n]!=preflight['components'][n] for n in b.COMPONENTS))
            values['S39']=bool(review and active['seq']>review['seq'] and active.get('review_receipt')==review['receipt'] and changed and active['source_digest']==current and active.get('reproducible') and rebuilt==raw and preserved and values['S36'] and values['S35'] and values['S03'])
        except (OSError,ValueError,KeyError) as exc:details['S39']=str(exc)[:200]
    def bound(e):return for_candidate(e,active) and active['source_digest']==current
    checks=[e for e in ops('verify') if bound(e) and e.get('phase')==2 and review and e.get('review_receipt')==review['receipt'] and e['seq']>active['seq']]
    deploys=[e for e in ops('deploy') if bound(e)]
    upgrade=next((e for e in deploys if review and e['seq']>review['seq'] and e.get('upgrade_preserved') and e.get('review_receipt')==review['receipt']),None)
    values['S40']=bool(upgrade and all_checks(active,2,upgrade['seq']) and all(any(e.get('group')==g and e['seq']<upgrade['seq'] for e in checks) for g in b.GROUPS))
    values['S41']=bool(upgrade)
    drain=last([e for e in ops('drain') if bound(e) and upgrade and e['seq']>upgrade['seq'] and e.get('review_receipt')==review['receipt']])
    values['S42']=bool(drain)
    checkpoint=last([e for e in ops('checkpoint') if bound(e) and drain and e['seq']>drain['seq'] and e.get('proof')==drain['proof']])
    values['S43']=bool(checkpoint)
    state={k:checkpoint[k] for k in ('database_digest','provider_digest')} if checkpoint else None
    rollback=last([e for e in ops('rollback') if active and e.get('previous')==active['candidate'] and checkpoint and e['seq']>checkpoint['seq'] and e.get('before')==e.get('after')==state and any(x['receipt']==e.get('backup') for x in backups)])
    values['S44']=bool(rollback)
    probe=last([e for e in ops('rollback-check') if rollback and e.get('candidate')==rollback['candidate'] and e['seq']>rollback['seq'] and e.get('before')==e.get('after')==state])
    values['S45']=bool(probe)
    redeploy=last([e for e in deploys if probe and e['seq']>probe['seq'] and e.get('before')==e.get('after')==state])
    values['S46']=bool(redeploy)
    smoke=last([e for e in ops('smoke') if bound(e) and redeploy and e['seq']>redeploy['seq'] and e.get('proof')==drain['proof']])
    runtime=last([e for e in events if e['kind']=='runtime_final']) or {}
    values['S47']=bool(smoke and bound(runtime) and all(runtime.get(k)==v for k,v in state.items()))
    notes=final.get('notes',{})
    try:manifest=json.loads(notes.get('reports/release.json','null'))
    except ValueError:manifest=None
    expected=dict(candidate=active['candidate'],artifact_digest=active['artifact_digest'],source_digest=current,components=active['components'],preflight_candidate=preflight['candidate'],review_receipt=review['receipt'],deploy_receipt=redeploy['receipt'],drain_receipt=drain['receipt'],checkpoint_receipt=checkpoint['receipt'],rollback_receipt=rollback['receipt'],rollback_check_receipt=probe['receipt'],smoke_receipt=smoke['receipt']) if all((active,preflight,review,redeploy,drain,checkpoint,rollback,probe,smoke)) else {}
    valid=bool(expected and isinstance(manifest,dict) and all(manifest.get(k)==v for k,v in expected.items()))
    if valid:
        mapping=manifest.get('verification',{})
        valid=isinstance(mapping,dict) and all(any(e.get('group')==g and e['receipt']==mapping.get(g) for e in checks) for g in b.GROUPS) and isinstance(manifest.get('limitations'),list)
    handover=notes.get('reports/handover.md','')
    values['S48']=bool(valid and handover.strip() and active['artifact_digest'] in handover and 'rollback' in handover.lower())
    if audit.get('invalid_workspace'):values={k:False for k in values};details['S39']='invalid candidate filesystem'
    metrics=dependency_metrics(stages,values);complete=sum(values.values());groups={}
    for group in ('release',*b.GROUPS):
        ids=[r['id'] for r in stages if r['group']==group];groups[group]=dict(passed=sum(values[i] for i in ids),total=len(ids))
    scenarios={name:all(values[f'S{i:02}'] for i in ids) for name,ids in {
        'customer_refund':[6,8,9,11,13,14], 'partial_refunds':[14,15,16,27],
        'cancel_and_reject':[8,10,12], 'concurrent_retries':[17,18,31],
        'access_control':[19,20,21,33], 'client_and_accounting':[22,23,24,25,34,35],
        'provider_failure_recovery':[28,29,30,32,33], 'late_integration':[36,37,38,39,40,41,42],
        'durable_release':[26,43,44,45,46,47,48]}.items()}
    failures=[k for k,v in values.items() if not v]
    return dict(passed=not failures,score=round(complete/len(stages),6),completion_fraction=complete/len(stages),completed_stages=complete,total_stages=len(stages),**metrics,
        user_scenarios=scenarios,scenario_fraction=sum(scenarios.values())/len(scenarios),final_artifact_verified=values['S39'] and values['S40'],groups=groups,
        detail='all release stages passed' if not failures else 'failed: '+', '.join(failures),
        cases=[dict(id=r['id'],status='pass' if values[r['id']] else 'fail',detail=details.get(r['id'],'')) for r in stages],behavior_cases=behavior)
