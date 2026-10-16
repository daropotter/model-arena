"""Audit trail."""


def up(conn):
    conn.execute("""
        CREATE TABLE audit (
            id INTEGER PRIMARY KEY,
            at INTEGER NOT NULL,
            tenant_id INTEGER,
            actor_id INTEGER,
            action TEXT NOT NULL,
            subject TEXT NOT NULL
        )""")
