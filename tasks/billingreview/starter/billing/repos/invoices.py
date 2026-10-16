from ..models import Invoice
from .base import ScopedRepo


class InvoiceRepo(ScopedRepo):
    table = "invoices"
    row_type = Invoice

    def create(self, ctx, customer_id, number, currency, due_date, now):
        cur = self.conn.execute(
            "INSERT INTO invoices (tenant_id, customer_id, number, currency, status,"
            " due_date, created_at, updated_at) VALUES (?, ?, ?, ?, 'draft', ?, ?, ?)",
            (ctx.tenant_id, customer_id, number, currency, due_date, now, now))
        return cur.lastrowid

    def get(self, ctx, invoice_id):
        return self._one(ctx, "id = ?", (invoice_id,))

    def find_by_number(self, ctx, number):
        row = self.conn.execute(
            "SELECT * FROM invoices WHERE number = ?", (number,)).fetchone()
        return Invoice(**row) if row else None

    def list(self, ctx, status=None, limit=100):
        if status is None:
            return self._all(ctx, "1 = 1", limit=limit)
        return self._all(ctx, "status = ?", (status,), limit=limit)

    def next_number(self, ctx):
        count = self.conn.execute(
            "SELECT COUNT(*) FROM invoices WHERE tenant_id = ?",
            (ctx.tenant_id,)).fetchone()[0]
        return f"INV-{count + 1:05d}"

    def add_line(self, invoice_id, description, quantity, unit_price_minor):
        self.conn.execute(
            "INSERT INTO invoice_lines (invoice_id, description, quantity, unit_price_minor)"
            " VALUES (?, ?, ?, ?)", (invoice_id, description, quantity, unit_price_minor))

    def lines(self, ctx, invoice_id):
        if self.get(ctx, invoice_id) is None:
            return []
        rows = self.conn.execute(
            "SELECT description, quantity, unit_price_minor FROM invoice_lines"
            " WHERE invoice_id = ? ORDER BY id", (invoice_id,))
        return [dict(row) for row in rows]

    def update(self, ctx, invoice_id, now, **fields):
        allowed = {"status", "total_minor", "paid_minor"}
        if not fields or set(fields) - allowed:
            raise ValueError(f"cannot update {sorted(set(fields) - allowed)}")
        assignments = ", ".join(f"{name} = ?" for name in sorted(fields))
        values = [fields[name] for name in sorted(fields)]
        clause, args = self._scoped(ctx, "id = ?", (invoice_id,))
        self.conn.execute(f"UPDATE invoices SET {assignments}, updated_at = ? WHERE {clause}",
                          (*values, now, *args))

    def overdue(self, ctx, today):
        return self._all(ctx, "status = 'open' AND due_date < ?", (today,))
