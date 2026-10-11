"""Build exactly the manifests selected by the local instance configuration."""
import io
import json
from pathlib import Path
import zipfile


def archive(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    return out.getvalue()


def main():
    dist=Path('dist');dist.mkdir(exist_ok=True)
    routes=json.loads(Path('ops/vhosts.json').read_text())['routes'];trace={}
    for instance in sorted(set(routes.values())):
        cfg=json.loads(Path('instances',instance+'.json').read_text());manifest=json.loads(Path(cfg['manifest']).read_text())
        files={'__main__.py':b'from server import main\nmain()\n','server.py':Path('runtime/server.py').read_bytes(),'application.py':Path(manifest['entry']).read_bytes()}
        inputs=[manifest['entry'],'runtime/server.py']
        for module,root in manifest['modules'].items():
            for path in sorted(Path(root).rglob('*.py')):
                files[module+'/'+str(path.relative_to(root))]=path.read_bytes();inputs.append(str(path))
        (dist/(instance+'.pyz')).write_bytes(archive(files))
        (dist/(instance+'.json')).write_text(json.dumps(cfg,sort_keys=True)+'\n')
        trace[instance]={'manifest':cfg['manifest'],'sources':inputs}
    (dist/'source-map.json').write_text(json.dumps(trace,sort_keys=True)+'\n')
    (dist/'vhosts.json').write_text(json.dumps(routes,sort_keys=True)+'\n')

if __name__=='__main__':main()
