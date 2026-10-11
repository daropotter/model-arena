import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from .db import connect
from .domain import dispatch,Problem

def serve(db,port,enabled=True):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self):
            try:
                url=urlparse(self.path)
                if url.path=='/health':status,data=200,{'ok':True}
                else:
                    # Synthetic local exercise identities, not real credentials.
                    actor=self.headers.get('Authorization','').removeprefix('Bearer ').split(':')
                    if len(actor)!=3 or actor[0] not in ('alpha','beta') or actor[1] not in ('customer','support','warehouse','finance'):
                        raise Problem(401,'unauthorized')
                    body=None
                    if self.command=='POST':
                        try:body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                        except (ValueError,TypeError):raise Problem(400,'invalid_json')
                    c=connect(db)
                    try:status,data=dispatch(c,self.command,url.path,parse_qs(url.query),body,actor,enabled)
                    finally:c.close()
                raw=data.encode() if isinstance(data,str) else json.dumps(data,ensure_ascii=False).encode()
                content='text/csv; charset=utf-8' if isinstance(data,str) else 'application/json'
            except Problem as e:status,raw,content=e.status,json.dumps({'error':e.code}).encode(),'application/json'
            except Exception:status,raw,content=500,b'{"error":"internal"}','application/json'
            self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        do_GET=respond
        do_POST=respond
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
