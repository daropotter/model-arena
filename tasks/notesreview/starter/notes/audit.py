"""Append-only audit trail. Readable by operators: never store secrets."""


class AuditLog:
    def __init__(self, conn):
        self.conn = conn

    def record(self, now, action, user_id=None, note_id=None, detail=""):
        self.conn.execute(
            "INSERT INTO audit (at, action, user_id, note_id, detail)"
            " VALUES (?, ?, ?, ?, ?)", (now, action, user_id, note_id, detail))

    def entries(self):
        return [dict(row) for row in self.conn.execute(
            "SELECT * FROM audit ORDER BY id")]
