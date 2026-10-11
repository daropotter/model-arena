"""Trusted scoring against the frozen private oracle, never candidate code."""
import importlib.util
import json
import re
from collections import Counter,defaultdict
from pathlib import Path

TASK=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dossier_format',TASK/'starter/table_format.py')
fmt=importlib.util.module_from_spec(spec);spec.loader.exec_module(fmt)
WEIGHTS={'Legal entity':.10,'State':.10,'Rule':.25,'Exception':.10,'Since':.10,'Basis':.10}


def safe_read(root,relative,limit=24_000_000):
    current=Path(root)
    for part in Path(relative).parts:
        current=current/part
        if current.is_symlink():raise ValueError('symlink output')
    if not current.is_file() or current.stat().st_size>limit:raise ValueError('missing or oversized output')
    return current.read_text()


def evaluate(text,oracle):
    rows,errors=fmt.parse(text);by_key=defaultdict(list)
    for row in rows:by_key[fmt.key(row)].append(row)
    expected={fmt.key(item['answer']):item for item in oracle['rows']}
    count=len(expected);den=max(1,count);found=0;weighted=0.;exact=0;decision=0;entity_wrong=0;stale=0;unsupported=0;unnecessary_unknown=0
    evidence_total=0.;citation_valid=0;citation_count=0;bound_total=0;unresolved_total=0;missing=0
    family=defaultdict(lambda:dict(total=0,correct=0));failures=[]
    for k,item in expected.items():
        target=item['answer'];group=family[item['family']];group['total']+=1
        candidates=by_key.get(k,[])
        if len(candidates)!=1:
            missing+=1
            if len(failures)<100:failures.append({'scope':list(k),'error':'missing or duplicate'})
            continue
        row=candidates[0];found+=1;value=.05
        comparisons={field:row[field]==target[field] for field in WEIGHTS}
        # The public vocabulary includes broad descriptions as well as more
        # specific ones. A true general basis must not be rejected solely for
        # omitting the author's preferred taxonomy label. All substantive
        # fields and every supporting evidence role remain independently due.
        if target['State']=='bound':
            if row['Basis']=='baseline-controls' and target['Rule']==item['initial_rule']:
                comparisons['Basis']=True
            if row['Basis']=='executed-change' and target['Rule']!=item['initial_rule']:
                comparisons['Basis']=True
            if item['family']=='conflict' and item['polarity'] and row['Basis']=='specific-prevails':
                comparisons['Basis']=True
            if item['family']=='missing-schedule' and item['polarity'] and row['Basis']=='incorporated-term':
                comparisons['Basis']=True
        for field,weight in WEIGHTS.items():value+=weight*comparisons[field]
        refs=fmt.citations(row);citation_count+=len(refs)
        allowed=set(item['allowed_evidence']);good=set(refs)&allowed
        citation_valid+=sum(ref in allowed for ref in refs)
        complete_fields=all(comparisons.values())
        groups=[list(g) for g in item['evidence_groups']]
        # Identity is also expressly stated in the executed master. For a
        # novation the change instrument names the successor, and the other
        # mandatory groups establish its execution. One paragraph can support
        # more than one evidentiary role; a separate registry citation is not
        # intrinsically necessary to identify the correct legal entity.
        identity_role=1 if target['Legal entity']==item['initial_entity'] else 3
        groups[0]=list(set(groups[0]+groups[identity_role]))
        coverage=sum(bool(set(g)&set(refs)) for g in groups)/len(groups)
        precision=len(good)/max(1,len(refs))
        valid_refs=2<=len(refs)<=12 and len(refs)==len(set(refs))
        proof=coverage*precision if valid_refs and complete_fields else 0.
        evidence_total+=proof;value+=.20*proof;weighted+=value
        decision_fields=('State','Rule','Exception','Since','Basis')
        correct=all(comparisons[f] for f in decision_fields)
        decision+=correct;entity_wrong+=not comparisons['Legal entity']
        if row['State']=='bound':
            bound_total+=1
            unsupported+=not (complete_fields and proof==1)
        elif row['State']=='unresolved':unresolved_total+=1
        unnecessary_unknown+=row['State']=='unresolved' and target['State']=='bound'
        stale+=row['Rule']==item['initial_rule'] and target['Rule'] not in (item['initial_rule'],'?')
        ok=complete_fields and proof==1
        exact+=ok;group['correct']+=ok
        if not ok and len(failures)<100:
            failures.append({'scope':list(k),'fields':[f for f,ok in comparisons.items() if not ok],'evidence_fraction':round(proof,4)})
    extras=sum(len(v) for k,v in by_key.items() if k not in expected)
    duplicates=sum(max(0,len(v)-1) for v in by_key.values())
    # Extra invented scopes cannot increase recall or be offset by repetition.
    penalty=(extras+duplicates)/den*.5
    score=max(0.,min(1.,weighted/den-penalty))
    if errors:score=min(score,.5)
    metrics=dict(completeness=found/den,resolution_accuracy=decision/den,evidence_accuracy=evidence_total/den,
        citation_precision=citation_valid/max(1,citation_count),entity_error_rate=entity_wrong/den,
        stale_rule_rate=stale/den,unsupported_claim_rate=unsupported/max(1,bound_total),
        unnecessary_unknown_rate=unnecessary_unknown/den,exact_rows=exact,total_rows=count,
        invented_rows=extras,duplicate_rows=duplicates,unresolved_predictions=unresolved_total,
        missing_rows=missing,family_accuracy={k:dict(v,accuracy=v['correct']/v['total']) for k,v in sorted(family.items())})
    conditions={'C01':found==count and not extras and not duplicates,'C02':decision==count,
        'C03':evidence_total==count,'C04':entity_wrong==0 and found==count,
        'C05':stale==0 and found==count,'C06':unsupported==0 and found==count,
        'C07':unnecessary_unknown==0 and found==count,'C08':not errors}
    return dict(score=round(score,6),passed=all(conditions.values()),conditions=conditions,metrics=metrics,errors=errors,failures=failures)


def grade(workspace,audit,requirements):
    oracle=json.loads((TASK/'assets/oracle.json').read_text())
    try:text=safe_read(workspace,'answer/obligations.md')
    except (OSError,ValueError,UnicodeError):text=''
    result=evaluate(text,oracle)
    manifest=json.loads((TASK/'assets/manifest.json').read_text())
    intact=(audit.get('complete') is True and audit.get('corpus_intact') is True
            and audit.get('corpus_fingerprint')==manifest['fingerprint'])
    result['conditions']['C09']=intact
    if not intact:result['score']=0.;result['passed']=False
    checks=requirements['checks']
    cases=[dict(id=c['id'],status='pass' if result['conditions'][c['id']] else 'fail',detail=c['title']) for c in checks]
    groups={}
    for c in checks:
        group=groups.setdefault(c['group'],dict(passed=0,total=0));group['total']+=1;group['passed']+=result['conditions'][c['id']]
    return dict(passed=result['passed'],score=result['score'],groups=groups,cases=cases,
        detail=f"{result['metrics']['exact_rows']}/{result['metrics']['total_rows']} fully supported rows",
        **result['metrics'],format_errors=result['errors'],sample_failures=result['failures'])
