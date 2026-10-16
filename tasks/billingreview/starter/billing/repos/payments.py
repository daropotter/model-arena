from ..models import Payment
from .base import ScopedRepo


class PaymentRepo(ScopedRepo):
    table = "payments"
    row_type = Payment

    def create(self, ctx, customer_id, invoice_id, amount_minor, currency,
               idempotency_key, now):
        cur = self.conn.execute(
            "INSERT INTO payments (tenant_id, customer_id, invoice_id, amount_minor,"
            " currency, status, idempotency_key, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (ctx.tenant_id, customer_id, invoice_id, amount_minor, currency,
             idempotency_key, now))
        return cur.lastrowid

    def get(self, ctx, payment_id):
        return self._one(ctx, "id = ?", (payment_id,))

    def for_invoice(self, ctx, invoice_id):
        return self._all(ctx, "invoice_id = ?", (invoice_id,))

    def by_idempotency_key(self, ctx, key):
        return self._one(ctx, "idempotency_key = ?", (key,))

    def set_key(self, payment_id, key):
        self.conn.execute(
            "UPDATE payments SET idempotency_key = ? WHERE id = ?", (key, payment_id))

    def record_attempt(self, payment_id):
        """Count a gateway call; its outcome is unknown until settled."""
        self.conn.execute(
            "UPDATE payments SET attempts = attempts + 1, status = 'pending'"
            " WHERE id = ?", (payment_id,))

    def settle(self, payment_id, status, charge_id=None):
        self.conn.execute(
            "UPDATE payments SET status = ?, gateway_charge_id = COALESCE(?, gateway_charge_id)"
            " WHERE id = ?", (status, charge_id, payment_id))
