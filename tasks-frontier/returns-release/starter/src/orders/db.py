import sqlite3

def connect(path):
    c=sqlite3.connect(path,timeout=10,isolation_level=None)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def migrate(path):
    # Existing installations have schema v1. Implement an additive v2 upgrade.
    c=connect(path)
    try:
        if c.execute('PRAGMA user_version').fetchone()[0]!=1:
            raise ValueError('expected v1 database')
    finally:c.close()
