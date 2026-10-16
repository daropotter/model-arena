"""Payments against invoices."""


def up(conn):
    conn.execute("""
        CREATE TABLE payments (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            invoice_id INTEGER NOT NULL REFERENCES invoices(id),
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed')),
            idempotency_key TEXT NOT NULL UNIQUE,
            gateway_charge_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )""")
