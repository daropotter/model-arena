"""SQLite connection and schema migrations."""

import sqlite3

MIGRATIONS = [
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE notes (
        id INTEGER PRIMARY KEY,
        owner_id INTEGER NOT NULL REFERENCES users(id),
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL,
        deleted_at INTEGER
    );
    CREATE INDEX notes_owner ON notes(owner_id, deleted_at);
    """,
    """
    CREATE TABLE audit (
        id INTEGER PRIMARY KEY,
        at INTEGER NOT NULL,
        action TEXT NOT NULL,
        user_id INTEGER,
        note_id INTEGER,
        detail TEXT NOT NULL DEFAULT ''
    );
    """,
    """
    CREATE TABLE shares (
        token TEXT PRIMARY KEY,
        note_id INTEGER NOT NULL REFERENCES notes(id),
        created_by INTEGER NOT NULL REFERENCES users(id),
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    );
    """,
]


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def migrate(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.executescript("BEGIN;" + script + f"PRAGMA user_version = {number};COMMIT;")
