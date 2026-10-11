"""Existing v1 smoke behavior; deliberately not full v2 acceptance."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    cfg = {'version': 1, 'tenant': 'old',
           'defaults': {'locale': 'en', 'timezone': 'UTC', 'channels': ['email']},
           'contacts': [{'id': 'a', 'enabled': True, 'email': 'a@example.test',
                         'sms': None, 'push': None, 'channels': None,
                         'locale': None, 'timezone': None}]}
    event = {'tenant': 'old', 'id': 'e', 'audience': ['a'],
             'subject': 'Hello', 'body': 'World', 'urgent': False}
    (folder/'cfg.json').write_text(json.dumps(cfg))
    (folder/'event.json').write_text(json.dumps(event))
    out = folder/'out.json'
    p = subprocess.run([sys.executable, '-m', 'dispatch', 'route',
                        str(folder/'cfg.json'), str(folder/'event.json'), str(out)],
                       cwd=root, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    data = json.loads(out.read_text())
    assert len(data) == 1 and data[0]['destination'] == 'a@example.test'
print('visible v1 smoke passed')
