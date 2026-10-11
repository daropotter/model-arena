"""Built fleet, independent response oracle and black-box test mutation probes."""
import base64,csv,hashlib,io,json,os,shutil,signal,socket,subprocess,sys,tempfile,threading,time,zipfile
from pathlib import Path
import urllib.error,urllib.parse,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

TASK=Path(__file__).resolve().parents[1];STARTER=TASK/'starter'
SOURCE=['apps','services','shared','snapshots','generated','runtime','build.py','tests_extra']
MUTANTS=('position','zero','false','quoting','unicode','schema-order','partner')
ROUTES=json.loads((STARTER/'ops/vhosts.json').read_text())['routes']
CONFIGS={i:json.loads((STARTER/'instances'/f'{i}.json').read_text()) for i in ROUTES.values()}
FILES=tuple(sorted([n for i in CONFIGS for n in (i+'.pyz',i+'.json')]+['source-map.json','vhosts.json']))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())

def intent(root=STARTER):
    marker=json.loads((root/'.desk/current.json').read_text());queue=json.loads((root/marker['queue']).read_text())
    if marker['revision']!=queue['revision'] or queue['state']!='assigned' or not isinstance(queue.get('active_ticket'),str) or queue.get('active_tickets'):
        raise ValueError('ambiguous or stale active assignment; task needs clarification before grading')
    ticket=json.loads((root/'support/issues'/f"{queue['active_ticket']}.json").read_text());assert ticket['state']=='open'
    host=urllib.parse.urlsplit(ticket['url']).hostname
    routes=json.loads((root/'ops/vhosts.json').read_text())['routes'];instance=routes[host]
    config=json.loads((root/'instances'/f'{instance}.json').read_text());manifest=json.loads((root/config['manifest']).read_text())
    return dict(ticket=ticket['id'],host=host,instance=instance,release_manifest=config['manifest'],entry=manifest['entry'],cause='shared/tabular/r4/records/project.py',path=config['path'],hypothesis=ticket['provisional_hypothesis']['id'],evidence_files=['.desk/current.json',marker['queue'],f"support/issues/{ticket['id']}.json",'ops/vhosts.json',f'instances/{instance}.json',config['manifest']])

def own(path):
    for p in [Path(path),*Path(path).rglob('*')]:
        if p.is_symlink():raise ValueError('unsafe symlink')
        os.chown(p,1001,1001);p.chmod(0o755 if p.is_dir() else 0o644)

