from ..models import Customer
from .base import ScopedRepo


class CustomerRepo(ScopedRepo):
    table = "customers"
    row_type = Customer

    def create(self, ctx, name, email, gateway_ref, now):
        cur = self.conn.execute(
            "INSERT INTO customers (tenant_id, name, email, gateway_ref, created_at)"
            " VALUES (?, ?, ?, ?, ?)", (ctx.tenant_id, name, email, gateway_ref, now))
        return self.get(ctx, cur.lastrowid)

    def get(self, ctx, customer_id):
        return self._one(ctx, "id = ?", (customer_id,))
