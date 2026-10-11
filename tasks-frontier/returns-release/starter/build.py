"""Build only src/ into a deterministic standalone application. No dependencies."""
import pathlib,zipfile
root=pathlib.Path(__file__).parent
out=root/'dist/orders.pyz';out.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    entries={'__main__.py':b'from orders.main import main\nmain()\n'}
    entries.update({str(p.relative_to(root/'src')):p.read_bytes() for p in (root/'src').rglob('*.py')})
    for name,raw in sorted(entries.items()):
        i=zipfile.ZipInfo(name,date_time=(2020,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED
        i.external_attr=0o644<<16;z.writestr(i,raw)
print(out)
