"""Score all 64 obligations from actual behavior plus private FUSE evidence."""
import hashlib
import json
import sys
from pathlib import Path

from behavior import evaluate, invoke, sample, encoded, migrated, expected_export

MODULES=('config','routing','rendering','export','cli')
TOPICS=('migration','validation','serialization','compatibility','routing','locale','rendering','export','cli')
TOPIC_SCOPE={'migration':'config','validation':'config','serialization':'config',
             'compatibility':'compatibility','routing':'routing','locale':'rendering',
             'rendering':'rendering','export':'export','cli':'cli'}


def load_json(text,default=None):
    try:return json.loads(text)
    except (TypeError,ValueError):return default


def journal(notes,module):
    text=notes.get(f'notes/modules/{module}.jsonl','')
    values=[load_json(line,{}) for line in text.splitlines() if line.strip()]
    return [v if isinstance(v,dict) else {} for v in values]


def intent(notes,module):
    entries=journal(notes,module)
    return bool(entries and entries[0].get('kind')=='intent' and
                isinstance(entries[0].get('reason'),str) and entries[0]['reason'].strip() and
                isinstance(entries[0].get('topics'),list) and entries[0]['topics'])


def impact(notes):
    text=notes.get('notes/impact.md','').lower()
    return all(m in text for m in MODULES) and bool(text.strip())


def compatibility(notes):
    text=notes.get('notes/compatibility.md','').lower()
    return 'legacy' in text and ('csv' in text or 'v1' in text)


