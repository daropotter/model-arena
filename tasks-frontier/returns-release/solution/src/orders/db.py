import sqlite3


def connect(path):
    c=sqlite3.connect(path,timeout=15,isolation_level=None)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def migrate(path):
    c=connect(path)
    try:
        c.execute('BEGIN IMMEDIATE')
        version=c.execute('PRAGMA user_version').fetchone()[0]
        if version not in (1,2):raise ValueError('unsupported schema')
        c.execute('CREATE TABLE IF NOT EXISTS returns (tenant TEXT,id TEXT,order_id TEXT,customer TEXT,request_key TEXT,payload TEXT,reason TEXT,status TEXT,refund_cents INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant,id),UNIQUE(tenant,customer,request_key))')
        c.execute('CREATE TABLE IF NOT EXISTS return_items (tenant TEXT,return_id TEXT,sku TEXT,quantity INTEGER,PRIMARY KEY(tenant,return_id,sku))')
        c.execute('CREATE TABLE IF NOT EXISTS refund_ledger (tenant TEXT,return_id TEXT,amount_cents INTEGER,currency TEXT,PRIMARY KEY(tenant,return_id))')
        c.execute('CREATE TABLE IF NOT EXISTS return_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,tenant TEXT,return_id TEXT,action TEXT,actor TEXT)')
        c.execute('PRAGMA user_version=2')
        c.commit()
    except BaseException:
        c.rollback();raise
    finally:c.close()
