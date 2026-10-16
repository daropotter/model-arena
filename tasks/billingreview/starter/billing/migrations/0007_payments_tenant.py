"""payments.tenant_id: scope payments directly instead of through
customers. Rebuilds the table (SQLite cannot add a NOT NULL column with a
computed value) and backfills the tenant from the invoice."""

FOREIGN_KEYS_OFF = True  # refunds reference payments(id) during the rebuild


def up(conn):
    conn.execute("""
        CREATE TABLE payments_new (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
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
    conn.execute("""
        INSERT INTO payments_new (id, tenant_id, customer_id, invoice_id, amount_minor,
                                  currency, status, idempotency_key, gateway_charge_id,
                                  attempts, created_at)
        SELECT p.id, i.tenant_id, p.customer_id, p.invoice_id, p.amount_minor,
               p.currency, p.status, p.idempotency_key, p.gateway_charge_id,
               p.attempts, p.created_at
        FROM payments p JOIN invoices i ON i.id = p.invoice_id""")
    conn.execute("DROP TABLE payments")
    conn.execute("ALTER TABLE payments_new RENAME TO payments")
    conn.execute("CREATE INDEX payments_tenant ON payments(tenant_id, invoice_id)")
