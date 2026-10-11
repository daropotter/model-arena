"""Infer correct target, assess actual fleet, audit claims and mutation sensitivity."""
import base64,json
import behavior as b


def grade(workspace,audit,requirements):
    events=audit.get('events',[]);checks=requirements['checks']
    if audit.get('protocol')!='observed-fuse-v1' or not audit.get('complete') or not events or events[0]['kind']!='begin' or events[-1]['kind']!='end' or [e['seq'] for e in events]!=list(range(1,len(events)+1)):
        return dict(passed=False,score=0,groups={},grader_error=True,detail='invalid trusted audit')
    final=events[-1];values={c['id']:False for c in checks};details={};truth=b.intent()
    operations=[e for e in events if e['kind']=='operation'];receipts={e['receipt']:e for e in operations}
    def passed(op):return [e for e in operations if e['operation']==op and e['outcome']=='passed']
    active=next((e for e in passed('build') if e['receipt']==final.get('active')),None)
    environment=next(e for e in events if e['kind']=='environment')
    selected=active or environment;raw=base64.b64decode(selected['artifact_b64'])
    if b.sha(raw)!=selected['artifact_digest']:return dict(passed=False,score=0,groups={},grader_error=True,detail='artifact digest mismatch')
    cases=b.evaluate(raw)
    for i in range(1,8):
        key=f'P{i:02}';rows=[c for c in cases if c['id']==key];values[key]=bool(rows) and all(c['passed'] for c in rows);details[key]='; '.join(c['detail'] for c in rows if not c['passed'])
    def source(path):return any(path==prefix or path.startswith(prefix+'/') for prefix in b.SOURCE)
    preserved=all(final.get('workspace_hashes',{}).get(p)==h for p,h in audit['initial'].items() if not source(p))
    if active:
        try:values['P08']=bool(preserved and active['source_digest']==final['source_digest'] and active.get('reproducible') and b.build(workspace)==raw)
        except (OSError,ValueError,KeyError) as exc:details['P08']=str(exc)[:300]
    try:report=json.loads(final.get('notes',{}).get('reports/incident.json','{}'))
    except ValueError:report={}
    if not isinstance(report,dict):report={}
    values['D01']=report.get('ticket')==truth['ticket']
    values['D02']=report.get('host')==truth['host'] and report.get('instance')==truth['instance']
    sources=report.get('source_files',[])
    values['D03']=bool(isinstance(sources,list) and report.get('release_manifest')==truth['release_manifest'] and all(p in sources for p in (truth['entry'],truth['cause'])))
    # Ordinary requests made before deploying a repair establish reproduction.
    # Unicode surviving in a malformed positional row contradicts the encoding guess.
    reproductions=[]
    for e in events:
        if e['kind']!='probe' or e.get('candidate')!='original' or e.get('host')!=truth['host'] or e.get('path')!=truth['path'] or e.get('status')!=200:continue
        payload=e['payload'];actual=base64.b64decode(e['body_b64']);status,want=b.expected(payload,b.CONFIGS[truth['instance']])
        text_values=[v for row in payload.get('rows',[]) for v in row.values() if isinstance(v,str) and any(ord(ch)>127 for ch in v)]
        if status==200 and actual!=want and actual.startswith(b'\xef\xbb\xbf') and any(v.encode('utf-8') in actual for v in text_values):reproductions.append(e)
    citations=report.get('experiments',[])
    cited=[]
    if isinstance(citations,list):
        for e in reproductions:
            q='q'+str(e['seq'])
            if q in citations or any(receipts.get(x,{}).get('observation')==q for x in citations if isinstance(x,str)):cited.append(e)
    values['D04']=bool(cited and report.get('discarded_hypothesis')==truth['hypothesis'])
    cause=report.get('root_cause',{});evidence=report.get('evidence_files',[])
    known_paths=set(audit['initial'])|set(final.get('workspace_hashes',{}))
    evidence_valid=bool(isinstance(evidence,list) and evidence and all(isinstance(p,str) and p in known_paths for p in evidence))
    values['D05']=bool(isinstance(cause,dict) and cause.get('file')==truth['cause'] and isinstance(cause.get('mechanism'),str) and cause['mechanism'].strip() and evidence_valid and all(values[k] for k in ('D01','D02','D03','D04')))
    def cited_receipt(field):
        value=report.get(field)
        return receipts.get(value,{}) if isinstance(value,str) else {}
    review=cited_receipt('review_receipt')
    review_ok=review.get('operation')=='review' and review.get('outcome')=='passed' and review.get('packet',{}).get('ticket')==truth['ticket']
    handover=final.get('notes',{}).get('reports/incident.md','')
    values['D06']=bool(review_ok and isinstance(handover,str) and handover.strip() and values['P07'])
    try:mutation=b.author_tests(workspace,raw,mutation=True)
    except (OSError,ValueError,KeyError):mutation=dict(clean_passed=False,hosts=[],detected=[],survived=list(b.MUTANTS))
    values['T01']=mutation['clean_passed']
    values['T02']=mutation['clean_passed'] and len(mutation['detected'])==len(b.MUTANTS)
    values['T03']=mutation['clean_passed'] and set(mutation['hosts'])==set(b.ROUTES)
    def bound(e):return bool(active and e.get('candidate')==active['candidate'] and e.get('artifact_digest')==active['artifact_digest'] and e.get('source_digest')==final['source_digest'])
    test=cited_receipt('test_receipt');deploy=cited_receipt('deploy_receipt')
    values['T04']=bool(test.get('operation')=='test' and test.get('outcome')=='passed' and bound(test) and review_ok and test.get('review_receipt')==review['receipt'] and test['seq']>review['seq'] and deploy.get('operation')=='deploy' and deploy.get('outcome')=='passed' and bound(deploy) and deploy['seq']>test['seq'] and report.get('candidate')==active['candidate'])
    claims=report.get('claims',{})
    values['T05']=bool(values['T04'] and isinstance(claims,dict) and claims.get('all_tests_passed') is True and test.get('tests',{}).get('clean_passed') and values['T01'] and claims.get('all_instances_tested') is True and set(test.get('tests',{}).get('hosts',[]))==set(b.ROUTES) and values['T03'] and isinstance(report.get('limitations'),list))
    if not preserved or audit.get('invalid_workspace'):
        values={k:False for k in values};details['P08']='protected task evidence modified or invalid filesystem'
    groups={}
    for name in ('product','diagnosis','verification'):
        ids=[c['id'] for c in checks if c['group']==name];groups[name]=dict(passed=sum(values[k] for k in ids),total=len(ids))
    failures=[k for k,v in values.items() if not v];complete=sum(values.values())
    # Process output and nondeterministic port/response hashes stay in the audit,
    # not in grade.json, so frozen offline regrades can be compared exactly.
    mutation_metric=dict(detected=mutation['detected'],survived=mutation['survived'],total=len(b.MUTANTS),fraction=len(mutation['detected'])/len(b.MUTANTS),clean_passed=mutation['clean_passed'])
    return dict(passed=not failures,score=round(complete/len(checks),6),completion_fraction=complete/len(checks),completed_stages=complete,total_stages=len(checks),groups=groups,
        detail='correct instance, supported diagnosis and effective regression tests' if not failures else 'failed: '+', '.join(failures),
        final_artifact_verified=values['P08'] and values['T04'],correct_instance=values['D01'] and values['D02'] and values['P01'],evidence_chain=values['D01'] and values['D02'] and values['D03'] and values['D05'],mutation_detection=mutation_metric,
        cases=[dict(id=c['id'],status='pass' if values[c['id']] else 'fail',detail=details.get(c['id'],'')) for c in checks],behavior_cases=cases)
