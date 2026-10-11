import json

class Problem(Exception):
    def __init__(self,status,code):self.status,self.code=status,code

def order(c,tenant,oid):
    row=c.execute('SELECT * FROM orders WHERE tenant=? AND id=?',(tenant,oid)).fetchone()
    if row is None:raise Problem(404,'not_found')
    return dict(row)

def public_order(c,tenant,oid):
    row=order(c,tenant,oid)
    return {k:row[k] for k in ('id','status','currency','total_cents')}

def dispatch(c,method,path,query,body,actor,enabled):
    tenant,role,user=actor
    parts=path.strip('/').split('/')
    if method=='GET' and len(parts)==3 and parts[:2]==['v1','orders']:
        return 200,public_order(c,tenant,parts[2])
    raise Problem(404,'not_found')
