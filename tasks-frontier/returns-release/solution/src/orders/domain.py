import csv
import io
import json
import uuid


class Problem(Exception):
    def __init__(self,status,code):self.status,self.code=status,code


def order(c,tenant,oid):
    row=c.execute('SELECT * FROM orders WHERE tenant=? AND id=?',(tenant,oid)).fetchone()
    if row is None:raise Problem(404,'not_found')
    return dict(row)


def allowed_order(c,actor,oid):
    tenant,role,user=actor
    row=order(c,tenant,oid)
    if role=='customer' and row['customer']!=user:raise Problem(404,'not_found')
    return row


def public_order(c,actor,oid):
    row=allowed_order(c,actor,oid)
    return {k:row[k] for k in ('id','status','currency','total_cents')}


def get_return(c,actor,rid):
    tenant,role,user=actor
    row=c.execute('SELECT * FROM returns WHERE tenant=? AND id=?',(tenant,rid)).fetchone()
    if row is None or role=='customer' and row['customer']!=user:raise Problem(404,'not_found')
    return dict(row)


def view(c,row):
    result={k:row[k] for k in ('id','order_id','status','reason','refund_cents')}
    result['items']=[dict(x) for x in c.execute('SELECT sku,quantity FROM return_items WHERE tenant=? AND return_id=? ORDER BY sku',(row['tenant'],row['id']))]
    return result


def event(c,actor,rid,action):
    c.execute('INSERT INTO return_events(tenant,return_id,action,actor) VALUES(?,?,?,?)',(actor[0],rid,action,':'.join(actor)))


def create(c,actor,body):
    tenant,role,user=actor
    if role!='customer':raise Problem(403,'forbidden')
    if not isinstance(body,dict) or set(body)!={'order_id','request_key','reason','items'}:raise Problem(400,'invalid_request')
    if any(not isinstance(body[k],str) or not body[k].strip() or len(body[k])>200 for k in ('order_id','request_key','reason')):raise Problem(400,'invalid_request')
    items=body['items']
    if not isinstance(items,list) or not items:raise Problem(400,'invalid_items')
    seen=set()
    for x in items:
        if not isinstance(x,dict) or set(x)!={'sku','quantity'} or not isinstance(x['sku'],str) or not x['sku'] or type(x['quantity']) is not int or x['quantity']<=0 or x['sku'] in seen:raise Problem(400,'invalid_items')
        seen.add(x['sku'])
    payload=json.dumps(dict(body,items=sorted(items,key=lambda x:x['sku'])),sort_keys=True,separators=(',',':'))
    existing=c.execute('SELECT * FROM returns WHERE tenant=? AND customer=? AND request_key=?',(tenant,user,body['request_key'])).fetchone()
    if existing:
        if existing['payload']!=payload:raise Problem(409,'key_conflict')
        return 200,view(c,dict(existing))
    o=allowed_order(c,actor,body['order_id'])
    if o['status']!='paid':raise Problem(409,'not_paid')
    for x in items:
        line=c.execute('SELECT quantity FROM order_items WHERE tenant=? AND order_id=? AND sku=?',(tenant,o['id'],x['sku'])).fetchone()
        if line is None:raise Problem(400,'invalid_items')
        reserved=c.execute("SELECT COALESCE(SUM(i.quantity),0) FROM return_items i JOIN returns r ON r.tenant=i.tenant AND r.id=i.return_id WHERE r.tenant=? AND r.order_id=? AND i.sku=? AND r.status NOT IN ('cancelled','rejected')",(tenant,o['id'],x['sku'])).fetchone()[0]
        if reserved+x['quantity']>line['quantity']:raise Problem(409,'quantity_exceeded')
    rid='ret-'+uuid.uuid4().hex
    c.execute('INSERT INTO returns(tenant,id,order_id,customer,request_key,payload,reason,status) VALUES(?,?,?,?,?,?,?,?)',(tenant,rid,o['id'],user,body['request_key'],payload,body['reason'],'requested'))
    c.executemany('INSERT INTO return_items VALUES(?,?,?,?)',[(tenant,rid,x['sku'],x['quantity']) for x in items])
    event(c,actor,rid,'create')
    return 201,view(c,get_return(c,actor,rid))


