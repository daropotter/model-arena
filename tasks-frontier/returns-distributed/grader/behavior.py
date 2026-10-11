"""Independent probes of HTTP API, separate worker process, Node/Python clients."""
import base64
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import zipfile
import legacy as old
from provider import Provider

TASK=Path(__file__).resolve().parents[1]
GROUPS=(*old.GROUPS,'outbox','payments','clients')
COMPONENTS=('orders.pyz','worker.pyz','refunds.mjs','payment-contract.json')
state=old.state;own=old.own;child=old.child;core=old.core;success=old.success


def sha(raw):return hashlib.sha256(raw).hexdigest()
def pack(parts):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,raw in sorted(parts.items()):
            info=zipfile.ZipInfo(name,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,raw)
    return out.getvalue()


def unpack(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if set(z.namelist())!=set(COMPONENTS) or len(z.namelist())!=len(COMPONENTS) or any(i.file_size>1_000_000 for i in z.infolist()):raise ValueError('invalid release bundle')
        return {n:z.read(n) for n in COMPONENTS}


def build(snapshot):
    with tempfile.TemporaryDirectory(prefix='distributed-build-',dir='/checks') as tmp:
        project=Path(tmp)/'project';shutil.copytree(snapshot,project);own(Path(tmp))
        rc,out,err=child([sys.executable,'build.py'],project)
        if rc:raise ValueError('build failed: '+err[-600:])
        parts={}
        for name in COMPONENTS:
            p=project/'dist'/name
            if (project/'dist').is_symlink() or p.is_symlink() or not p.is_file() or p.stat().st_size>1_000_000:raise ValueError('missing/unsafe component '+name)
            parts[name]=p.read_bytes()
        return pack(parts)


def contract2(seed='standalone'):
    suffix=sha(seed.encode())[:10]
    return {'protocol':2,'merchants':{'alpha':'merchant-a-'+suffix,'beta':'merchant-b-'+suffix},'signing_key':'synthetic-test-key-'+suffix}


class Product(old.Product):
    def __init__(self,bundle,variant=0,migrate=True,database=None,contract=None):
        self.parts=unpack(bundle);self.contract=json.loads(self.parts['payment-contract.json'])
        self.provider=Provider(contract or self.contract)
        try:super().__init__(self.parts['orders.pyz'],variant,migrate,database)
        except BaseException:self.provider.close();raise

    def start(self,enabled=True,artifact=None,migrate=False):
        if artifact is not None:
            self.parts=unpack(artifact);self.contract=json.loads(self.parts['payment-contract.json'])
        super().start(enabled=enabled,artifact=self.parts['orders.pyz'],migrate=migrate)
        for name,raw in self.parts.items():
            if name=='orders.pyz':continue
            p=self.root/name;p.write_bytes(raw);os.chown(p,1001,1001)

    def close(self):
        super().close();self.provider.close()

    def command(self,now=100):
        return [sys.executable,str(self.root/'worker.pyz'),'--db',str(self.db),'--provider',self.provider.url,'--contract',str(self.root/'payment-contract.json'),'--now',str(now),'--once']

    def worker(self,now=100):
        rc,out,err=child(self.command(now),self.root)
        success(rc==0,'worker failed: '+err)
        return json.loads(out)

    def spawn_worker(self,now=100):
        return subprocess.Popen(self.command(now),cwd=self.root,env={'PATH':'/usr/local/bin:/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},user=1001,group=1001,extra_groups=[],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)

    def raw_action(self,rid,action,token=None):return super().action(rid,action,token)

    def action(self,rid,action,token=None):
        status,row=self.raw_action(rid,action,token)
        if action=='settle' and status==202:
            success(row['status']=='pending_refund' and row['refund_cents']==0)
            self.worker()
            return self.req('GET','/v2/returns/'+rid,token=token or 'alpha:finance:alice')
        return status,row

    def queued(self,key='k1',qty=1,order='o1'):
        status,row=self.create(key,qty,order);success(status==201)
        for action in ('approve','receive'):
            status,row=self.raw_action(row['id'],action);success(status==200)
        status,row=self.raw_action(row['id'],'settle');success(status==202 and row['status']=='pending_refund')
        return row

    def payout(self,rid):
        status,row=self.req('GET','/v3/payouts/'+rid,token='alpha:finance:alice');success(status==200)
        return row


def check(p,key,variant,phase):
    if key=='migration':
        now=state(p.db);success(now['version']==(2 if phase==1 else 3))
        success(all(now['tables'].get(k)==v for k,v in p.initial_state['tables'].items()))
        success(p.req('GET','/v1/orders/o1')==(200,old.expected_order(p)))
    elif key=='migration_repeat':
        before=state(p.db);success(before['version']==(2 if phase==1 else 3))
        rc,_,_=child([sys.executable,str(p.artifact),'migrate','--db',str(p.db)],p.root)
        success(rc==0 and state(p.db)==before)
    elif key=='settle':
        r=p.queued();before=p.payout(r['id']);success(before['amount_cents']==333 and before['state']=='queued')
        success(p.provider.snapshot()==[])
        p.worker();r=p.req('GET','/v2/returns/'+r['id'])[1];success(r['status']=='refunded' and r['refund_cents']==333)
        db=state(p.db);p.worker();success(state(p.db)==db and len(p.provider.snapshot())==1)
        success(p.raw_action(r['id'],'settle')[0]==200)
    elif key=='audit':
        r=p.complete();p.action(r['id'],'settle');p.create()
        events=p.req('GET',f'/v2/returns/{r["id"]}/events')[1]['events']
        success([x['action'] for x in events]==['create','approve','receive','settle','paid'])
        success([x['actor'] for x in events][-2:]==['alpha:finance:alice','alpha:worker:payouts'])
    elif key=='client':
        def cli(token,*args):return child([sys.executable,str(p.artifact),'client',p.base,token,*args],p.root)
        rc,out,err=cli('alpha:customer:alice','create','o1','client-key','Client reason','book','1');success(rc==0,err);r=json.loads(out)
        for action,role in [('approve','support'),('receive','warehouse'),('settle','finance')]:
            rc,out,err=cli(f'alpha:{role}:alice','action',r['id'],action);success(rc==0,err)
        success(json.loads(out)['status']=='pending_refund');p.worker()
        rc,out,_=cli('alpha:customer:alice','get',r['id']);success(rc==0 and json.loads(out)['status']=='refunded')
        rc,out,_=cli('alpha:customer:alice','list','o1');success(rc==0 and len(json.loads(out)['returns'])==1)
        rc,out,_=cli('alpha:finance:alice','export');success(rc==0 and 'Client reason' in out)
    elif key=='queue_atomic':
        one=p.queued('one');two=p.queued('two',qty=2)
        jobs=[p.payout(r['id']) for r in (one,two)]
        success([x['amount_cents'] for x in jobs]==[333,667] and len({x['provider_key'] for x in jobs})==2)
        before=state(p.db)
        success(p.raw_action(one['id'],'settle')[0]==202 and state(p.db)==before)
        success(p.provider.snapshot()==[] and p.req('GET','/v2/ledger',token='alpha:finance:alice')[1]['entries']==[])
        success(p.create('over')[0]==409)
        p.worker();p.worker();success(sum(x['amount_cents'] for x in p.provider.snapshot())==1000)
    elif key=='offline':
        r=p.queued();p.provider.mode='offline';p.worker(100)
        job=p.payout(r['id']);success(job['state']=='queued' and job['attempts']==1 and job['next_attempt']==105)
        success(p.provider.snapshot()==[] and p.req('GET','/v2/returns/'+r['id'])[1]['refund_cents']==0)
        p.start(migrate=True);p.provider.mode='healthy';p.worker(105)
        success(p.payout(r['id'])['state']=='paid')
    elif key=='lost_reply':
        r=p.queued();key0=p.payout(r['id'])['provider_key'];p.provider.mode='drop_once';p.worker(100)
        success(len(p.provider.snapshot())==1 and p.payout(r['id'])['state']=='queued')
        p.start();p.worker(105);job=p.payout(r['id'])
        success(job['state']=='paid' and job['provider_key']==key0 and len(p.provider.snapshot())==1)
    elif key=='crash' and variant:
        r=p.queued();p.provider.mode='hold_first';p.provider.release_reply.clear();proc=p.spawn_worker(100)
        try:
            success(p.provider.accepted.wait(4),'first worker never reached provider')
            p.worker(131)
            success(p.payout(r['id'])['state']=='paid','later lease owner did not complete')
            before=state(p.db);p.provider.release_reply.set()
            _,err=proc.communicate(timeout=5);success(proc.returncode==0,err.decode(errors='replace'))
            success(state(p.db)==before,'stale owner rewrote later acknowledgment or audit')
            success(len(p.provider.snapshot())==1)
        finally:
            p.provider.release_reply.set()
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.communicate(timeout=5)
    elif key=='crash':
        r=p.queued();p.provider.release_reply.clear();proc=p.spawn_worker(100)
        try:
            success(p.provider.accepted.wait(4),'worker never reached provider')
            # Network I/O must not hold the write transaction and block API work.
            started=time.monotonic();success(p.create('unrelated',order='multi')[0]==201 and time.monotonic()-started<2,'worker holds DB write lock during network call')
            job=p.payout(r['id']);success(job['state']=='processing' and job['lease_until']==130)
        finally:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.communicate(timeout=5);p.provider.release_reply.set()
        calls=len(p.provider.calls);p.worker(129);success(len(p.provider.calls)==calls)
        p.worker(131);success(p.payout(r['id'])['state']=='paid' and len(p.provider.snapshot())==1)
    elif key=='workers':
        rows=[p.queued('parallel-'+str(i)) for i in range(3)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda _:p.worker(100),range(6)))
        success(all(p.payout(r['id'])['state']=='paid' for r in rows))
        success(len(p.provider.snapshot())==3 and sum(x['amount_cents'] for x in p.provider.snapshot())==1000)
    elif key=='retry':
        r=p.queued();p.provider.mode='offline'
        for now,next_time in ((100,105),(105,115)):
            p.worker(now);job=p.payout(r['id']);success(job['next_attempt']==next_time and job['state']=='queued')
            calls=len(p.provider.calls);p.worker(next_time-1);success(len(p.provider.calls)==calls)
        p.worker(115);job=p.payout(r['id']);success(job['state']=='dead' and job['attempts']==3)
        calls=len(p.provider.calls);p.worker(200);success(len(p.provider.calls)==calls)
        p.provider.mode='healthy'
        status,_=p.req('POST','/v3/payouts/'+r['id']+'/retry',{},'alpha:finance:alice');success(status==200)
        p.worker(201);success(p.payout(r['id'])['state']=='paid' and p.payout(r['id'])['provider_key']==job['provider_key'])
    elif key=='decline':
        r=p.queued(qty=3);p.provider.mode='decline';p.worker(100)
        success(p.payout(r['id'])['state']=='dead' and p.provider.snapshot()==[])
        success(p.create('over')[0]==409)
        with sqlite3.connect(p.db) as c:success(c.execute("SELECT on_hand FROM inventory WHERE tenant='alpha' AND sku='book'").fetchone()[0]==13)
        before=state(p.db);success(p.req('POST','/v3/payouts/'+r['id']+'/retry',{},'alpha:customer:alice')[0]==403 and state(p.db)==before)
        success(p.req('GET','/v3/payouts/'+r['id'],token='beta:finance:bob')[0]==404)
    elif key=='pagination':
        ids=[]
        for i in range(4):
            _,r=p.create('page-'+str(i));ids.append(r['id']);p.raw_action(r['id'],'cancel')
        status,page=p.req('GET','/v3/returns?order_id=o1&limit=2');success(status==200 and len(page['returns'])==2 and page['next_cursor'])
        cursor=page['next_cursor'];first=[r['id'] for r in page['returns']]
        _,r=p.create('later');p.raw_action(r['id'],'cancel')
        encoded=urllib.parse.quote(cursor,safe='')
        status,page2=p.req('GET','/v3/returns?order_id=o1&limit=2&cursor='+encoded)
        success(status==200 and first+[r['id'] for r in page2['returns']]==sorted(ids) and page2['next_cursor'] is None)
        success(p.req('GET','/v3/returns?order_id=o1&limit=2&cursor='+encoded,token='beta:customer:bob')[0]==400)
        success(p.req('GET','/v3/returns?order_id=o1&cursor=bad')[0]==400)
    elif key=='node_client':
        def node(token,*args):return child(['node',str(p.root/'refunds.mjs'),p.base,token,*args],p.root)
        rc,out,_=child(['node',str(p.root/'refunds.mjs'),'version'],p.root);success(rc==0 and json.loads(out)['release_abi']==phase)
        rows=[]
        for i in range(3):
            _,r=p.create('node-'+str(i));rows.append(r)
            for action in ('approve','receive'):p.raw_action(r['id'],action)
        rc,out,err=node('alpha:finance:alice','list','o1','1');success(rc==0,err)
        success([r['id'] for r in json.loads(out)['returns']]==sorted(r['id'] for r in rows))
        rc,out,err=node('alpha:finance:alice','settle',rows[0]['id']);success(rc==0 and json.loads(out)['status']=='pending_refund',err)
        p.worker();rc,out,_=node('alpha:finance:alice','get',rows[0]['id']);success(rc==0 and json.loads(out)['state']=='paid')
        rc,out,_=node('alpha:finance:alice','export');success(rc==0 and rows[0]['id'] in out)
    elif key=='wire':
        success(p.req('GET','/health')[1].get('release_abi')==phase)
        rc,out,err=child([sys.executable,str(p.root/'worker.pyz'),'--version'],p.root);success(rc==0 and json.loads(out)['release_abi']==phase,err)
        p.complete();status,r=p.create('beta-pay',token='beta:customer:bob');success(status==201)
        for action,role in [('approve','support'),('receive','warehouse'),('settle','finance')]:
            status,_=p.raw_action(r['id'],action,f'beta:{role}:bob');success(status in (200,202))
        p.worker();success(len(p.provider.snapshot())==2 and {x['tenant'] for x in p.provider.snapshot()}=={'alpha','beta'})
        success(all(x.get('protocol')==phase for x in p.provider.calls))
    else:old.check(p,key,variant)


def evaluate(bundle,scope=None,public=False,phase=2,contract=None):
    rows=[]
    for stage in json.loads((TASK/'requirements.json').read_text())['stages']:
        if stage['group']=='release' or scope and stage['group']!=scope:continue
        variants=[0,1] if stage['key']=='crash' or not public and stage['key'] in ('migration','create','rounding','reservation','idempotency') else [0]
        for variant in variants:
            p=None
            try:
                p=Product(bundle,variant=variant,contract=contract or ({'protocol':1} if phase==1 else contract2()))
                check(p,stage['key'],variant,phase);passed=True;detail=''
            except (AssertionError,ValueError,KeyError,TypeError,IndexError,OSError,sqlite3.Error,subprocess.TimeoutExpired) as exc:passed=False;detail=f'{type(exc).__name__}: {exc}'[:300]
            finally:
                if p:p.close()
            rows.append(dict(id=stage['id'],case=stage['key']+('/variant' if variant else ''),passed=passed,detail=detail))
    return rows


def release_prepare(p):
    """Resume the reserved HTTP requests; never reset the deployed database."""
    rows=[]
    for key in ('release-paid','release-pending'):
        status,row=p.create(key);success(status in (200,201),str(row))
        for state0,action in [('requested','approve'),('approved','receive'),('received','settle')]:
            if row['status']==state0:
                status,row=p.raw_action(row['id'],action);success(status in (200,202),str(row))
        if key=='release-paid' and row['status']=='pending_refund':p.worker()
        rows.append(row['id'])
    paid,pending=rows
    success(p.req('GET','/v2/returns/'+paid)[1]['status']=='refunded')
    success(p.req('GET','/v2/returns/'+pending)[1]['status']=='pending_refund')
    proof=release_proof(p,rows)
    success(len(proof['provider'])==1 and proof['jobs'][0]['state']=='paid' and proof['jobs'][1]['state']=='queued')
    success([j['amount_cents'] for j in proof['jobs']]==[333,333])
    return proof


def release_proof(p,ids):
    rows=[core(p.req('GET','/v2/returns/'+rid)[1]) for rid in ids]
    jobs=[p.payout(rid) for rid in ids]
    ledger=p.req('GET','/v2/ledger',token='alpha:finance:alice')[1]['entries']
    with sqlite3.connect(p.db) as c:stock=c.execute("SELECT on_hand FROM inventory WHERE tenant='alpha' AND sku='book'").fetchone()[0]
    return dict(ids=ids,returns=rows,jobs=[{k:j[k] for k in ('return_id','amount_cents','currency','provider_key','state','provider_receipt')} for j in jobs],ledger=ledger,stock=stock,provider=p.provider.snapshot())


def release_drain(p,before):
    success(release_proof(p,before['ids'])==before,'upgrade changed paid/pending data')
    p.worker(100);after=release_proof(p,before['ids'])
    success(all(r['status']=='refunded' and r['refund_cents']==333 for r in after['returns']))
    success(all(j['state']=='paid' for j in after['jobs']) and len(after['ledger'])==2 and after['stock']==12)
    success(len(after['provider'])==2 and sum(x['amount_cents'] for x in after['provider'])==666)
    success(all(x in after['provider'] for x in before['provider']))
    success(all(a['provider_key']==b['provider_key'] and a['amount_cents']==b['amount_cents'] for a,b in zip(after['jobs'],before['jobs'])))
    success(p.provider.calls[-1].get('protocol')==2,'old queued payment did not use ABI2')
    snapshot=state(p.db);p.worker(200)
    success(state(p.db)==snapshot and release_proof(p,before['ids'])==after,'drain replay changed state')
    return after


def release_smoke(p,expected):
    success(release_proof(p,expected['ids'])==expected,'retained journey differs')
    before=state(p.db)
    for rid in expected['ids']:success(p.raw_action(rid,'settle')[0]==200)
    p.worker(300);old.check(p,'legacy_client',0)
    for rid in expected['ids']:
        rc,out,err=child([sys.executable,str(p.artifact),'client',p.base,'alpha:customer:alice','get',rid],p.root)
        success(rc==0 and json.loads(out)['status']=='refunded',err)
    rc,out,err=child(['node',str(p.root/'refunds.mjs'),p.base,'alpha:finance:alice','list','o1','1'],p.root)
    success(rc==0 and sorted(r['id'] for r in json.loads(out)['returns'])==sorted(expected['ids']),err)
    success(state(p.db)==before and release_proof(p,expected['ids'])==expected,'smoke changed financial data')
    return expected
