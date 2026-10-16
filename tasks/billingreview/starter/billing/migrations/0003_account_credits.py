"""Account credits: prepayments that belong to a customer but to no
invoice yet. payments.invoice_id becomes nullable (SQLite needs a table
rebuild for that); a credit has invoice_id NULL."""


def up(conn):
    conn.execute("""
        CREATE TABLE payments_new (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            invoice_id INTEGER REFERENCES invoices(id),
            amount_minor INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded', 'failed')),
            idempotency_key TEXT NOT NULL UNIQUE,
            gateway_charge_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )""")
    conn.execute("INSERT INTO payments_new SELECT * FROM payments")
    conn.execute("DROP TABLE payments")
    conn.execute("ALTER TABLE payments_new RENAME TO payments")
