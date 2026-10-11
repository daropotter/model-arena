"""Existing consumer: the v1 order response is an exact four-field object."""
import json,sys,urllib.request
base,token,oid=sys.argv[1:]
q=urllib.request.Request(base+'/v1/orders/'+oid,headers={'Authorization':'Bearer '+token})
with urllib.request.urlopen(q) as r:value=json.load(r)
assert set(value)=={'id','status','currency','total_cents'}
assert type(value['total_cents']) is int and value['currency']=='PLN'
print(json.dumps(value,sort_keys=True))
