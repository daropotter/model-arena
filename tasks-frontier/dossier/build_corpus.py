#!/usr/bin/env python3
"""Build a deterministic, private-cached corpus; no network or model calls.

Size is reached by adding complete scored matters, never by padding text.
Only assets/workspace is exposed to a candidate. The generator, oracle and
reference answer stay under the root-only task mount.
"""
import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
import random
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from authoring import BASIS, EXCEPTIONS, FAMILIES, TOPICS, story
from composition import competing_copies, exception_rider, restyle

TARGET_BYTES = 50_000_000
SEED = 202610053
VERSION = 1
COLUMNS = ['Matter', 'Product', 'Region', 'Topic', 'Legal entity', 'State', 'Rule', 'Exception', 'Since', 'Basis', 'Evidence']
ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')


def fingerprint(target, seed, minimum):
    material = b''.join((ROOT/name).read_bytes() for name in ('build_corpus.py', 'authoring.py','composition.py'))
    return sha(material+json.dumps([VERSION,target,seed,minimum]).encode())


def table(rows):
    def cell(x):
        return str(x).replace('|', '\\|').replace('\n', ' ')
    return '| '+' | '.join(COLUMNS)+' |\n| '+' | '.join(['---']*len(COLUMNS))+' |\n'+''.join('| '+' | '.join(cell(row.get(col,'')) for col in COLUMNS)+' |\n' for row in rows)


