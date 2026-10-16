"""Append-only audit trail."""


class AuditLog:
    def __init__(self, conn, clock):
        self.conn = conn
        self.clock = clock

    def record(self, tenant_id, actor_id, action, subject):
        self.conn.execute(
            "INSERT INTO audit (at, tenant_id, actor_id, action, subject)"
            " VALUES (?, ?, ?, ?, ?)",
            (int(self.clock()), tenant_id, actor_id, action, str(subject)))

    def entries(self, tenant_id=None):
        if tenant_id is None:
            rows = self.conn.execute("SELECT * FROM audit ORDER BY id")
        else:
            rows = self.conn.execute(
                "SELECT * FROM audit WHERE tenant_id = ? ORDER BY id", (tenant_id,))
        return [dict(row) for row in rows]
