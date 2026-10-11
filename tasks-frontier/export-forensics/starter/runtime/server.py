import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from application import export


def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--config',required=True);a=p.parse_args()
    with open(a.config) as f:config=json.load(f)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200 if self.path=='/health' else 404);self.end_headers();self.wfile.write(b'{}')
        def do_POST(self):
            try:
                if self.path!=config['path']:
                    self.send_response(404);self.end_headers();return
                payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));data=export(payload,config)
                self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            except (ValueError,TypeError,KeyError):
                self.send_response(400);self.end_headers();self.wfile.write(b'{"error":"invalid payload"}')
    ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
