"""Tenants, users, customers and invoices."""


def up(conn):
    conn.execute("""
        CREATE TABLE tenants (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            base_currency TEXT NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('viewer', 'billing', 'admin')),
            is_staff INTEGER NOT NULL DEFAULT 0,
            api_key_hash TEXT NOT NULL UNIQUE
        )""")
    conn.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            gateway_ref TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE invoices (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            number TEXT NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'open', 'paid', 'void')),
            total_minor INTEGER NOT NULL DEFAULT 0,
            paid_minor INTEGER NOT NULL DEFAULT 0,
            due_date TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            UNIQUE (tenant_id, number)
        )""")
    conn.execute("""
        CREATE TABLE invoice_lines (
            id INTEGER PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id),
            description TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price_minor INTEGER NOT NULL
        )""")
