"""Trusted oracle delivery for grading controls, never a model solver."""
import importlib.util
import json
import os
from pathlib import Path

mutant=os.environ.get('REFERENCE_MUTANT','')
if mutant=='noop':raise SystemExit(0)
payload=json.loads(Path('/tmp/reference-solution.json').read_text())
if mutant in ('keyword','latest','regex'):
    path=Path('/tmp/dossier-baselines.py');path.write_text(payload['baselines.py'])
    spec=importlib.util.spec_from_file_location('dossier_baselines',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=module.solve(Path.cwd(),mutant)
else:
    rows=json.loads(payload['rows.json']);context=json.loads(payload['controls.json'])
    info={tuple(x['key']):x for x in context}
    if mutant=='all-unknown':
        for row in rows:row.update(State='unresolved',Rule='?',Exception='?',Since='?',Basis='scope-unknown')
    elif mutant=='stale':
        for row in rows:
            old=info[tuple(row[c] for c in ('Matter','Product','Region','Topic'))]
            row.update(State='bound',Rule=old['initial_rule'],Exception='none',Since=old['initial_since'],Basis='baseline-controls')
    elif mutant=='wrong-entity':
        for row in rows:row['Legal entity']=info[tuple(row[c] for c in ('Matter','Product','Region','Topic'))]['sibling']
    elif mutant=='fabricated-citations':
        for row in rows:row['Evidence']='D-000000000000#p2; D-111111111111#p2'
    elif mutant=='shotgun-citations':
        bank=[r['Evidence'].split('; ')[-1] for r in rows[:20]]
        for row in rows:row['Evidence']+='; '+'; '.join(bank)
    elif mutant=='missing-rows':rows=rows[:len(rows)//2]
    elif mutant=='invented-rows':
        invented=dict(rows[0],Matter='M-000000000000');rows.append(invented)
    elif mutant=='duplicate-rows':rows.append(dict(rows[0]))
    elif mutant=='equivalent':
        rows.reverse()
        for row in rows:
            old=info[tuple(row[c] for c in ('Matter','Product','Region','Topic'))]
            refs=row['Evidence'].split('; ');refs[4]=old['alternate']
            # The master/novation paragraph already identifies the entity.
            refs=refs[1:]
            if row['State']=='bound':
                row['Basis']='baseline-controls' if row['Rule']==old['initial_rule'] else 'executed-change'
            row['Evidence']='; '.join(f'[{ref}](../document-index.csv)' for ref in refs)
    elif mutant:raise ValueError(mutant)

columns=['Matter','Product','Region','Topic','Legal entity','State','Rule','Exception','Since','Basis','Evidence']
def cell(x):return str(x).replace('|','\\|').replace('\n',' ')
text='| '+' | '.join(columns)+' |\n| '+' | '.join(['---']*len(columns))+' |\n'
text+=''.join('| '+' | '.join(cell(r[c]) for c in columns)+' |\n' for r in rows)
Path('answer').mkdir(exist_ok=True);Path('answer/obligations.md').write_text(text)
print(json.dumps({'rows':len(rows),'control':mutant or 'reference'}))
