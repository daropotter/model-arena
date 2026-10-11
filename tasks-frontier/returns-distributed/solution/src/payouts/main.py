"""One leased payout per invocation; intent and provider idempotency survive crashes."""
import argparse
import hashlib
import hmac
import json
import sqlite3
import urllib.error
import urllib.request
from orders.db import connect
from orders.release import ABI


def payload(job,contract):
    key=job['provider_key'];headers={'Content-Type':'application/json'}
    if contract['protocol']==1:
        value={'tenant':job['tenant'],'key':key,'amount_cents':job['amount_cents'],'currency':job['currency']};path='/refunds'
    else:
        amount=job['amount_cents']
        value={'merchant':contract['merchants'][job['tenant']],'request_id':key,'money':{'value':f'{amount//100}.{amount%100:02}','currency':job['currency']}}
        path='/v2/refunds'
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    if contract['protocol']==2:headers['X-Signature']=hmac.new(contract['signing_key'].encode(),raw,hashlib.sha256).hexdigest()
    return path,raw,headers


def once(db,provider,contract,now):
    c=connect(db)
    try:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT * FROM payouts WHERE (state='queued' AND next_attempt<=?) OR (state='processing' AND lease_until<=?) ORDER BY rowid LIMIT 1",(now,now)).fetchone()
        if row is None:c.commit();return {'processed':0}
        job=dict(row);attempt=job['attempts']+1
        c.execute("UPDATE payouts SET state='processing',attempts=?,lease_until=? WHERE tenant=? AND return_id=?",(attempt,now+30,job['tenant'],job['return_id']))
        c.commit()
        receipt=None;permanent=False
        try:
            path,raw,headers=payload(job,contract)
            request=urllib.request.Request(provider+path,data=raw,headers=headers)
            with urllib.request.urlopen(request,timeout=2) as response:value=json.load(response)
            receipt=value['receipt'] if contract['protocol']==1 else value['result']['id']
            if not isinstance(receipt,str) or not receipt:raise ValueError('invalid receipt')
        except urllib.error.HTTPError as e:permanent=400<=e.code<500 and e.code not in (408,429)
        except (OSError,ValueError,KeyError):pass
        c.execute('BEGIN IMMEDIATE')
        current=c.execute('SELECT * FROM payouts WHERE tenant=? AND return_id=?',(job['tenant'],job['return_id'])).fetchone()
        # A later owner may already have recovered this lease.
        if current['state']!='processing' or current['attempts']!=attempt or current['lease_until']!=now+30:
            c.commit();return {'processed':0}
        if receipt:
            c.execute('INSERT OR IGNORE INTO refund_ledger VALUES(?,?,?,?)',(job['tenant'],job['return_id'],job['amount_cents'],job['currency']))
            c.execute("UPDATE returns SET status='refunded',refund_cents=? WHERE tenant=? AND id=?",(job['amount_cents'],job['tenant'],job['return_id']))
            c.execute("UPDATE payouts SET state='paid',lease_until=0,next_attempt=0,provider_receipt=? WHERE tenant=? AND return_id=?",(receipt,job['tenant'],job['return_id']))
            c.execute('INSERT INTO return_events(tenant,return_id,action,actor) VALUES(?,?,?,?)',(job['tenant'],job['return_id'],'paid',job['tenant']+':worker:payouts'))
        else:
            state='dead' if permanent or attempt>=3 else 'queued'
            c.execute('UPDATE payouts SET state=?,lease_until=0,next_attempt=? WHERE tenant=? AND return_id=?',(state,0 if state=='dead' else now+5*(2**(attempt-1)),job['tenant'],job['return_id']))
        c.commit();return {'processed':1}
    except BaseException:c.rollback();raise
    finally:c.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--version',action='store_true');p.add_argument('--db');p.add_argument('--provider');p.add_argument('--contract');p.add_argument('--now',type=int,default=100);p.add_argument('--once',action='store_true')
    a=p.parse_args()
    if a.version:print(json.dumps({'release_abi':ABI}));return
    if not all((a.db,a.provider,a.contract,a.once)):p.error('db, provider, contract and once required')
    with open(a.contract) as f:contract=json.load(f)
    print(json.dumps(once(a.db,a.provider,contract,a.now)))
