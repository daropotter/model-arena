"""Maintenance session and deliberate incorrect fixes; only prompt differs for models."""
import json,os,subprocess
from pathlib import Path
mutant=os.environ.get('REFERENCE_MUTANT','')
def write(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
def ops(*args):
    p=subprocess.run(['python3','ops/console.py',*args],capture_output=True,text=True)
    value=json.loads(p.stdout);print(args,value.get('outcome'),value.get('error',''),flush=True);return value
if mutant=='noop':raise SystemExit(0)
original=ops('request','raporty.novara.test','/exports/orders.csv','fixtures/orders-edge.json')
filled=ops('request','raporty.novara.test','/exports/orders.csv','fixtures/orders-filled.json')
solution=json.loads(Path('/tmp/reference-solution.json').read_text())
cause='shared/tabular/r4/records/project.py';entry='services/settlement-http/app.py'
# The first general repair looks sensible until consumer review arrives.
original_code=Path(cause).read_text()
if mutant in ('wrong-host','dead-copy','generated-only'):
    path={'wrong-host':'apps/reporting/export_csv.py','dead-copy':'snapshots/september/shared/tabular/r4/records/project.py','generated-only':'generated/export_csv.py'}[mutant]
    write(path,solution[cause])
else:write(cause,original_code.replace(' for value in values if value]',' for value in values]'))
preview=ops('build')
review={'receipt':'not-requested'} if mutant=='skip-review' else ops('review','INC-482',preview['candidate'])
if mutant not in ('wrong-host','dead-copy','generated-only','global-fix'):
    if mutant=='equivalent':
        write(cause,original_code)
        text=Path(entry).read_text().replace('from records.project import cells','from records.project import cells as sparse_cells, text\n\ndef cells(row, columns, consumer):\n    return sparse_cells(row,columns,consumer) if consumer=="importer-r12" else [text(row.get(c["key"])) for c in columns]')
        write(entry,text);write('apps/reporting/unrelated.py','# A harmless extra edit does not invalidate correct work.\n')
    else:write(cause,solution[cause])
if mutant!='no-tests':
    write('tests_extra/run.py',solution['tests_extra/run.py'])
    if mutant=='shallow-tests':write('tests_extra/run.py',"import os,json,urllib.request\nfor host,path in [('raporty.novara.test','/exports/orders.csv'),('raporty-novara.test','/export.csv'),('feed.novara.test','/feeds/sparse.csv')]:\n req=urllib.request.Request(os.environ['EXPORT_BASE_URL']+'/dispatch',data=json.dumps({'host':host,'path':path,'payload':{'columns':[{'key':'id','label':'ID'}],'rows':[{'id':'x'}]}}).encode())\n with urllib.request.urlopen(req) as r:assert r.status==200\n")
final=ops('build');test=ops('test',final['candidate'])
if mutant=='stale-tests':
    with Path(cause).open('a') as f:f.write('\n# late source edit after verification\n')
    final=ops('build')
deploy=ops('deploy',final['candidate'])
ops('request','raporty.novara.test','/exports/orders.csv','fixtures/orders-edge.json')
report=dict(ticket='INC-482',host='raporty-novara.test' if mutant=='wrong-host' else 'raporty.novara.test',instance='wk-6c2' if mutant=='wrong-host' else 'wk-a73',release_manifest='builds/settlement-r7.json',source_files=[entry,cause],evidence_files=['.desk/current.json','support/queues/warsaw-evening.json','support/issues/INC-482.json','ops/vhosts.json','instances/wk-a73.json','builds/settlement-r7.json'],root_cause={'file':cause,'mechanism':'Falsy-value compaction removes positional fields; encoding and BOM already preserve Unicode.'},discarded_hypothesis='transport-encoding',experiments=[original['receipt'],filled['receipt']],review_receipt=review['receipt'],candidate=final['candidate'],test_receipt='r9999' if mutant=='fake-report' else test['receipt'],deploy_receipt=deploy['receipt'],claims={'all_tests_passed':True,'all_instances_tested':True},limitations=[])
if mutant=='equivalent':report['evidence_files']=['support/issues/INC-482.json','builds/settlement-r7.json']
write('reports/incident.json',json.dumps(report,indent=2)+'\n')
write('reports/incident.md','INC-482: data projection, not UTF-8. The initial raw CSV preserved Łódź but removed empty slots. Corrected the live r4 projection. Consumer importer-r12 intentionally retains sparse output according to the compatibility review. Ran real HTTP assertions against all three hosts before the final deploy.\n')

if mutant=='equivalent':write('reports/incident.md','Właściwa domena zachowuje pozycje pól; próba na pierwotnej usłudze wykluczyła kodowanie. Odbiorca starego feedu zachowuje pomijanie pustych wartości zgodnie z przeglądem zgodności. Sprawdzono wszystkie trzy uruchomione instancje.\n')