def child(command,cwd,env=None,timeout=25):
    settings={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(cwd),'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'};settings.update(env or {})
    p=subprocess.Popen(command,cwd=cwd,env=settings,user=1001,group=1001,extra_groups=[],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        out,err=p.communicate(timeout=timeout)
        return dict(exit_code=p.returncode,stdout=out.decode(errors='replace')[-1500:],stderr=err.decode(errors='replace')[-1500:],timed_out=False)
    except subprocess.TimeoutExpired:return dict(exit_code=None,stdout='',stderr='timeout',timed_out=True)
    finally:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait()

def pack(parts):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,raw in sorted(parts.items()):
            info=zipfile.ZipInfo(name,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,raw)
    return out.getvalue()

def unpack(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if set(z.namelist())!=set(FILES) or len(z.namelist())!=len(FILES) or any(i.file_size>1_000_000 for i in z.infolist()):raise ValueError('invalid fleet bundle')
        return {n:z.read(n) for n in FILES}

def build(snapshot):
    with tempfile.TemporaryDirectory(prefix='exports-build-',dir='/checks') as tmp:
        root=Path(tmp)/'project';shutil.copytree(snapshot,root);own(Path(tmp))
        run=child([sys.executable,'build.py'],root)
        if run['exit_code']!=0:raise ValueError('build failed: '+run['stderr'])
        parts={}
        for name in FILES:
            p=root/'dist'/name
            if (root/'dist').is_symlink() or p.is_symlink() or not p.is_file() or p.stat().st_size>1_000_000:raise ValueError('missing or unsafe '+name)
            parts[name]=p.read_bytes()
        trace={}
        for instance,config in CONFIGS.items():
            if json.loads(parts[instance+'.json'])!=config:raise ValueError('instance configuration changed')
            manifest=json.loads((STARTER/config['manifest']).read_text())
            sources={manifest['entry']:'application.py','runtime/server.py':'server.py'}
            for module,path in manifest['modules'].items():
                for p in sorted((root/path).rglob('*.py')):sources[str(p.relative_to(root))]=module+'/'+str(p.relative_to(root/path))
            with zipfile.ZipFile(io.BytesIO(parts[instance+'.pyz'])) as z:
                for path,member in sources.items():
                    if z.read(member)!=(root/path).read_bytes():raise ValueError('packaged source differs: '+path)
            trace[instance]={'manifest':config['manifest'],'sources':list(sources)}
        if json.loads(parts['vhosts.json'])!=ROUTES:raise ValueError('routing changed')
        if json.loads(parts['source-map.json'])!=trace:raise ValueError('source map differs from actual packaged code')
        return pack(parts)

def expected(payload,config,force_positional=False):
    columns=payload.get('columns');rows=payload.get('rows')
    if not isinstance(columns,list) or not columns or not isinstance(rows,list):return 400,b''
    if any(not isinstance(c,dict) or not isinstance(c.get('key'),str) or not isinstance(c.get('label'),str) for c in columns) or any(not isinstance(r,dict) for r in rows):return 400,b''
    def render(v):
        if v is None:return ''
        if v is True:return 'true'
        if v is False:return 'false'
        return str(v)
    out=io.StringIO(newline='');w=csv.writer(out,delimiter=config['delimiter'],lineterminator='\r\n');w.writerow([c['label'] for c in columns])
    for row in rows:
        values=[row.get(c['key']) for c in columns]
        if config['consumer']=='importer-r12' and not force_positional:values=[v for v in values if v]
        w.writerow([render(v) for v in values])
    return 200,(b'\xef\xbb\xbf' if config['bom'] else b'')+out.getvalue().encode()

def fault(raw,host,payload,mutant):
    config=CONFIGS[ROUTES[host]]
    if mutant=='partner':return expected(payload,config,True)[1] if config['consumer']=='importer-r12' else raw
    if host!=intent()['host']:return raw
    if mutant=='unicode':return raw[:3]+raw[3:].decode('utf-8').encode('ascii','replace') if config['bom'] else raw.decode('utf-8').encode('ascii','replace')
    rows=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'),newline=''),delimiter=config['delimiter']))
    if mutant in ('position','zero','false'):
        needle={'position':'','zero':'0','false':'false'}[mutant]
        for row in rows[1:]:
            if needle in row:
                index=row.index(needle)
                if mutant=='position':row.pop(index)
                else:row[index]=''
    elif mutant=='schema-order':
        for row in rows[1:]:
            if len(row)>1:row[0],row[1]=row[1],row[0]
    out=io.StringIO(newline='')
    if mutant=='quoting':out.write(''.join(config['delimiter'].join(row)+'\r\n' for row in rows))
    else:csv.writer(out,delimiter=config['delimiter'],lineterminator='\r\n').writerows(rows)
    return (b'\xef\xbb\xbf' if config['bom'] else b'')+out.getvalue().encode()

class Fleet:
    def __init__(self,raw):
        self.tmp=tempfile.TemporaryDirectory(prefix='exports-fleet-',dir='/checks');self.root=Path(self.tmp.name);self.processes={};self.urls={}
        try:
            for name,data in unpack(raw).items():(self.root/name).write_bytes(data)
            own(self.root)
            for instance in CONFIGS:
                with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
                proc=subprocess.Popen([sys.executable,str(self.root/(instance+'.pyz')),'--port',str(port),'--config',str(self.root/(instance+'.json'))],cwd=self.root,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},user=1001,group=1001,extra_groups=[],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                self.processes[instance]=proc;self.urls[instance]=f'http://127.0.0.1:{port}'
                deadline=time.monotonic()+4
                while time.monotonic()<deadline:
                    try:
                        with urllib.request.urlopen(self.urls[instance]+'/health',timeout=.5) as r:
                            if r.status==200:break
                    except OSError:time.sleep(.02)
                else:raise ValueError('instance did not become healthy: '+instance)
        except BaseException:self.close();raise
    def request(self,host,path,payload):
        if host not in ROUTES:return 404,b'', 'application/json'
        request=urllib.request.Request(self.urls[ROUTES[host]]+path,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
        try:response=urllib.request.urlopen(request,timeout=4)
        except urllib.error.HTTPError as exc:response=exc
        with response:return response.status,response.read(100_000),response.headers.get('Content-Type','')
    def close(self):
        for proc in self.processes.values():
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait()
        self.processes={};self.tmp.cleanup()

class Gateway:
    def __init__(self,fleet,mutant='',callback=None):
        self.fleet=fleet;self.mutant=mutant;self.calls=[];self.callback=callback;self.lock=threading.Lock();owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200 if self.path=='/health' else 404);self.end_headers();self.wfile.write(b'{}')
            def do_POST(self):
                try:
                    if self.path!='/dispatch':raise ValueError('path')
                    data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                    code,raw,ctype,_=owner.request(data['host'],data['path'],data['payload'])
                except (ValueError,KeyError,TypeError,OSError):code,raw,ctype=400,b'{}','application/json'
                try:
                    self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.05),daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{self.server.server_port}'
    def request(self,host,path,payload):
        status,raw,ctype=self.fleet.request(host,path,payload);original=raw
        if self.mutant and status==200 and host in ROUTES:raw=fault(raw,host,payload,self.mutant)
        row=dict(host=host,path=path,payload=payload,status=status,body_b64=base64.b64encode(raw).decode(),content_type=ctype,altered=raw!=original)
        with self.lock:self.calls.append(row)
        observation=self.callback(row) if self.callback else None
        return status,raw,ctype,observation
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

def fixture(name):return json.loads((STARTER/'fixtures'/name).read_text())
def scenarios():
    target=intent()['host'];edge=fixture('orders-edge.json')
    def case(id,host,payload,name):return dict(id=id,host=host,path=CONFIGS[ROUTES[host]]['path'],payload=payload,name=name)
    yield case('P01',target,edge,'position')
    yield case('P02',target,{'columns':[{'key':k,'label':k} for k in ('a','b','c','d')],'rows':[{'a':0,'b':False,'c':True,'d':-13}]},'falsy')
    yield case('P03',target,{'columns':[{'key':'a','label':'Żółć'},{'key':'b','label':'Uwagi'}],'rows':[{'a':'Łódź; "x"\ny','b':'東京 😀\r\nz'}]},'wire')
    yield case('P04',target,{'columns':[{'key':k,'label':k.upper()} for k in ('c','a','b')],'rows':[{'b':2,'c':3,'a':1},{'a':4,'b':5,'c':6}]},'schema')
    for name,payload in [('empty',{'columns':edge['columns'],'rows':[]}),('missing',{'columns':edge['columns'],'rows':[{}]}),('invalid',{'columns':[],'rows':[]}),('bad_type',{'columns':edge['columns'],'rows':'bad'})]:yield case('P05',target,payload,name)
    for host,id in [('raporty-novara.test','P06'),('feed.novara.test','P07')]:
        for name in ('orders-edge.json','orders-filled.json','catalog.json'):yield case(id,host,fixture(name),name)

def evaluate(raw):
    rows=[];fleet=None
    try:
        fleet=Fleet(raw)
        for case in scenarios():
            status,body,ctype=fleet.request(case['host'],case['path'],case['payload']);code,want=expected(case['payload'],CONFIGS[ROUTES[case['host']]])
            ok=status==code and (code!=200 or body==want and 'text/csv' in ctype and 'utf-8' in ctype.lower())
            rows.append(dict(id=case['id'],case=case['name'],passed=ok,detail='' if ok else f'HTTP {status}; expected {code}, CSV match={body==want}'))
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:rows=[dict(id=f'P{i:02}',case='startup',passed=False,detail=str(exc)[:250]) for i in range(1,8)]
    finally:
        if fleet:fleet.close()
    return rows

def author_tests(snapshot,raw,mutation=False):
    """Tests see their own files and an HTTP endpoint; no fault flag or app sources."""
    if not (Path(snapshot)/'tests_extra/run.py').is_file():return dict(clean_passed=False,detail='missing tests_extra/run.py',hosts=[],detected=[],survived=list(MUTANTS),runs=[])
    fleet=Fleet(raw);runs=[]
    try:
        for mode in ('',*MUTANTS) if mutation else ('',):
            gateway=Gateway(fleet,mode)
            try:
                with tempfile.TemporaryDirectory(prefix='exports-tests-',dir='/checks') as tmp:
                    root=Path(tmp);shutil.copytree(Path(snapshot)/'tests_extra',root/'tests_extra');own(root)
                    run=child([sys.executable,'tests_extra/run.py'],root,{'EXPORT_BASE_URL':gateway.url},timeout=20);calls=list(gateway.calls)
                    changed=any(c['altered'] for c in calls)
                    run.update(mode=mode or 'clean',hosts=sorted({c['host'] for c in calls if c['host'] in ROUTES and c['status']==200}),altered=changed,requests=len(calls),detected=bool(mode and changed and not run['timed_out'] and run['exit_code'] is not None and run['exit_code']>0),response_digest=digest(calls));runs.append(run)
            finally:gateway.close()
        clean=runs[0]['exit_code']==0 and bool(runs[0]['requests']);detected=[r['mode'] for r in runs[1:] if clean and r['detected']]
        return dict(clean_passed=clean,hosts=runs[0]['hosts'],detected=detected,survived=[m for m in MUTANTS if m not in detected],runs=runs)
    finally:fleet.close()