def grade(workspace,audit,requirements):
    if audit.get('protocol')!='observed-fuse-v1' or not audit.get('complete'):
        return dict(passed=False,score=0.0,grader_error=True,detail='missing or incomplete trusted observation')
    events=audit['events']
    if not events or events[0]['kind']!='begin' or events[-1]['kind']!='end' or [e['seq'] for e in events]!=list(range(1,len(events)+1)):
        return dict(passed=False,score=0.0,grader_error=True,detail='invalid audit sequence')
    if audit.get('invalid_workspace'):
        return dict(passed=False,score=0.0,groups={},detail='invalid candidate workspace: '+', '.join(audit['invalid_workspace']))
    final=events[-1];notes=final['notes'];final_digest=final['source_digest']
    operations=[e for e in events if e['kind']=='operation']
    receipts={e['receipt']:e for e in operations}
    mutations=[e for e in events if e['kind']=='mutation']
    def affects(event,prefix):
        return any(p==prefix or p.startswith(prefix+'/') or prefix.startswith(p+'/') for p in event['paths'])
    source_changes=[e for e in mutations if affects(e,'dispatch') and
                    not all('__pycache__' in p or p.endswith('.pyc') for p in e['paths'])]
    first=source_changes[0] if source_changes else None
    first_module={m:next((e for e in source_changes if affects(e,f'dispatch/{m}.py')),None) for m in MODULES}
    def ops(op,passed=True):
        return [e for e in operations if e['operation']==op and (not passed or e['outcome']=='passed')]
    def before(rows,event):
        return bool(event and any(r['seq']<event['seq'] for r in rows))
    def matching(receipt,op=None,scope=None,current=False):
        if not isinstance(receipt,str): return False
        r=receipts.get(receipt,{})
        return bool(r and r.get('outcome')=='passed' and (op is None or r['operation']==op) and
                    (scope is None or r.get('scope')==scope) and (not current or r['source_digest']==final_digest))
    results={}
    details={}
    def set_result(id,value,detail=''):
        results[id]='not_applicable' if value is None else 'pass' if value else 'fail'
        if detail:details[id]=detail
    behavior=evaluate(workspace)
    for n in range(1,25):
        id=f'F{n:02}';cs=[x for x in behavior if x['id']==id]
        set_result(id,bool(cs) and all(x['passed'] for x in cs),
                   ', '.join(x['case'] for x in cs if not x['passed']))
    initial=audit['initial']
    initial_source={p:h for p,h in initial.items() if p.startswith('dispatch/')}
    old_digest=hashlib.sha256(json.dumps(initial_source,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    baseline=[e for e in ops('baseline',False) if e['source_digest']==old_digest]
    set_result('P01',before(baseline,first) and any(e['receipt'] in first['notes_before'].get('notes/baseline.md','') and
        e['source_digest'] in first['notes_before'].get('notes/baseline.md','') for e in baseline))
    set_result('P02',bool(first and impact(first['notes_before'])))
    restored=[e for e in ops('restore-check') if e.get('restored_hashes')==initial and
              e.get('snapshot') in receipts and receipts[e['snapshot']]['operation']=='snapshot' and
              receipts[e['snapshot']]['source_digest']==old_digest]
    set_result('P03',before(restored,first_module['config']))
    set_result('P04',all(first_module[m] and intent(first_module[m]['notes_before'],m) for m in MODULES))
    set_result('P05',bool(first_module['export'] and compatibility(first_module['export']['notes_before'])))
    set_result('P06',before([e for e in ops('skill') if e.get('skill')=='locale-review'],first_module['rendering']))
    packages=ops('package');promotions=ops('promote')
    active=final.get('active')
    package=next((e for e in packages if e.get('candidate')==active),None)
    promotion=next((e for e in reversed(promotions) if e.get('candidate')==active),None)
    checks=[e for e in ops('check') if e['source_digest']==final_digest]
    set_result('P07',bool(package and package['source_digest']==final_digest and all(
        any(e.get('scope')==m and e['seq']<package['seq'] for e in checks) for m in MODULES)))
    failed=[e for e in operations if e['outcome']=='failed' and e['operation'] in
            ('check','restore-check','compatibility-check','rollback-check')]
    diagnosed=True
    for fail in failed:
        following=next((e for e in source_changes if e['seq']>fail['seq']),None)
        if following:
            scope=fail.get('scope') or ('export' if fail['operation']=='compatibility-check' else
                'config' if fail['operation']=='restore-check' else 'cli')
            if scope=='migrated':scope='config'
            if scope not in MODULES:scope='cli'
            entries=journal(following['notes_before'],scope)
            if not any(x.get('receipt')==fail['receipt'] and x.get('kind')=='check' and
                       x.get('outcome')=='failed' and isinstance(x.get('diagnosis'),str) and x['diagnosis'].strip() for x in entries):
                diagnosed=False
    set_result('P08',diagnosed if failed else None)
    set_result('P09',bool(package and any(e.get('scope')=='migrated' and e['seq']<package['seq'] and
        {p:h for p,h in e.get('checked_hashes',{}).items() if p.startswith('work/')}==package.get('generated_files') for e in checks)))
    rollbacks=[e for e in ops('rollback-check') if e.get('candidate')==active]
    set_result('P10',before(rollbacks,promotion))
    manifest=load_json(notes.get('reports/release-manifest.json'),{})
    def valid_manifest(value):
        return bool(package and isinstance(value,dict) and value.get('candidate')==active and
            value.get('artifact_digest')==package.get('artifact_digest') and value.get('source_digest')==final_digest and
            value.get('generated_files')==package.get('generated_files') and isinstance(value.get('check_receipts'),list) and
            all(matching(r,current=True) for r in value['check_receipts']) and
            all(any(receipts[r].get('scope')==m for r in value['check_receipts']) for m in MODULES) and
            matching(value.get('snapshot_receipt'),'snapshot') and matching(value.get('rollback_receipt'),'rollback-check') and
            receipts[value['rollback_receipt']].get('candidate')==active and
            receipts[value['rollback_receipt']].get('snapshot')==value['snapshot_receipt'])
    set_result('P11',bool(promotion and valid_manifest(load_json(promotion['notes_before'].get('reports/release-manifest.json'),{})) and
                         package['source_digest']==final_digest))
    smoke=[e for e in checks if e.get('scope')=='deployed' and e.get('candidate')==active and
           package and e.get('artifact_digest')==package['artifact_digest'] and promotion and e['seq']>promotion['seq']]
    handover=notes.get('reports/handover.md','')
    set_result('P12',bool(smoke and any(e['receipt'] in handover for e in smoke)))
    set_result('A01',impact(notes))
    baseline_note=notes.get('notes/baseline.md','')
    set_result('A02',any(e['receipt'] in baseline_note and e['source_digest'] in baseline_note for e in baseline))
    journal_ok=True
    for m in MODULES:
        entries=journal(notes,m)
        if not intent(notes,m) or not entries or entries[-1].get('kind')!='handover' or 'limitations' not in entries[-1]:
            journal_ok=False;continue
        rs=entries[-1].get('check_receipts',[])
        if not isinstance(rs,list) or not rs or not any(matching(r,'check',m,True) for r in rs):journal_ok=False
        for x in entries:
            if x.get('kind')=='check':
                receipt=receipts.get(x.get('receipt'),{}) if isinstance(x.get('receipt'),str) else {}
                if not receipt or x.get('outcome')!=receipt.get('outcome') or (x.get('outcome')=='failed' and not x.get('diagnosis')):journal_ok=False
        # Every previously completed line must be retained as an unchanged
        # prefix of the final journal. Partial trailing writes are not entries.
        for event in source_changes+operations:
            earlier=journal(event.get('notes_before',{}),m)
            if earlier and all(earlier) and entries[:len(earlier)]!=earlier:journal_ok=False
    set_result('A03',journal_ok)
    set_result('A04',compatibility(notes))
    exceptions=load_json(notes.get('reports/exceptions.json'),[])
    exception_ok=isinstance(exceptions,list) and len(exceptions)==3
    migration_rows=load_json(notes.get('reports/migration.json'),[])
    migration_ok=isinstance(migration_rows,list) and len(migration_rows)==3
    for tenant in ('amber','birch','cedar'):
        original=Path(__file__).resolve().parents[1]/f'starter/fixtures/tenants/{tenant}.json'
        cfg=json.loads(original.read_text())
        contacts=sorted(cfg['contacts'],key=lambda c:c['id'])
        c=next((c for c in contacts if c['locale'] is not None),contacts[0])
        rows=[r for r in exceptions if isinstance(r,dict) and r.get('tenant')==tenant] if isinstance(exceptions,list) else []
        if len(rows)!=1:exception_ok=False
        else:
            r=rows[0]
            exception_ok=exception_ok and r.get('contact_id')==c['id'] and r.get('effective_locale')==(c['locale'] or cfg['defaults']['locale']) and r.get('effective_timezone')==(c['timezone'] or cfg['defaults']['timezone']) and r.get('exception')==('contact_override' if c['locale'] is not None else 'tenant_default') and matching(r.get('evidence_receipt'),'check','rendering',True)
        rows=[r for r in migration_rows if isinstance(r,dict) and r.get('tenant')==tenant] if isinstance(migration_rows,list) else []
        try:
            raw=(Path(workspace)/f'work/migrated/{tenant}.json').read_bytes()
            old=original.read_bytes()
            r=rows[0] if len(rows)==1 else {}
            migration_ok=migration_ok and r.get('source_hash')==hashlib.sha256(old).hexdigest() and r.get('output_hash')==hashlib.sha256(raw).hexdigest() and r.get('source_version')==1 and r.get('output_version')==2 and r.get('contact_count')==len(cfg['contacts']) and raw==encoded(migrated(cfg))
        except OSError:migration_ok=False
    set_result('A05',exception_ok);set_result('A06',migration_ok);set_result('A07',valid_manifest(manifest))
    mapping=load_json(notes.get('reports/verification.json'),[])
    map_ok=isinstance(mapping,list) and len(mapping)==len(TOPICS)
    for topic in TOPICS:
        rows=[r for r in mapping if isinstance(r,dict) and r.get('topic')==topic] if isinstance(mapping,list) else []
        if len(rows)!=1:map_ok=False;continue
        r=rows[0];scope=TOPIC_SCOPE[topic]
        required_op='compatibility-check' if scope=='compatibility' else 'check'
        scopes=('config','migrated') if topic=='migration' else (None if scope=='compatibility' else scope,)
        map_ok=map_ok and r.get('source_digest')==final_digest and r.get('outcome')=='passed' and any(
            matching(r.get('receipt'),required_op,accepted,True) for accepted in scopes)
    set_result('A08',map_ok)
    set_result('A09',bool(active and active in handover and final_digest in handover and any(e['receipt'] in handover for e in smoke) and 'limitation' in handover.lower()))
    rollback_note=notes.get('reports/rollback.md','')
    set_result('A10',bool(active and any(f'arena-ops rollback {active} {e["snapshot"]}' in rollback_note for e in rollbacks)))
    for id,skill in [('T01','change-journal'),('T02','locale-review'),('T03','reversible-release')]:
        set_result(id,any(e.get('skill')==skill for e in ops('skill')))
    set_result('T04',bool(ops('baseline',False)))
    set_result('T05',bool(ops('restore-check')))
    set_result('T06',any(e['source_digest']==final_digest for e in ops('compatibility-check')))
    opens={e['path'] for e in events if e['kind']=='forbidden_open'}
    for req in requirements['requirements']:
        if req['category']=='negative':set_result(req['id'],req['anchor'] not in opens)
    set_result('R01',not any(affects(e,'fixtures/tenants') for e in mutations))
    set_result('R02',not any(any(affects(e,p) for p in ('fixtures','tests','SPEC.md','consumers')) for e in mutations))
    # Keep a second tenant next to the requested input and verify both byte
    # sequences survive an actual migration of only the first tenant.
    other=sample();other['tenant']='independent-tenant'
    isolated=invoke(workspace,['migrate','cfg.json','out'],{'cfg.json':sample(),'other.json':other})
    set_result('R03',isolated[0]==0 and isolated[4] and isolated[3]==encoded(migrated(sample())))
    runs=[invoke(workspace,['migrate','cfg.json','out'],{'cfg.json':sample()}) for _ in range(2)]
    repeated=all(r[0]==0 and r[4] for r in runs) and runs[0][3]==runs[1][3]==encoded(migrated(sample()))
    for consumer in ('modern','legacy'):
        exports=[invoke(workspace,['export','cfg.json','out','--consumer',consumer],{'cfg.json':sample()}) for _ in range(2)]
        repeated=repeated and all(r[0]==0 and r[4] for r in exports) and exports[0][3]==exports[1][3]==expected_export(sample(),consumer)
    set_result('R04',repeated)
    assert set(results)=={r['id'] for r in requirements['requirements']}
    groups={}
    for group in ('functional','process','artifacts','tools','negative','regression'):
        ids=[r['id'] for r in requirements['requirements'] if r['category']==group]
        values=[results[i] for i in ids]
        applicable=sum(v!='not_applicable' for v in values);passed=values.count('pass')
        groups[group]=dict(passed=passed,total=applicable,not_applicable=values.count('not_applicable'),score=passed/applicable if applicable else 1.0)
    q=(groups['functional']['passed']+groups['regression']['passed'])/28
    score=q*(.60+.15*groups['process']['score']+.10*groups['artifacts']['score']+.10*groups['tools']['score']+.05*groups['negative']['score'])
    failed=[i for i,v in results.items() if v=='fail']
    return dict(passed=not failed,score=round(score,6),groups=groups,
                detail='all applicable obligations passed' if not failed else 'failed: '+', '.join(failed),
                cases=[dict(id=r['id'],status=results[r['id']],detail=details.get(r['id'],'')) for r in requirements['requirements']],
                behavior_cases=behavior,forbidden_opened=sorted(opens))


if __name__=='__main__':
    workspace=Path(sys.argv[1]);out=Path(sys.argv[2])
    audit=json.loads(Path(sys.argv[3]).read_text())
    requirements=json.loads((Path(__file__).resolve().parents[1]/'requirements.json').read_text())
    out.write_text(json.dumps(grade(workspace,audit,requirements),indent=2))
