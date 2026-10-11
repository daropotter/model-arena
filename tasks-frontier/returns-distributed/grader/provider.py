"""Local payment fixture owned by the grader. Candidate cannot reset its ledger."""
import hashlib
import hmac
import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer


class Provider:
    def __init__(self,contract,serve=True):
        self.contract=contract;self.mode='healthy';self.lock=threading.Lock()
        self.entries={};self.calls=[];self.attempts={}
        self.accepted=threading.Event();self.release_reply=threading.Event();self.release_reply.set()
        self.server=None
        if not serve:return
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                status,value,drop,block=owner.handle(self.path,self.rfile.read(int(self.headers.get('Content-Length','0'))),self.headers)
                if block:owner.release_reply.wait(8)
                if drop:
                    self.close_connection=True
                    try:self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
                    return
                raw=json.dumps(value).encode()
                try:
                    self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=0.05),daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def handle(self,path,raw,headers):
        with self.lock:
            try:
                data=json.loads(raw);protocol=self.contract['protocol']
                if protocol==1:
                    assert path=='/refunds' and set(data)=={'tenant','key','amount_cents','currency'}
                    tenant,key,amount,currency=data['tenant'],data['key'],data['amount_cents'],data['currency']
                    assert type(amount) is int and amount>0 and tenant in ('alpha','beta')
                else:
                    assert path=='/v2/refunds' and set(data)=={'merchant','request_id','money'}
                    expected=hmac.new(self.contract['signing_key'].encode(),raw,hashlib.sha256).hexdigest()
                    assert hmac.compare_digest(headers.get('X-Signature',''),expected)
                    tenant=next(t for t,m in self.contract['merchants'].items() if m==data['merchant'])
                    key=data['request_id'];money=data['money'];assert set(money)=={'value','currency'}
                    assert isinstance(money['value'],str) and re.fullmatch(r'(0|[1-9][0-9]*)\.[0-9]{2}',money['value'])
                    units,cents=money['value'].split('.');amount=int(units)*100+int(cents);currency=money['currency']
                    assert amount>0
                assert isinstance(key,str) and key.startswith(tenant+'/') and currency in ('PLN','EUR')
            except (AssertionError,KeyError,ValueError,TypeError,StopIteration):
                self.calls.append({'path':path,'accepted':False,'error':'contract'})
                return 400,{'error':'contract'},False,False
            keytuple=(tenant,key);self.attempts[keytuple]=self.attempts.get(keytuple,0)+1
            count=self.attempts[keytuple]
            self.calls.append(dict(path=path,tenant=tenant,key=key,amount_cents=amount,currency=currency,protocol=protocol))
            if keytuple in self.entries:
                row=self.entries[keytuple]
                if row['amount_cents']!=amount or row['currency']!=currency:return 409,{'error':'changed_idempotent_payload'},False,False
            else:
                if self.mode=='offline' or self.mode=='transient' and count<=2:return 503,{'error':'temporarily_unavailable'},False,False
                if self.mode=='decline':return 422,{'error':'declined'},False,False
                row=dict(tenant=tenant,key=key,amount_cents=amount,currency=currency,receipt='payment-'+str(len(self.entries)+1))
                self.entries[keytuple]=row;self.accepted.set()
            response={'receipt':row['receipt'],'status':'paid'} if protocol==1 else {'result':{'id':row['receipt'],'state':'settled'}}
            return 200,response,self.mode=='drop_once' and count==1,not self.release_reply.is_set() and (self.mode!='hold_first' or count==1)

    def snapshot(self):
        with self.lock:return sorted([dict(x) for x in self.entries.values()],key=lambda r:(r['tenant'],r['key']))

    def close(self):
        self.release_reply.set()
        if self.server:
            self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