def transition(c,actor,rid,action):
    row=get_return(c,actor,rid);tenant,role,user=actor
    rules={'cancel':('customer',('requested',),'cancelled'),'approve':('support',('requested',),'approved'),'reject':('support',('requested','approved'),'rejected'),'receive':('warehouse',('approved',),'received'),'settle':('finance',('received',),'refunded')}
    if action not in rules:raise Problem(404,'not_found')
    required,states,target=rules[action]
    if role!=required:raise Problem(403,'forbidden')
    if row['status']==target:return 200,view(c,row)
    if row['status'] not in states:raise Problem(409,'invalid_state')
    items=view(c,row)['items'];refund=0
    if action=='receive':
        for x in items:c.execute('UPDATE inventory SET on_hand=on_hand+? WHERE tenant=? AND sku=?',(x['quantity'],tenant,x['sku']))
    if action=='settle':
        for x in items:
            line=c.execute('SELECT quantity,paid_cents FROM order_items WHERE tenant=? AND order_id=? AND sku=?',(tenant,row['order_id'],x['sku'])).fetchone()
            prior=c.execute("SELECT COALESCE(SUM(i.quantity),0) FROM return_items i JOIN returns r ON r.tenant=i.tenant AND r.id=i.return_id WHERE r.tenant=? AND r.order_id=? AND i.sku=? AND r.status='refunded'",(tenant,row['order_id'],x['sku'])).fetchone()[0]
            refund+=(prior+x['quantity'])*line['paid_cents']//line['quantity']-prior*line['paid_cents']//line['quantity']
        currency=order(c,tenant,row['order_id'])['currency']
        c.execute('INSERT INTO refund_ledger VALUES(?,?,?,?)',(tenant,rid,refund,currency))
    c.execute('UPDATE returns SET status=?,refund_cents=? WHERE tenant=? AND id=?',(target,refund,tenant,rid))
    event(c,actor,rid,action)
    return 200,view(c,get_return(c,actor,rid))


def dispatch(c,method,path,query,body,actor,enabled):
    tenant,role,user=actor
    parts=path.strip('/').split('/')
    if method=='GET' and len(parts)==3 and parts[:2]==['v1','orders']:
        return 200,public_order(c,actor,parts[2])
    if parts[:2]==['v2','returns']:
        if method=='POST':
            if not enabled:raise Problem(503,'returns_disabled')
            c.execute('BEGIN IMMEDIATE')
            try:
                if len(parts)==2:result=create(c,actor,body)
                elif len(parts)==4:result=transition(c,actor,parts[2],parts[3])
                else:raise Problem(404,'not_found')
                c.commit();return result
            except BaseException:c.rollback();raise
        if method=='GET':
            if len(parts)==2:
                oid=query.get('order_id',[None])[0]
                if not oid:raise Problem(400,'order_required')
                allowed_order(c,actor,oid)
                return 200,{'returns':[view(c,dict(r)) for r in c.execute('SELECT * FROM returns WHERE tenant=? AND order_id=? ORDER BY id',(tenant,oid))]}
            if len(parts)==3:return 200,view(c,get_return(c,actor,parts[2]))
            if len(parts)==4 and parts[3]=='events':
                get_return(c,actor,parts[2])
                return 200,{'events':[dict(r) for r in c.execute('SELECT action,actor FROM return_events WHERE tenant=? AND return_id=? ORDER BY seq',(tenant,parts[2]))]}
    if method=='GET' and path in ('/v2/refunds.csv','/v2/ledger'):
        if role!='finance':raise Problem(403,'forbidden')
        ledger=[dict(r) for r in c.execute('SELECT return_id,amount_cents,currency FROM refund_ledger WHERE tenant=? ORDER BY return_id',(tenant,))]
        if path=='/v2/ledger':return 200,{'entries':ledger}
        stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
        writer.writerow(['return_id','order_id','currency','refund_cents','reason'])
        for entry in ledger:
            row=get_return(c,actor,entry['return_id'])
            writer.writerow([row['id'],row['order_id'],entry['currency'],entry['amount_cents'],row['reason']])
        return 200,stream.getvalue()
    raise Problem(404,'not_found')
