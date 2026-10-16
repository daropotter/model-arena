"""Refunds of succeeded payments."""


def up(conn):
    conn.execute("""
        CREATE TABLE refunds (
            id INTEGER PRIMARY KEY,
            payment_id INTEGER NOT NULL REFERENCES payments(id),
            amount_minor INTEGER NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed')),
            reason TEXT NOT NULL,
            gateway_refund_id TEXT,
            created_at INTEGER NOT NULL
        )""")
