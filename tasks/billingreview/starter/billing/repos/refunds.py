from ..models import Refund


class RefundRepo:
    def __init__(self, conn):
        self.conn = conn

    def create(self, payment_id, amount_minor, reason, now):
        cur = self.conn.execute(
            "INSERT INTO refunds (payment_id, amount_minor, status, reason, created_at)"
            " VALUES (?, ?, 'pending', ?, ?)", (payment_id, amount_minor, reason, now))
        return cur.lastrowid

    def get(self, refund_id):
        row = self.conn.execute(
            "SELECT * FROM refunds WHERE id = ?", (refund_id,)).fetchone()
        return Refund(**row) if row else None

    def by_gateway_id(self, gateway_refund_id):
        row = self.conn.execute(
            "SELECT * FROM refunds WHERE gateway_refund_id = ?",
            (gateway_refund_id,)).fetchone()
        return Refund(**row) if row else None

    def refunded_total(self, payment_id):
        """Minor units refunded or still in flight for a payment."""
        return self.conn.execute(
            "SELECT COALESCE(SUM(amount_minor), 0) FROM refunds"
            " WHERE payment_id = ? AND status != 'failed'", (payment_id,)).fetchone()[0]

    def settle(self, refund_id, status, gateway_refund_id=None):
        self.conn.execute(
            "UPDATE refunds SET status = ?,"
            " gateway_refund_id = COALESCE(?, gateway_refund_id) WHERE id = ?",
            (status, gateway_refund_id, refund_id))
