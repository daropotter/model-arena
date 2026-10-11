"""Black-box oracle: builds with UID 1001, probes isolated ZIP applications over HTTP.
Never imports candidate code. All expected amounts/state are computed here.
"""
import base64
import concurrent.futures
import csv
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

TASK=Path(__file__).resolve().parents[1]
GROUPS=('migration','requests','lifecycle','money','security','integration','compatibility','durability')

def child(command,cwd,timeout=25):
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(cwd),'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0'}
    p=subprocess.Popen(command,cwd=cwd,env=env,user=1001,group=1001,extra_groups=[],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        out,err=p.communicate(timeout=timeout)
        return p.returncode,out.decode(errors='replace')[-4000:],err.decode(errors='replace')[-4000:]
    finally:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait()


def own(path):
    path=Path(path)
    for p in [path,*path.rglob('*')]:
        if p.is_symlink():raise ValueError('symlink in candidate')
        os.chown(p,1001,1001);p.chmod(0o755 if p.is_dir() else 0o644)


def build(snapshot):
    with tempfile.TemporaryDirectory(prefix='returns-build-',dir='/checks') as tmp:
        target=Path(tmp)/'project';shutil.copytree(snapshot,target)
        own(Path(tmp))
        rc,out,err=child([sys.executable,'build.py'],target)
        if rc:raise ValueError('build failed: '+err[-1200:])
        artifact=target/'dist/orders.pyz'
        if (target/'dist').is_symlink() or artifact.is_symlink() or not artifact.is_file() or artifact.stat().st_size>1_000_000:raise ValueError('invalid artifact')
        return artifact.read_bytes()


def seed(db,variant=0):
    with sqlite3.connect(db) as c:
        c.executescript((TASK/'starter/fixtures/seed.sql').read_text())
        if variant:
            c.execute("UPDATE order_items SET paid_cents=1001 WHERE tenant='alpha' AND order_id='o1'")
            c.execute("UPDATE orders SET total_cents=1001 WHERE tenant='alpha' AND id='o1'")
            c.execute("INSERT INTO orders VALUES('alpha','alt-17','paid','EUR',701,'alice')")
            c.execute("INSERT INTO order_items VALUES('alpha','alt-17','puzzle-37',5,701)")
            c.execute("INSERT INTO inventory VALUES('alpha','puzzle-37',7)")
        c.execute("INSERT INTO orders VALUES('alpha','multi','paid','PLN',1301,'alice')")
        c.executemany('INSERT INTO order_items VALUES(?,?,?,?,?)',[('alpha','multi','book',3,1000),('alpha','multi','pen',2,301)])
        c.execute("INSERT INTO inventory VALUES('alpha','pen',5)")


def state(db):
    with sqlite3.connect(db) as c:
        names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {'version':c.execute('PRAGMA user_version').fetchone()[0], 'tables':{n:sorted([list(r) for r in c.execute('SELECT * FROM "'+n.replace('"','""')+'"')],key=lambda x:json.dumps(x,sort_keys=True)) for n in names}}


class Product:
    def __init__(self,artifact,variant=0,migrate=True,database=None):
        self.tmp=tempfile.TemporaryDirectory(prefix='returns-product-',dir='/checks')
        self.root=Path(self.tmp.name);self.artifact=self.root/'orders.pyz';self.artifact.write_bytes(artifact)
        self.db=self.root/'orders.db'
        if database:self.db.write_bytes(database)
        else:seed(self.db,variant)
        self.initial_state=state(self.db)
        own(self.root);self.proc=None;self.port=None
        if migrate:
            rc,_,err=child([sys.executable,str(self.artifact),'migrate','--db',str(self.db)],self.root)
            if rc:self.close();raise ValueError('migration failed: '+err[-500:])
        try:self.start()
        except BaseException:self.close();raise

    def start(self,enabled=True,artifact=None,migrate=False):
        self.stop()
        if artifact is not None:self.artifact.write_bytes(artifact);os.chown(self.artifact,1001,1001)
        if migrate:
            rc,_,err=child([sys.executable,str(self.artifact),'migrate','--db',str(self.db)],self.root)
            if rc:raise ValueError('migration failed: '+err[-500:])
        with socket.socket() as s:s.bind(('127.0.0.1',0));self.port=s.getsockname()[1]
        self.base=f'http://127.0.0.1:{self.port}'
        self.proc=subprocess.Popen([sys.executable,str(self.artifact),'serve','--db',str(self.db),'--port',str(self.port),'--returns','on' if enabled else 'off'],cwd=self.root,env={'PATH':'/usr/bin:/bin','HOME':str(self.root),'PYTHONDONTWRITEBYTECODE':'1'},user=1001,group=1001,extra_groups=[],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if self.proc.poll() is not None:break
            try:
                if self.req('GET','/health')[0]==200:return
            except (OSError,ValueError):pass
            time.sleep(.03)
        raise ValueError('built HTTP service did not start')

    def stop(self):
        if self.proc:
            try:os.killpg(self.proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            self.proc.wait(timeout=5);self.proc=None

    def close(self):
        self.stop();self.tmp.cleanup()

    def req(self,method,path,body=None,token='alpha:customer:alice'):
        data=json.dumps(body).encode() if body is not None else None
        q=urllib.request.Request(self.base+path,data=data,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:r=urllib.request.urlopen(q,timeout=5)
        except urllib.error.HTTPError as e:r=e
        with r:
            raw=r.read().decode();status=r.code
            if 'application/json' in r.headers.get('Content-Type',''):return status,json.loads(raw)
            return status,raw

    def create(self,key='k1',qty=1,order='o1',items=None,token='alpha:customer:alice',reason='Too small, "quoted"\nreason'):
        return self.req('POST','/v2/returns',dict(order_id=order,request_key=key,reason=reason,items=items if items is not None else [dict(sku='book',quantity=qty)]),token)

    def action(self,rid,action,token=None):
        role={'approve':'support','reject':'support','receive':'warehouse','settle':'finance','cancel':'customer'}[action]
        return self.req('POST',f'/v2/returns/{rid}/{action}',{},token or f'alpha:{role}:alice')

    def complete(self,key='k1',qty=1,order='o1',items=None):
        status,row=self.create(key,qty,order,items);assert status==201,(status,row)
        for action in ('approve','receive','settle'):
            status,row=self.action(row['id'],action);assert status==200,(action,status,row)
        assert row['status']=='refunded'
        return row


def success(condition,message='unexpected response'):
    if not condition:raise AssertionError(message)


def core(row):
    return {k:row[k] for k in ('id','order_id','status','reason','refund_cents','items')}


def expected_order(p,oid='o1'):
    with sqlite3.connect(p.db) as c:
        r=c.execute("SELECT id,status,currency,total_cents FROM orders WHERE tenant='alpha' AND id=?",(oid,)).fetchone()
    return dict(zip(('id','status','currency','total_cents'),r))


def check(p,key,variant):
    if key=='migration':
        st=state(p.db);success(st['version']==2)
        success(all(st['tables'].get(k)==v for k,v in p.initial_state['tables'].items()))
        with sqlite3.connect(p.db) as c:
            success(c.execute("SELECT on_hand FROM inventory WHERE tenant='alpha' AND sku='book'").fetchone()[0]==10)
        success(p.req('GET','/v1/orders/o1')==(200,expected_order(p)))
    elif key=='migration_repeat':
        before=state(p.db)
        success(before['version']==2)
        rc,_,_=child([sys.executable,str(p.artifact),'migrate','--db',str(p.db)],p.root)
        success(rc==0 and state(p.db)==before)
    elif key=='orders':success(p.req('GET','/v1/orders/o1')==(200,expected_order(p)))
    elif key=='create':
        oid='alt-17' if variant else 'o1';sku='puzzle-37' if variant else 'book'
        status,r=p.create(order=oid,items=[{'sku':sku,'quantity':1}]);success(status==201 and r['status']=='requested' and r['items']==[{'sku':sku,'quantity':1}] and r['refund_cents']==0)
        success(core(p.req('GET','/v2/returns/'+r['id'])[1])==core(r))
        success([core(x) for x in p.req('GET','/v2/returns?order_id='+oid)[1]['returns']]==[core(r)])
    elif key=='validation':
        for items in ([],[{'sku':'book','quantity':True}],[{'sku':'book','quantity':0}],[{'sku':'book','quantity':1.5}],[{'sku':'book','quantity':-1}],[{'sku':'missing','quantity':1}],[{'sku':'book','quantity':1},{'sku':'book','quantity':1}]):
            before=state(p.db);success(p.create(items=items)[0]==400 and state(p.db)==before)
        before=state(p.db);success(p.create(order='unpaid')[0]==409 and state(p.db)==before)
        valid=dict(order_id='o1',request_key='bad',reason='test',items=[dict(sku='book',quantity=1)])
        for changes in ({'reason':''},{'request_key':True},{'unknown':1},{'order_id':42}):
            before=state(p.db);success(p.req('POST','/v2/returns',dict(valid,**changes))[0]==400 and state(p.db)==before)
        success(p.create()[0]==201)
    elif key=='reservation':
        success(p.create(qty=2)[0]==201);before=state(p.db)
        success(p.create('k2',qty=2)[0]==409 and state(p.db)==before)
        success(p.create('k3',qty=1)[0]==201)
    elif key=='idempotency':
        a=p.create();before=state(p.db);b=p.create()
        success(a[0]==201 and b[0]==200 and core(a[1])==core(b[1]) and state(p.db)==before)
        success(p.create(qty=2)[0]==409 and state(p.db)==before)
        success(p.create(token='beta:customer:bob')[0]==201)
        items=[dict(sku='book',quantity=1),dict(sku='pen',quantity=1)]
        a=p.create('multi-key',order='multi',items=items);before=state(p.db)
        b=p.create('multi-key',order='multi',items=list(reversed(items)))
        success(a[0]==201 and b[0]==200 and core(a[1])==core(b[1]) and state(p.db)==before)
    elif key=='cancel':
        _,r=p.create(qty=3);success(p.action(r['id'],'cancel')[1]['status']=='cancelled')
        before=state(p.db);success(p.action(r['id'],'cancel')[0]==200 and state(p.db)==before)
        success(p.create('again',3)[0]==201)
    elif key=='approve':
        _,r=p.create();before=state(p.db);success(p.action(r['id'],'receive')[0]==409 and state(p.db)==before)
        success(p.action(r['id'],'approve')[1]['status']=='approved')
        before=state(p.db);success(p.action(r['id'],'approve')[0]==200 and state(p.db)==before)
        success(p.action(r['id'],'cancel')[0]==409)
    elif key=='reject':
        _,r=p.create(qty=3);p.action(r['id'],'approve');success(p.action(r['id'],'reject')[1]['status']=='rejected')
        success(p.create('again',3)[0]==201);success(p.action(r['id'],'receive')[0]==409)
    elif key=='receive':
        _,r=p.create(qty=2);p.action(r['id'],'approve');success(p.action(r['id'],'receive')[1]['status']=='received')
        with sqlite3.connect(p.db) as c:success(c.execute("SELECT on_hand FROM inventory WHERE tenant='alpha' AND sku='book'").fetchone()[0]==12)
        before=state(p.db);success(p.action(r['id'],'receive')[0]==200 and state(p.db)==before)
    elif key=='settle':
        _,r=p.create();p.action(r['id'],'approve');p.action(r['id'],'receive')
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:p.action(r['id'],'settle'),range(6)))
        success(all(status==200 for status,_ in results));r=results[0][1]
        success(all(core(row)==core(r) for _,row in results))
        before=state(p.db);success(core(p.action(r['id'],'settle')[1])==core(r) and state(p.db)==before)
        entries=p.req('GET','/v2/ledger',token='alpha:finance:alice')[1]['entries']
        success(entries==[{'return_id':r['id'],'amount_cents':333,'currency':'PLN'}])
    elif key=='rounding':
        amounts=[p.complete('part'+str(i))['refund_cents'] for i in range(3)]
        success(amounts==([333,334,334] if variant else [333,333,334]),str(amounts))
    elif key=='partials':
        a=p.complete('p1',order='multi',items=[{'sku':'book','quantity':1},{'sku':'pen','quantity':1}])
        b=p.complete('p2',order='multi',items=[{'sku':'book','quantity':2},{'sku':'pen','quantity':1}])
        success(a['refund_cents']==483 and b['refund_cents']==818)
        success(p.create('excess',order='multi')[0]==409)
    elif key in ('concurrency','concurrent_key'):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda i:p.create('one' if key=='concurrent_key' else str(i),qty=3),range(6)))
        statuses=sorted(r[0] for r in results)
        success(statuses==([200]*5+[201] if key=='concurrent_key' else [201]+[409]*5),str(statuses))
        success(len(p.req('GET','/v2/returns?order_id=o1')[1]['returns'])==1)
    elif key=='isolation':
        _,r=p.create();before=state(p.db)
        for actor in ('beta:customer:bob','beta:support:bob','alpha:customer:mallory'):
            success(p.req('GET','/v2/returns/'+r['id'],token=actor)[0]==404)
            success(p.action(r['id'],'approve',actor)[0]==404)
        success(p.create('bad',token='alpha:customer:mallory')[0]==404 and state(p.db)==before)
        success(p.req('GET','/v1/orders/o1',token='alpha:customer:mallory')[0]==404)
        success(p.req('GET','/v2/returns?order_id=o1',token='alpha:customer:mallory')[0]==404)
    elif key=='roles':
        _,r=p.create()
        for action,correct in [('approve','support'),('receive','warehouse'),('settle','finance')]:
            for role in ('customer','support','warehouse','finance'):
                if role==correct:continue
                before=state(p.db);success(p.action(r['id'],action,f'alpha:{role}:alice')[0]==403 and state(p.db)==before)
            success(p.action(r['id'],action)[0]==200)
        for role in ('customer','support','warehouse'):
            success(p.req('GET','/v2/refunds.csv',token=f'alpha:{role}:alice')[0]==403)
            success(p.req('GET','/v2/ledger',token=f'alpha:{role}:alice')[0]==403)
        for role in ('support','warehouse','finance'):
            before=state(p.db);success(p.create('staff-key',token=f'alpha:{role}:alice')[0]==403 and state(p.db)==before)
        success(p.req('GET','/v1/orders/o1',token='invalid')[0]==401)
    elif key=='flag':
        _,r=p.create();p.start(enabled=False);before=state(p.db)
        success(p.create('disabled')[0]==503 and p.action(r['id'],'approve')[0]==503 and state(p.db)==before)
        success(p.req('GET','/v2/returns/'+r['id'])[0]==200 and p.req('GET','/v1/orders/o1')[0]==200)
        p.start();success(p.action(r['id'],'approve')[0]==200)
    elif key=='audit':
        r=p.complete();p.action(r['id'],'settle');p.create()
        events=p.req('GET',f'/v2/returns/{r["id"]}/events')[1]['events']
        success([x['action'] for x in events]==['create','approve','receive','settle'])
        success([x['actor'] for x in events]==['alpha:customer:alice','alpha:support:alice','alpha:warehouse:alice','alpha:finance:alice'])
    elif key=='export':
        r=p.complete();p.create('pending')
        status,raw=p.req('GET','/v2/refunds.csv',token='alpha:finance:alice')
        rows=list(csv.DictReader(io.StringIO(raw)))
        success(status==200 and rows==[dict(return_id=r['id'],order_id='o1',currency='PLN',refund_cents='333',reason='Too small, "quoted"\nreason')])
        success(len(list(csv.DictReader(io.StringIO(p.req('GET','/v2/refunds.csv',token='beta:finance:bob')[1]))))==0)
    elif key=='client':
        def cli(token,*args):return child([sys.executable,str(p.artifact),'client',p.base,token,*args],p.root)
        rc,out,err=cli('alpha:customer:alice','create','o1','client-key','Client reason','book','1');success(rc==0,err);r=json.loads(out)
        for action,role in [('approve','support'),('receive','warehouse'),('settle','finance')]:
            rc,out,err=cli(f'alpha:{role}:alice','action',r['id'],action);success(rc==0,err)
        rc,out,_=cli('alpha:customer:alice','get',r['id']);success(rc==0 and json.loads(out)['status']=='refunded')
        rc,out,_=cli('alpha:customer:alice','list','o1');success(rc==0 and len(json.loads(out)['returns'])==1)
        rc,out,_=cli('alpha:finance:alice','export');success(rc==0 and len(list(csv.DictReader(io.StringIO(out))))==1)
        success(cli('alpha:customer:alice','action',r['id'],'settle')[0]!=0)
    elif key=='legacy_client':
        path=p.root/'legacy.py';path.write_bytes((TASK/'starter/clients/legacy.py').read_bytes());os.chown(path,1001,1001)
        rc,out,_=child([sys.executable,str(path),p.base,'alpha:customer:alice','o1'],p.root)
        success(rc==0 and json.loads(out)==expected_order(p))
    elif key=='restart':
        r=p.complete();before=state(p.db);p.start(migrate=True)
        success(core(p.req('GET','/v2/returns/'+r['id'])[1])==core(r) and core(p.create()[1])==core(r) and state(p.db)==before)
    else:raise ValueError('unknown test '+key)


