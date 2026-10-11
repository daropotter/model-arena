import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def run(args):
    try:
        base,token,verb,*rest=args
        body=None
        if verb=='create':
            oid,key,reason,*pairs=rest
            if len(pairs)%2:raise ValueError('unpaired item')
            body=dict(order_id=oid,request_key=key,reason=reason,items=[dict(sku=pairs[i],quantity=int(pairs[i+1])) for i in range(0,len(pairs),2)])
            path='/v2/returns'
        elif verb=='get':path='/v2/returns/'+urllib.parse.quote(rest[0],safe='')
        elif verb=='action':path='/v2/returns/'+urllib.parse.quote(rest[0],safe='')+'/'+rest[1];body={}
        elif verb=='list':path='/v2/returns?'+urllib.parse.urlencode({'order_id':rest[0]})
        elif verb=='export':path='/v2/refunds.csv'
        else:raise ValueError('unknown command')
        request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=10) as response:sys.stdout.write(response.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write(e.read().decode());raise SystemExit(1)
    except (ValueError,IndexError) as e:
        sys.stderr.write(str(e));raise SystemExit(2)
