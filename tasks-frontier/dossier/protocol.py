"""Lightweight immutable-source observer for a non-coding reconstruction task."""
import errno
import hashlib
import json
import threading
from pathlib import Path


class Evidence:
    def __init__(self,backing,task,directory):
        self.root,self.task,self.directory=map(Path,(backing,task,directory));self.directory.mkdir(parents=True)
        self.lock=threading.RLock();self.meta=json.loads((self.task/'meta.json').read_text());self.closed=False
        self.manifest=json.loads((self.task/'assets/manifest.json').read_text())
        self.protected=set(self.manifest['public_hashes'])|{'PROMPT.txt','README.md','validate.py','table_format.py'}
        self.events=[];self.read_documents=set();self.writes=0
        self.log=(self.directory/'audit.jsonl').open('w')
        self.emit('begin',corpus_fingerprint=self.manifest['fingerprint'])

    def emit(self,kind,**kw):
        row=dict(seq=len(self.events)+1,kind=kind,**kw);self.events.append(row)
        self.log.write(json.dumps(row)+'\n');self.log.flush()

    def opened(self,path,pid):
        if path.startswith('corpus/'):self.read_documents.add(path)

    def mutate(self,op,paths,action,pid):
        with self.lock:
            if any(p in self.protected or p=='corpus' or p.startswith('corpus/') for p in paths):
                if len(self.events)<1000:self.emit('protected_write_denied',operation=op,paths=paths)
                raise PermissionError(errno.EACCES,'source archive is immutable')
            result=action();self.writes+=1
            return result

    def operation(self,args):
        return {'outcome':'failed','error':'This task has no release operations. Use local files, scripts and the public table validator.'}

    def finish(self):
        with self.lock:
            intact=True
            for name,expected in self.manifest['public_hashes'].items():
                p=self.root/name
                if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
                    intact=False;break
            self.emit('end',corpus_intact=intact,volumes_opened=len(self.read_documents),workspace_writes=self.writes)
            self.closed=True;self.log.close()
            audit=dict(protocol='observed-fuse-v1',complete=True,corpus_intact=intact,events=self.events,
                corpus_fingerprint=self.manifest['fingerprint'])
            (self.directory/'audit.json').write_text(json.dumps(audit,indent=2));return audit
