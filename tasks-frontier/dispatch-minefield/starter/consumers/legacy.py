"""Supported v1 consumer: consumes the documented CSV contract."""
import csv
import sys
from pathlib import Path

rows = list(csv.DictReader(Path(sys.argv[1]).open(encoding='utf-8', newline='')))
assert all(set(row) == {'tenant', 'id', 'email', 'locale', 'timezone'} for row in rows)
print(len(rows))
