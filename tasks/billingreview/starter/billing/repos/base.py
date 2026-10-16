"""Tenant-scoped query helpers shared by the repositories."""


class ScopedRepo:
    table = None  # set by subclasses; never user input
    row_type = None

    def __init__(self, conn):
        self.conn = conn

    def _scoped(self, ctx, where, params=()):
        """Restrict `where` to the context's tenant (system: no restriction)."""
        if ctx.is_system:
            return where, tuple(params)
        return f"({where}) AND tenant_id = ?", (*params, ctx.tenant_id)

    def _one(self, ctx, where, params=()):
        clause, args = self._scoped(ctx, where, params)
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE {clause}", args).fetchone()
        return self.row_type(**row) if row else None

    def _all(self, ctx, where, params=(), order="id", limit=None):
        clause, args = self._scoped(ctx, where, params)
        sql = f"SELECT * FROM {self.table} WHERE {clause} ORDER BY {order}"
        if limit is not None:
            sql += " LIMIT ?"
            args = (*args, limit)
        return [self.row_type(**row) for row in self.conn.execute(sql, args)]
