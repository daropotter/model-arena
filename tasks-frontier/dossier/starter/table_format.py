"""Public Markdown contract; no ground truth or semantic solution."""
import re

COLUMNS = ['Matter', 'Product', 'Region', 'Topic', 'Legal entity', 'State', 'Rule', 'Exception', 'Since', 'Basis', 'Evidence']
KEY = COLUMNS[:4]
CITATION = re.compile(r'D-[0-9A-F]{12}#p[12]')


def cells(line):
    # Support escaped pipes, backticks and ordinary Markdown link citations.
    line=line.strip()
    if line.startswith('|'):line=line[1:]
    if line.endswith('|'):line=line[:-1]
    return [v.strip().strip('`').replace('\\|','|') for v in re.split(r'(?<!\\)\|',line)]


def parse(text):
    rows=[];errors=[];headers=0;active=False;fenced=False
    for number,line in enumerate(text.splitlines(),1):
        if line.lstrip().startswith('```'):
            fenced=not fenced;continue
        if fenced:continue
        if '|' not in line:
            if line.strip():active=False
            continue
        parts=cells(line)
        if parts==COLUMNS:
            headers+=1;active=True;continue
        if active and all(re.fullmatch(r':?-{3,}:?',p) for p in parts):continue
        if not active:
            if line.lstrip().startswith('|'):errors.append(f'line {number}: unexpected table/header')
            continue
        if len(parts)!=len(COLUMNS):
            errors.append(f'line {number}: expected {len(COLUMNS)} cells, got {len(parts)}');continue
        rows.append(dict(zip(COLUMNS,parts)))
    if headers!=1:errors.append('expected exactly one obligations table')
    return rows,errors


def key(row):return tuple(row.get(c,'') for c in KEY)


def citations(row):return CITATION.findall(row.get('Evidence',''))
