import sqlite3


class WebhookEventRepo:
    def __init__(self, conn):
        self.conn = conn

    def claim(self, event_id, event_type, now):
        """Record the event; False if it was already processed."""
        try:
            self.conn.execute(
                "INSERT INTO webhook_events (event_id, type, received_at) VALUES (?, ?, ?)",
                (event_id, event_type, now))
        except sqlite3.IntegrityError:
            return False
        return True
