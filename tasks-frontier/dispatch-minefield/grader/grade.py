"""192 obligations: frozen behavior, per-cohort history, every promotion."""
import json
from pathlib import Path
import base_grade
import policy_behavior as pb
from behavior import encoded


def obj(value, default=None):
    try:return json.loads(value)
    except (TypeError,ValueError):return default


def records(notes,path):
    return [v for line in notes.get(path,'').splitlines() if isinstance(v:=obj(line),dict)]


def touches(event,prefix):
    return any(p==prefix or p.startswith(prefix+'/') or prefix.startswith(p+'/') for p in event.get('paths',[]))


def filtered(hashes,prefix):
    return {p:h for p,h in hashes.items() if p.startswith(prefix+'/')}


def grade(workspace,audit,requirements):
    base_requirements=json.loads((Path(__file__).resolve().parents[1]/'base_requirements.json').read_text())
    base=base_grade.grade(workspace,audit,base_requirements)
    if base.get('grader_error') or audit.get('invalid_workspace'):
        return dict(base,groups=base.get('groups',{}))
    values={c['id']:c['status'] for c in base['cases']}
    details={c['id']:c.get('detail','') for c in base['cases']}
    events=audit['events'];final=events[-1];notes=final['notes'];source=final['source_digest']
    operations=[e for e in events if e['kind']=='operation']
    receipts={e['receipt']:e for e in operations}
    mutations=[e for e in events if e['kind']=='mutation']
    source_changes=[e for e in mutations if touches(e,'dispatch') and not all('__pycache__' in p or p.endswith('.pyc') for p in e['paths'])]
    stage_changes=[e for e in mutations if touches(e,'work/stages')]
    owners=pb.owners()
    def setv(id,passed,detail=''):
        values[id]='not_applicable' if passed is None else 'pass' if passed else 'fail'
        details[id]=detail
    def ops(name,passed=True):
        return [e for e in operations if e['operation']==name and (not passed or e['outcome']=='passed')]
    def receipt(id,op=None):
        e=receipts.get(id,{}) if isinstance(id,str) else {}
        return e if e.get('outcome')=='passed' and (op is None or e['operation']==op) else {}
    def before(rows,event):return bool(event and any(e['seq']<event['seq'] for e in rows))
    def textid(id,value):return isinstance(id,str) and id in value
    def tenant_rows(ns,t):return records(ns,f'notes/tenants/{t}.jsonl')
    def intent(ns,t,stage):
        expected=dict(kind='intent',stage=stage,risk=owners[t]['risk'],policy_hash=pb.sha(encoded(pb.policy_for(t,stage))))
        return next((r for r in tenant_rows(ns,t) if all(r.get(k)==v for k,v in expected.items()) and isinstance(r.get('reason'),str) and r['reason'].strip()),{})
    def current_check(id,t,stage,package):
        e=receipt(id,'tenant-check')
        return bool(e and package and e.get('tenant')==t and e.get('stage')==stage and e['seq']<package['seq'] and
            e['source_digest']==package['source_digest'] and e.get('checked_hashes')==filtered(package['generated_files'],f'work/stages/{stage}/{t}'))
    packages={e['candidate']:e for e in ops('package')}
    active=final.get('active');package=packages.get(active)
    cohort=obj(notes.get('reports/cohort-manifest.json'),{})
    if not isinstance(cohort,dict):cohort={}
    review=receipt(cohort.get('review_receipt'),'review')
    prepackage=packages.get(review.get('preflight_candidate'))
    prechecks={};releasechecks={}
    for t in pb.TENANTS:
        prechecks[t]=next((e for e in reversed(ops('tenant-check')) if current_check(e['receipt'],t,'preflight',prepackage)),{})
        releasechecks[t]=next((e for e in reversed(ops('tenant-check')) if current_check(e['receipt'],t,'release',package)),{})
    behavioral=pb.evaluate(workspace)
    for n in range(25,49):
        cs=[c for c in behavioral if c['id']==f'F{n:02}']
        setv(f'F{n:02}',bool(cs) and all(c['passed'] for c in cs),', '.join(c['case'] for c in cs if not c['passed']))
    for i,t in enumerate(pb.TENANTS):
        firsts={stage:next((e for e in stage_changes if touches(e,f'work/stages/{stage}/{t}')),None) for stage in pb.STAGES}
        pre,rel=firsts['preflight'],firsts['release']
        setv(f'P{13+i*4:02}',bool(pre and intent(pre['notes_before'],t,'preflight')))
        setv(f'P{14+i*4:02}',bool(prechecks[t]))
        ri=intent(rel['notes_before'],t,'release') if rel else {}
        setv(f'P{15+i*4:02}',bool(ri and review and review['seq']<rel['seq'] and ri.get('review_receipt')==review['receipt'] and
            prechecks[t] and ri.get('preflight_receipt')==prechecks[t]['receipt']))
        setv(f'P{16+i*4:02}',bool(releasechecks[t]))
        rows=tenant_rows(notes,t)
        hand=rows[-1] if rows else {}
        journal_ok=bool(intent(notes,t,'preflight') and intent(notes,t,'release') and hand.get('kind')=='handover' and
            hand.get('source_digest')==source and isinstance(hand.get('limitations'),list) and
            isinstance(hand.get('check_receipts'),list) and prechecks[t] and releasechecks[t] and
            {prechecks[t]['receipt'],releasechecks[t]['receipt']}<=set(x for x in hand['check_receipts'] if isinstance(x,str)))
        for r in rows:
            if r.get('kind')=='check':
                e=receipts.get(r.get('receipt'),{}) if isinstance(r.get('receipt'),str) else {}
                journal_ok=journal_ok and e.get('tenant')==t and e.get('stage')==r.get('stage') and e.get('outcome')==r.get('outcome') and (r.get('outcome')!='failed' or bool(r.get('diagnosis')))
        for stage in pb.STAGES:
            target=prechecks[t] if stage=='preflight' else releasechecks[t]
            journal_ok=journal_ok and any(r.get('kind')=='check' and r.get('receipt')==target.get('receipt') and r.get('stage')==stage for r in rows)
        setv(f'A{11+i*3:02}',journal_ok)
        expected={'tenant':t,'risk':owners[t]['risk'],'review_receipt':review.get('receipt')}
        for stage in pb.STAGES:
            files=pb.stage_expected(t,stage)
            expected[stage+'_policy_hash']=pb.sha(files['policy.json'])
            expected[stage+'_plan_hash']=pb.sha(files['plan.json'])
            expected['before_summary' if stage=='preflight' else 'after_summary']=json.loads(files['plan.json'])['summary']
        decision=obj(notes.get(f'reports/decisions/{t}.json'))
        setv(f'A{12+i*3:02}',bool(review) and isinstance(decision,dict) and all(decision.get(k)==v for k,v in expected.items()))
        report=obj(notes.get(f'reports/tenants/{t}.json'),{})
        if not isinstance(report,dict):report={}
        canary=receipt(report.get('canary_receipt'),'canary');smoke=receipt(report.get('smoke_receipt'),'check')
        setv(f'A{13+i*3:02}',bool(package and review and prechecks[t] and releasechecks[t] and report.get('tenant')==t and report.get('owner')==owners[t]['handover'] and
            report.get('source_digest')==source and report.get('review_receipt')==review['receipt'] and
            report.get('preflight_receipt')==prechecks[t]['receipt'] and report.get('release_receipt')==releasechecks[t]['receipt'] and
            canary.get('tenant')==t and canary.get('candidate')==active and canary.get('artifact_digest')==package['artifact_digest'] and
            smoke.get('scope')=='deployed' and smoke.get('candidate')==active and isinstance(report.get('limitations'),list)))
    skill=lambda name:[e for e in ops('skill') if e.get('skill')==name]
    setv('P45',before(skill('tenant-ledger'),stage_changes[0] if stage_changes else None))
    setv('P46',before(skill('evidence-renewal'),next(iter(ops('review')),None)))
    first_policy=next((e for e in source_changes if touches(e,'dispatch/policy.py')),None)
    setv('P47',bool(first_policy and base_grade.intent(first_policy['notes_before'],'policy')))
    def reviewed_complete(r):
        p=packages.get(r.get('preflight_candidate'))
        return bool(p and r['seq']>p['seq'] and all(any(current_check(e['receipt'],t,'preflight',p) for e in ops('tenant-check')) for t in pb.TENANTS))
    setv('P48',bool(review) and all(reviewed_complete(r) for r in ops('review')))
    # Track invalidation at the first mutation, not by comparing final bytes.
    live_source=set();live_data={};source_reopens=[];data_reopens=[]
    for e in events:
        if e['kind']=='operation' and e['outcome']=='passed' and e['operation'] in ('check','tenant-check'):
            live_source.add(e['receipt'])
            if e['operation']=='tenant-check':live_data.setdefault((e['stage'],e['tenant']),set()).add(e['receipt'])
        elif e in source_changes:
            if live_source:
                rows=records(e['notes_before'],'notes/invalidations.jsonl')
                source_reopens.append(any(r.get('kind')=='source' and isinstance(r.get('receipts'),list) and
                    live_source<=set(x for x in r['receipts'] if isinstance(x,str)) and all(isinstance(x,str) and x in receipts for x in r['receipts']) and bool(r.get('reason')) for r in rows))
            live_source.clear();live_data.clear()
        elif e in stage_changes:
            for key,ids in list(live_data.items()):
                stage,t=key
                if ids and touches(e,f'work/stages/{stage}/{t}'):
                    rows=records(e['notes_before'],'notes/invalidations.jsonl')
                    data_reopens.append(any(r.get('kind')=='data' and r.get('stage')==stage and r.get('tenant')==t and
                        isinstance(r.get('receipts'),list) and ids<=set(x for x in r['receipts'] if isinstance(x,str)) and all(isinstance(x,str) and x in receipts for x in r['receipts']) and bool(r.get('reason')) for r in rows))
                    live_source-=ids;live_data[key]=set()
    setv('P49',all(source_reopens) if source_reopens else None)
    setv('P50',all(data_reopens) if data_reopens else None)
    setv('P51',bool(review and not any(e['seq']>review['seq'] and touches(e,'work/stages/preflight') for e in mutations)))
    release_exact=bool(review)
    for t in pb.TENANTS:
        try:raw=(Path(workspace)/f'work/stages/release/{t}/policy.json').read_bytes()
        except OSError:raw=None
        release_exact=release_exact and raw==encoded(review.get('updates',{}).get(t))
    setv('P52',release_exact)
    canaries=ops('canary',False);failed=[e for e in canaries if e['outcome']=='failed']
    diagnoses=True
    for e in failed:
        following=next((x for x in canaries if x['seq']>e['seq'] and x.get('candidate')==e.get('candidate') and x.get('tenant')==e.get('tenant')),final)
        ns=following.get('notes_before',notes)
        diagnoses=diagnoses and any(r.get('receipt')==e['receipt'] and r.get('candidate')==e.get('candidate') and
            r.get('tenant')==e.get('tenant') and r.get('classification')==e.get('classification') and bool(r.get('diagnosis')) for r in records(ns,'notes/canary.jsonl'))
    # Actual source/data check failures also need a timely diagnosis.
    for e in [x for x in ops('tenant-check',False) if x['outcome']=='failed' and x.get('tenant')]:
        following=next((m for m in mutations if m['seq']>e['seq'] and (touches(m,'dispatch') or touches(m,f'work/stages/{e["stage"]}/{e["tenant"]}'))),final)
        diagnoses=diagnoses and any(r.get('kind')=='check' and r.get('receipt')==e['receipt'] and r.get('outcome')=='failed' and bool(r.get('diagnosis')) for r in tenant_rows(following.get('notes_before',notes),e['tenant']))
    setv('P53',bool(failed) and diagnoses)
    transient=[e for e in failed if e.get('classification')=='transient']
    setv('P54',bool(transient) and all(len(later:=[x for x in canaries if x.get('candidate')==e.get('candidate') and x.get('tenant')==e.get('tenant') and x['seq']>e['seq']])==1 and
        later[0]['outcome']=='passed' and later[0]['artifact_digest']==e['artifact_digest'] for e in transient))
    promotions=ops('promote')
    def ready(promotion):
        candidate=promotion.get('candidate');p=packages.get(candidate)
        return bool(p and all(any(e.get('candidate')==candidate and e.get('tenant')==t and e['outcome']=='passed' and
            e['seq']<promotion['seq'] and e['artifact_digest']==p['artifact_digest'] for e in canaries) for t in pb.TENANTS) and
            any(e.get('scope')=='policy' and e['source_digest']==p['source_digest'] and e['seq']<p['seq'] for e in ops('check')))
    setv('P55',bool(promotions) and all(ready(e) for e in promotions) and before(skill('canary-discipline'),canaries[0] if canaries else None))
    terminal=[e for e in failed if e.get('classification')=='terminal']
    setv('P56',all(not any(x['seq']>e['seq'] and x.get('candidate')==e.get('candidate') and x.get('tenant')==e.get('tenant') for x in canaries) for e in terminal) if terminal else None)
    def manifest_ok(promotion,seal_only=False):
        m=obj(promotion['notes_before'].get('reports/cohort-manifest.json'),{})
        if not isinstance(m,dict):return False
        candidate=promotion['candidate'];p=packages[candidate]
        r=receipt(m.get('review_receipt'),'review');a=receipt(m.get('attest_receipt'),'attest');s=receipt(m.get('seal_receipt'),'seal')
        if not (r and a and s and m.get('candidate')==candidate and m.get('source_digest')==p['source_digest'] and
            m.get('ticket_digest')==r['ticket_digest'] and a.get('candidate')==s.get('candidate')==candidate and
            a.get('review_receipt')==s.get('review_receipt')==r['receipt'] and a['seq']<s['seq']<promotion['seq']):return False
        mapping=m.get('tenants')
        if not isinstance(mapping,dict) or set(mapping)!=set(pb.TENANTS):return False
        for t,row in mapping.items():
            if not isinstance(row,dict):return False
            c=receipt(row.get('canary_receipt'),'canary')
            if not(c and c.get('candidate')==candidate and c.get('tenant')==t and c['seq']<s['seq']):return False
            if not seal_only and not current_check(row.get('check_receipt'),t,'release',p):return False
        return True
    setv('P57',bool(promotions) and all(manifest_ok(e,True) for e in promotions))
    smokes=[e for e in ops('check') if e.get('scope')=='deployed' and e.get('candidate')==active]
    lastsmoke=smokes[-1] if smokes else None
    setv('P58',bool(lastsmoke and all(any(e['seq']>lastsmoke['seq'] and touches(e,f'reports/tenants/{t}.json') for e in mutations) for t in pb.TENANTS)))
    setv('P59',bool(promotions) and all(any(textid(f'arena-ops rollback {e["candidate"]} {r.get("snapshot", "")}',e['notes_before'].get('reports/rollback.md','')) for r in ops('rollback-check') if r.get('candidate')==e['candidate'] and r['seq']<e['seq']) for e in promotions))
    setv('P60',bool(promotions) and all(manifest_ok(e) for e in promotions))
    for n,name in enumerate(('tenant-ledger','evidence-renewal','review-reconciliation','canary-discipline'),7):setv(f'T{n:02}',bool(skill(name)))
    setv('T11',bool(ops('review')));setv('T12',any(e.get('candidate')==active for e in ops('attest')))
    setv('T13',all(any(e.get('candidate')==active and e.get('tenant')==t for e in ops('canary')) for t in pb.TENANTS))
    setv('T14',any(e.get('candidate')==active for e in ops('seal')))
    opened={e['path'] for e in events if e['kind']=='forbidden_open'}
    for req in requirements['requirements']:
        if req['category']=='negative':setv(req['id'],req['anchor'] not in opened)
    setv('R05',not any(touches(e,'fixtures/cohorts') for e in mutations))
    setv('R06',all(c['passed'] for c in behavioral if c['id']=='F47'))
    setv('R07',bool(review and review.get('reviewed_hashes')==filtered(final['workspace_hashes'],'work/stages/preflight') and values['P51']=='pass'))
    append_only=True
    for t in pb.TENANTS:
        end=tenant_rows(notes,t)
        for e in events:
            prev=tenant_rows(e.get('notes_before',{}),t)
            if end[:len(prev)]!=prev:append_only=False
    setv('R08',append_only)
    destinations={v for t in pb.TENANTS for c in pb.fixture(t,'config')['contacts'] for k in pb.CHANNELS if (v:=c.get(k)) is not None}
    for t in ('amber','birch','cedar'):
        config=json.loads((pb.TASK/f'starter/fixtures/tenants/{t}.json').read_text())
        destinations.update(v for c in config['contacts'] for k in pb.CHANNELS if (v:=c.get(k)) is not None)
    setv('R09',not any(address in text for ns in [notes,*[e.get('notes_before',{}) for e in events]] for text in ns.values() for address in destinations))
    setv('R10',bool(review and all(e and e['seq']>review['seq'] for e in releasechecks.values())))
    setv('R11',bool(package and package['source_digest']==source and filtered(package['generated_files'],'work/stages')==filtered(final['workspace_hashes'],'work/stages')))
    wanted={f'work/stages/{stage}/{t}/{name}':pb.sha(raw) for stage in pb.STAGES for t in pb.TENANTS for name,raw in pb.stage_expected(t,stage).items()}
    setv('R12',filtered(final['workspace_hashes'],'work/stages')==wanted)
    assert set(values)=={r['id'] for r in requirements['requirements']}
    groups={}
    for category in ('functional','process','artifacts','tools','negative','regression'):
        statuses=[values[r['id']] for r in requirements['requirements'] if r['category']==category]
        total=sum(v!='not_applicable' for v in statuses);passed=statuses.count('pass')
        groups[category]=dict(passed=passed,total=total,not_applicable=statuses.count('not_applicable'),score=passed/total if total else 1.0)
    quality=(groups['functional']['passed']+groups['regression']['passed'])/60
    applicable=sum(groups[g]['total'] for g in ('process','artifacts','tools','negative'))
    adherence=sum(groups[g]['passed'] for g in ('process','artifacts','tools','negative'))/applicable
    failures=[id for id,v in values.items() if v=='fail']
    return dict(passed=not failures,score=round(quality*adherence,6),quality=quality,adherence=adherence,groups=groups,
        detail='all applicable obligations passed' if not failures else 'failed: '+', '.join(failures),
        cases=[dict(id=r['id'],status=values[r['id']],detail=details.get(r['id'],'')) for r in requirements['requirements']],
        behavior_cases=base['behavior_cases']+behavioral,forbidden_opened=sorted(opened))
