"""Small smoke; the release acceptance contract is broader."""
import subprocess,sys,tempfile,sqlite3
from pathlib import Path
subprocess.run([sys.executable,'build.py'],check=True)
with tempfile.TemporaryDirectory() as tmp:
    db=Path(tmp)/'shop.db'
    with sqlite3.connect(db) as c:c.executescript(Path('fixtures/seed.sql').read_text())
    subprocess.run([sys.executable,'dist/orders.pyz','migrate','--db',str(db)],check=True)
print('visible migration smoke passed')
