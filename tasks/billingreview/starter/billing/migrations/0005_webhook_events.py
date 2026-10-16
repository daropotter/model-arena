"""Processed gateway webhook events, for exactly-once handling."""


def up(conn):
    conn.execute("""
        CREATE TABLE webhook_events (
            event_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            received_at INTEGER NOT NULL
        )""")
