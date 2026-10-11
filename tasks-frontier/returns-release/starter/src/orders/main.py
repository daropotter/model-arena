import argparse
from .db import migrate
from .server import serve
from .client import run

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    m=s.add_parser('migrate');m.add_argument('--db',required=True)
    v=s.add_parser('serve');v.add_argument('--db',required=True);v.add_argument('--port',type=int,required=True);v.add_argument('--returns',choices=['on','off'],default='on')
    c=s.add_parser('client');c.add_argument('args',nargs=argparse.REMAINDER)
    a=p.parse_args()
    if a.command=='migrate':migrate(a.db)
    elif a.command=='serve':serve(a.db,a.port,a.returns=='on')
    else:run(a.args)