def evaluate(artifact,scope=None,public=False):
    rows=[]
    stages=json.loads((TASK/'requirements.json').read_text())['stages']
    for row in stages:
        if row['group']=='release' or scope and row['group']!=scope:continue
        variants=[0] if public or row['key'] not in ('migration','create','rounding','reservation','idempotency') else [0,1]
        for variant in variants:
            p=None
            try:
                p=Product(artifact,variant=variant)
                check(p,row['key'],variant);passed=True;detail=''
            except (AssertionError,ValueError,KeyError,TypeError,IndexError,OSError,subprocess.TimeoutExpired) as exc:passed=False;detail=f'{type(exc).__name__}: {exc}'[:200]
            finally:
                if p:p.close()
            rows.append(dict(id=row['id'],case=row['key']+('/variant' if variant else ''),passed=passed,detail=detail))
    return rows


def retained_proof(p,rid):
    status,row=p.req('GET','/v2/returns/'+rid)
    success(status==200 and row['status']=='refunded' and row['refund_cents']==333)
    entries=p.req('GET','/v2/ledger',token='alpha:finance:alice')[1]['entries']
    matching=[x for x in entries if x['return_id']==rid]
    success(matching==[dict(return_id=rid,amount_cents=333,currency='PLN')])
    with sqlite3.connect(p.db) as c:inventory=c.execute("SELECT on_hand FROM inventory WHERE tenant='alpha' AND sku='book'").fetchone()[0]
    success(inventory==11)
    check(p,'legacy_client',0)
    # Retry after restart must return the original refund, with no extra effects.
    before=state(p.db)
    replay=p.create('release-proof')
    success(replay[0]==200 and core(replay[1])==core(row) and state(p.db)==before)
    return {'return':core(row),'ledger':matching,'inventory':inventory,'legacy_ok':True}


def release_journey(p):
    status,row=p.create('release-proof');success(status in (200,201))
    for current,action in [('requested','approve'),('approved','receive'),('received','settle')]:
        if row['status']==current:
            status,row=p.action(row['id'],action);success(status==200)
    return retained_proof(p,row['id'])