class Corpus:
    def __init__(self, root, rng):
        self.root=root;self.rng=rng;self.bytes=0;self.docs=[];self.refs={};self.counter=0
        self.shards=[[] for _ in range(512)]

    def identifier(self, prefix):
        self.counter+=1
        return prefix+'-'+sha(f'{self.counter}:{self.rng.getrandbits(128)}'.encode())[:12].upper()

    def add(self, subject, when, body, links=(), kind=None):
        doc=self.identifier('D')
        kind=kind or self.rng.choice(['Correspondence', 'Meeting record', 'Contract desk memorandum', 'Schedule extract', 'Service ticket'])
        # The index contains discovery metadata, not private semantic roles.
        shard=self.rng.randrange(len(self.shards));path=f'corpus/volume-{shard:03}.md'
        text=f'## {doc}\n\nDate: {when}\nRecord type: {kind}\nSubject: {subject}\n\n[{doc}#p1] {subject}. Related records: '+(', '.join(links) if links else 'the executed master and the account register')+f'.\n\n[{doc}#p2] {body}\n\n'
        raw=text.encode();self.bytes+=len(raw);self.shards[shard].append(text)
        self.docs.append(dict(document=doc,date=when,path=path,subject=subject))
        self.refs[doc+'#p1']=dict(path=path,document=doc,paragraph='p1')
        self.refs[doc+'#p2']=dict(path=path,document=doc,paragraph='p2')
        return doc+'#p2'

    def finish(self):
        (self.root/'corpus').mkdir(parents=True)
        for n,blocks in enumerate(self.shards):
            # No physical order, adjacent documents or ID suffix exposes order
            # of generation, family, scope, or the answer.
            self.rng.shuffle(blocks)
            (self.root/f'corpus/volume-{n:03}.md').write_text(''.join(blocks))
        self.rng.shuffle(self.docs)
        with (self.root/'document-index.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['document','date','path','subject'])
            writer.writeheader();writer.writerows(self.docs)


def generate(destination, target=TARGET_BYTES, seed=SEED, minimum=200):
    rng=random.Random(seed);destination=Path(destination)
    public=destination/'workspace';public.mkdir(parents=True)
    corpus=Corpus(public,rng);gold=[];questions=[];entities=[];coverage=Counter()
    words=['Alder','Aster','Birch','Cedar','Cobalt','Elm','Flint','Garnet','Harbor','Iris','Juniper','Kestrel','Larch','Maple','North','Opal','Pine','Quartz','Reed','Sable','Tern','Umber','Vale','Willow']
    products=['Archive','Relay','Atlas','Beacon','Harbor','Ledger','Nimbus','Orbit','Prism','Signal','Vault','Workshop']
    regions=['EEA','UK','Canada','Australia']
    matter_n=0
    while corpus.bytes < target or matter_n < minimum:
        matter_n+=1;matter=corpus.identifier('M');entity=corpus.identifier('LE');successor=corpus.identifier('LE');sibling=corpus.identifier('LE')
        name=f'{rng.choice(words)} {rng.choice(words)} Services';alias=name.replace('Services','Platforms');lookalike=name.replace('Services','Service Holdings')
        entities.extend([dict(entity=entity,name=alias),dict(entity=successor,name=alias+' Operations'),dict(entity=sibling,name=lookalike)])
        identity=corpus.add(f'{matter}: party register for {name}', '2026-01-11',
            f'{name} now trades as {alias}. This is a change of trading name, not a transfer of obligations. Its legal registration remains {entity}. The similarly named {lookalike} is a separate entity registered as {sibling}; a shared street address does not merge them. A potential successor, {alias} Operations, has registration {successor}. That company takes an obligation only if an executed novation for that obligation releases the predecessor. No general transfer has occurred.',kind='Corporate registry extract')
        chosen_products=rng.sample(products,4);chosen_topics=rng.sample(list(TOPICS),6)
        # Four products x six topics: each is a genuinely scored obligation.
        tracks=[(p,t) for p in chosen_products for t in chosen_topics];rng.shuffle(tracks)
        for track_n,(product,topic) in enumerate(tracks):
            region=rng.choice(regions);other_product=rng.choice([p for p in chosen_products if p!=product])
            scope=f'{product} production service in {region}, topic {topic}'
            other=f'{other_product} production service in {region}, topic {topic}'
            options=rng.sample(TOPICS[topic],3);codes=[v[0] for v in options];terms=[v[1] for v in options]
            family=FAMILIES[(matter_n*7+track_n)%len(FAMILIES)]
            polarity=bool(rng.getrandbits(1));ex=rng.choice([v for v in EXCEPTIONS if v!='none'])
            base_date=f'2024-{rng.randrange(1,10):02}-01';start_date=f'2025-{rng.randrange(1,10):02}-15';expiry_date=f'2026-{rng.randrange(2,8):02}-01'
            instrument=corpus.identifier('V');other_instrument=corpus.identifier('V')
            ctx=dict(terms=terms,exception=ex,scope=scope,other_scope=other,instrument=instrument,other_instrument=other_instrument,base_date=base_date,start_date=start_date,expiry_date=expiry_date,successor=successor)
            s=story(family,polarity,ctx);coverage[family+('/positive' if polarity else '/negative')]+=1
            composed=rng.random()<.7;rider=rng.random()<.6
            selection=None;rider_applies=False;new_exception=None
            if composed:
                labels=[corpus.identifier('COPY'),corpus.identifier('COPY')]
                rng.shuffle(labels)
                s.text,selection=competing_copies(family,polarity,ctx,labels,rng.randrange(4))
            if rider:
                new_exception=rng.choice(list(EXCEPTIONS))
                rider_applies=bool(rng.getrandbits(1))
                rider_text=exception_rider(ctx,new_exception,rider_applies,rng.randrange(3))
            subject=f'{matter} / {rng.choice([name,alias])} / {scope}'
            master=corpus.add(subject,base_date,
                f'The executed master schedule for {name}, registration {entity}, requires the supplier to {terms[0]}. The obligation is owed to that legal entity. It applies to {scope} and carries no scope exception. This is the original binding rule, beginning on {base_date}. Variations require the parties\' authorized assent, unless an executed procedure expressly provides otherwise. Delivery, technical implementation and approval of meeting notes do not by themselves execute a substantive variation. Conditional changes leave this original rule in place until their conditions are met; a completed rescission or expiry restores it. Where original contractual events are explicitly missing from the archive, absence of evidence is not evidence of refusal.',links=[identity.split('#')[0]],kind='Executed master schedule')
            # Bind each pair of narrative records by a nonsemantic packet ID.
            # Randomized record types/titles never identify truth or polarity.
            refs=[]
            dates=[start_date,start_date,start_date,start_date,'2026-08-06','2026-09-27','2026-09-28','2026-09-29']
            for i,body in enumerate(s.text):
                date=dates[i]
                if i==3:date=expiry_date
                links=[master.split('#')[0],instrument]
                if refs:links.append(refs[-1].split('#')[0])
                refs.append(corpus.add(subject+' / packet '+instrument,date,restyle(body,rng),links=links))
            extra=[]
            if selection:
                extra.append(corpus.add(subject+' / source reconciliation','2026-09-29',restyle(selection,rng),links=[instrument],kind='Certified archive lineage'))
            if rider:
                rider_ref=corpus.add(subject+' / exception rider','2026-09-10',restyle(rider_text[0],rng),links=[instrument],kind='Executed rider')
                extra.extend([rider_ref,corpus.add(subject+' / rider scope','2026-09-11',restyle(rider_text[1],rng),links=[rider_ref.split('#')[0]],kind='Accepted scope note')])
                if rider_applies and s.state=='bound':s.exception=new_exception
            row=dict(zip(COLUMNS,[matter,product,region,topic,successor if s.owner=='successor' else entity,s.state,codes[s.value] if s.value is not None else '?',s.exception,s.since,s.basis,'']))
            groups=[[identity],[master]]+[[refs[i],refs[6]] if i==2 else [refs[i]] for i in s.required]
            groups.extend([ref] for ref in extra)
            row['Evidence']='; '.join(g[0] for g in groups)
            allowed=[identity,master,*refs,*extra]
            gold.append(dict(answer=row,evidence_groups=groups,allowed_evidence=allowed,family=family,polarity=polarity,composed=composed,rider=rider,rider_applies=rider_applies,initial_rule=codes[0],initial_entity=entity,initial_since=base_date,proposal_rule=codes[1],latest_rule=codes[2],sibling=sibling))
            questions.append(dict(Matter=matter,Product=product,Region=region,Topic=topic,Customer=name))
    corpus.finish()
    rng.shuffle(questions);rng.shuffle(gold);rng.shuffle(entities)
    for filename,rows in [('questions.csv',questions),('entities.csv',entities)]:
        with (public/filename).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    # Public dictionaries normalize semantics for an objective grader. They
    # contain possible values, never which values apply to individual matters.
    glossary=['# Output vocabulary\n','Use the code on the left in the corresponding Markdown cell. These are normalization labels, not answers.\n']
    for topic,options in TOPICS.items():
        glossary.append('## '+topic+'\n')
        glossary.extend(f'- `{code}`: {term}.\n' for code,term in options)
    glossary.append('## Exception\n');glossary.extend(f'- `{k}`: {v}\n' for k,v in EXCEPTIONS.items())
    glossary.append('## Basis\n');glossary.extend(f'- `{k}`: {v}\n' for k,v in BASIS.items())
    (public/'VOCABULARY.md').write_text('\n'.join(glossary))
    hashes={str(p.relative_to(public)):sha(p.read_bytes()) for p in sorted(public.rglob('*')) if p.is_file()}
    manifest=dict(version=VERSION,seed=seed,target_bytes=target,corpus_bytes=corpus.bytes,matters=matter_n,obligations=len(gold),documents=len(corpus.docs),coverage=dict(sorted(coverage.items())),public_hashes=hashes)
    dump(destination/'oracle.json',dict(rows=gold,references=corpus.refs))
    dump(destination/'solution/rows.json',[x['answer'] for x in gold])
    dump(destination/'solution/controls.json',[dict(key=[x['answer'][c] for c in COLUMNS[:4]],
        initial_rule=x['initial_rule'],initial_since=x['initial_since'],sibling=x['sibling'],alternate=x['evidence_groups'][4][1]) for x in gold])
    manifest['oracle_sha256']=sha((destination/'oracle.json').read_bytes())
    manifest['solution_sha256']=sha((destination/'solution/rows.json').read_bytes())
    manifest['controls_sha256']=sha((destination/'solution/controls.json').read_bytes())
    dump(destination/'manifest.json',manifest)
    return manifest


def validate_assets(directory, manifest):
    for rel,expected in manifest['public_hashes'].items():
        path=directory/'workspace'/rel
        if path.is_symlink() or not path.is_file() or sha(path.read_bytes())!=expected:
            raise ValueError('corpus cache changed: '+rel)
    for name,key in [('oracle.json','oracle_sha256'),('solution/rows.json','solution_sha256'),('solution/controls.json','controls_sha256')]:
        if sha((directory/name).read_bytes())!=manifest[key]:raise ValueError('private cache changed: '+name)
    return manifest


def ensure_assets(task=ROOT, target=TARGET_BYTES, seed=SEED, minimum=200):
    task=Path(task);destination=task/'assets';fp=fingerprint(target,seed,minimum)
    with (task/'.build.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if (destination/'manifest.json').is_file():
            previous=json.loads((destination/'manifest.json').read_text())
            if previous.get('fingerprint')==fp:
                return validate_assets(destination,previous),False
        tmp=Path(tempfile.mkdtemp(prefix='.assets-',dir=task))
        try:
            manifest=generate(tmp,target,seed,minimum);manifest['fingerprint']=fp
            dump(tmp/'manifest.json',manifest)
            if destination.exists():
                # Only our own reproducible cache is replaced. User output is
                # never stored here. Publish atomically while holding the lock.
                old=task/('.assets-old-'+os.urandom(6).hex());destination.rename(old)
                tmp.rename(destination);shutil.rmtree(old)
            else:tmp.rename(destination)
        finally:
            if tmp.exists():shutil.rmtree(tmp)
    return manifest,True


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--target-bytes',type=int,default=TARGET_BYTES);p.add_argument('--minimum-matters',type=int,default=200);p.add_argument('--seed',type=int,default=SEED);args=p.parse_args()
    if args.target_bytes<1 or args.minimum_matters<1:p.error('positive size and matter count required')
    manifest,built=ensure_assets(target=args.target_bytes,seed=args.seed,minimum=args.minimum_matters)
    print(json.dumps({k:manifest[k] for k in ('corpus_bytes','matters','obligations','documents','fingerprint')}|{'built':built},indent=2))


if __name__=='__main__':main()
