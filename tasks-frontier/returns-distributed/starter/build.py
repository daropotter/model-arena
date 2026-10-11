"""Deterministic multi-component release; each component runs without the checkout."""
from pathlib import Path
import zipfile
root=Path(__file__).parent
out=root/'dist';out.mkdir(exist_ok=True)
def pack(name,entry):
    files={'__main__.py':entry.encode()}
    files.update({str(p.relative_to(root/'src')):p.read_bytes() for p in (root/'src').rglob('*.py')})
    with zipfile.ZipFile(out/name,'w') as z:
        for path,raw in sorted(files.items()):
            info=zipfile.ZipInfo(path,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            z.writestr(info,raw)
pack('orders.pyz','from orders.main import main\nmain()\n')
pack('worker.pyz','from payouts.main import main\nmain()\n')
(out/'refunds.mjs').write_bytes((root/'client/refunds.mjs').read_bytes())
(out/'payment-contract.json').write_bytes((root/'config/payment-contract.json').read_bytes())
print('Built orders.pyz, worker.pyz, refunds.mjs, payment-contract.json')
