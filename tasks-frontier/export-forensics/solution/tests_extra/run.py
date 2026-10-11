"""HTTP regression assertions, no access to application sources or grader state."""
import csv,io,json,os,urllib.request,urllib.error

base=os.environ['EXPORT_BASE_URL']
columns=[{'key':k,'label':k} for k in ('id','note','amount','paid','city')]
rows=[{'city':'Łódź; "N"\n新','id':'x','note':'','amount':0,'paid':False},{'id':'y','amount':13,'paid':True,'note':None,'city':'Żory'}]

def request(host,path,payload):
    req=urllib.request.Request(base+'/dispatch',data=json.dumps(dict(host=host,path=path,payload=payload),ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    try:r=urllib.request.urlopen(req,timeout=3)
    except urllib.error.HTTPError as e:r=e
    with r:return r.status,r.read(),r.headers.get('Content-Type','')

def check(host,path,delimiter,bom,sparse=False):
    status,raw,ctype=request(host,path,{'columns':columns,'rows':rows})
    assert status==200 and 'text/csv' in ctype and 'utf-8' in ctype
    expected_rows=[['id','note','amount','paid','city']]
    if sparse:expected_rows += [['x','Łódź; "N"\n新'],['y','13','true','Żory']]
    else:expected_rows += [['x','','0','false','Łódź; "N"\n新'],['y','','13','true','Żory']]
    out=io.StringIO(newline='');csv.writer(out,delimiter=delimiter,lineterminator='\r\n').writerows(expected_rows)
    assert raw==(b'\xef\xbb\xbf' if bom else b'')+out.getvalue().encode(),(host,raw)

check('raporty.novara.test','/exports/orders.csv',';',True)
check('raporty-novara.test','/export.csv',',',False)
check('feed.novara.test','/feeds/sparse.csv','|',False,True)
status,_,_=request('raporty.novara.test','/exports/orders.csv',{'columns':[],'rows':[]});assert status==400
print('All three live contracts checked, including false/zero/empty, Unicode, quoting and sparse compatibility.')
