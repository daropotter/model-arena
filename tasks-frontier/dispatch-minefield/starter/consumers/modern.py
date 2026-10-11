"""Supported v2 consumer: consumes the documented JSON contract."""
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
assert set(data) == {'version', 'tenant', 'recipients'} and data['version'] == 2
assert isinstance(data['recipients'], list)
print(len(data['recipients']))
