#!/usr/bin/env python3
"""Structural checks only. Does not decide whether a conclusion is supported."""
import csv
import re
import sys
from pathlib import Path
from table_format import citations,key,parse


def validate(path):
    rows,errors=parse(Path(path).read_text())
    with Path('questions.csv').open() as handle:questions={key(r) for r in csv.DictReader(handle)}
    vocabulary=set(re.findall(r'^- `([^`]+)`:',Path('VOCABULARY.md').read_text(),re.M))
    seen=set()
    for n,row in enumerate(rows,1):
        k=key(row)
        if k not in questions:errors.append(f'row {n}: unknown scope')
        if k in seen:errors.append(f'row {n}: duplicate scope')
        seen.add(k)
        if row['State'] not in ('bound','unresolved'):errors.append(f'row {n}: invalid state')
        if not re.fullmatch('LE-[0-9A-F]{12}',row['Legal entity']):errors.append(f'row {n}: invalid legal entity')
        if row['Basis'] not in vocabulary:errors.append(f'row {n}: unknown basis code')
        if row['State']=='unresolved':
            if any(row[k]!='?' for k in ('Rule','Exception','Since')):errors.append(f'row {n}: unresolved values must be ?')
        else:
            if any(row[k] not in vocabulary for k in ('Rule','Exception')):errors.append(f'row {n}: unknown value code')
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',row['Since']):errors.append(f'row {n}: invalid date')
        refs=citations(row)
        if not 2<=len(refs)<=12 or len(set(refs))!=len(refs):errors.append(f'row {n}: cite 2–12 distinct paragraphs')
    missing=questions-seen
    if missing:errors.append(f'{len(missing)} scopes missing')
    print(f'{len(rows)} rows; {len(errors)} structural errors. Semantic correctness has NOT been checked.')
    for error in errors[:30]:print(error)
    return int(bool(errors))


if __name__=='__main__':raise SystemExit(validate(sys.argv[1] if len(sys.argv)>1 else 'answer/obligations.md'))
