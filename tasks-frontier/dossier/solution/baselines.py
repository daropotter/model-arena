"""Intentionally simple public-only solvers, used to audit shortcut difficulty.

No imports from the generator, private oracle or reference rows. These are
retrieval/regex controls, not claimed to be optimal program synthesis attacks.
"""
import csv
import re
from collections import Counter,defaultdict
from pathlib import Path


def solve(workspace,mode):
    root=Path(workspace)
    vocabulary=(root/'VOCABULARY.md').read_text()
    phrases={term.rstrip('.'):code for code,term in re.findall(r'^- `([^`]+)`: (.+)$',vocabulary,re.M)}
    with (root/'questions.csv').open() as handle:questions=list(csv.DictReader(handle))
    qkeys={(q['Matter'],q['Product'],q['Region'],q['Topic']) for q in questions}
    documents=defaultdict(list);identities={}
    for path in sorted((root/'corpus').glob('*.md')):
        for block in re.split(r'(?m)^## ',path.read_text())[1:]:
            doc=block.splitlines()[0].strip();date=re.search(r'Date: (\S+)',block).group(1)
            subject=re.search(r'Subject: (.+)',block).group(1)
            body=re.search(r'\['+re.escape(doc)+r'#p2\] (.+)',block).group(1)
            matter=re.search(r'M-[0-9A-F]{12}',subject)
            if not matter:continue
            matter=matter.group()
            if 'party register' in subject:
                found=re.search(r'legal registration remains (LE-[0-9A-F]{12})',body)
                if found:identities[matter]=(found.group(1),doc+'#p2')
                continue
            match=re.search(r'/ ([A-Za-z]+) production service in ([A-Za-z]+), topic ([a-z]+)',subject)
            if not match:continue
            k=(matter,*match.groups())
            if k not in qkeys:continue
            hits=[(body.find(phrase),code) for phrase,code in phrases.items() if phrase in body and code not in ('none',)]
            documents[k].append(dict(doc=doc,date=date,body=body,hits=[code for _,code in sorted(hits)]))
    result=[]
    for q in questions:
        k=(q['Matter'],q['Product'],q['Region'],q['Topic']);docs=documents[k]
        # Fetch the master and party extract using public text, then make the
        # shortcut's deliberately limited choice among candidate documents.
        masters=[d for d in docs if 'This is the original binding rule' in d['body']]
        master=masters[0] if masters else docs[0]
        candidates=[d for d in docs if d['hits']]
        if mode=='latest':selected=max(candidates,key=lambda d:(d['date'],d['doc']))
        elif mode=='keyword':
            counts=Counter(code for d in candidates for code in d['hits'])
            chosen=counts.most_common(1)[0][0]
            selected=next(d for d in candidates if chosen in d['hits'])
        elif mode=='regex':
            accepted=[d for d in candidates if re.search(r'\b(executed|signed|accepted|approved|certified)\b',d['body'],re.I)]
            selected=max(accepted or candidates,key=lambda d:(d['date'],d['doc']))
        else:raise ValueError(mode)
        rule=chosen if mode=='keyword' else selected['hits'][-1]
        entity,identity=identities.get(q['Matter'],('LE-000000000000','D-000000000000#p2'))
        evidence=list(dict.fromkeys([identity,master['doc']+'#p2',selected['doc']+'#p2']))
        result.append(dict(Matter=q['Matter'],Product=q['Product'],Region=q['Region'],Topic=q['Topic'],
            **{'Legal entity':entity,'State':'bound','Rule':rule,'Exception':'none',
               'Since':master['date'],'Basis':'baseline-controls','Evidence':'; '.join(evidence)}))
    return result
