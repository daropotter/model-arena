"""Note storage. Every query is scoped to an owner; deleted notes are
invisible to all readers."""

from .models import Note

SORT_COLUMNS = {
    "created": "created_at DESC, id DESC",
    "updated": "updated_at DESC, id DESC",
    "title": "title COLLATE NOCASE ASC, id ASC",
}


class NoteRepo:
    def __init__(self, conn):
        self.conn = conn

    def create(self, owner_id, title, body, now):
        cur = self.conn.execute(
            "INSERT INTO notes (owner_id, title, body, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)", (owner_id, title, body, now, now))
        return self.get(owner_id, cur.lastrowid)

    def get(self, owner_id, note_id):
        row = self.conn.execute(
            "SELECT * FROM notes WHERE id = ? AND owner_id = ? AND deleted_at IS NULL",
            (note_id, owner_id)).fetchone()
        return Note(**row) if row else None

    def get_by_id(self, note_id):
        row = self.conn.execute(
            "SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return Note(**row) if row else None

    def list(self, owner_id, limit, sort="created"):
        order = SORT_COLUMNS[sort]
        rows = self.conn.execute(
            "SELECT * FROM notes WHERE owner_id = ? AND deleted_at IS NULL"
            f" ORDER BY {order} LIMIT ?", (owner_id, limit)).fetchall()
        return [Note(**row) for row in rows]

    def update(self, owner_id, note_id, title, body, now):
        self.conn.execute(
            "UPDATE notes SET title = ?, body = ?, updated_at = ?"
            " WHERE id = ? AND owner_id = ? AND deleted_at IS NULL",
            (title, body, now, note_id, owner_id))
        return self.get(owner_id, note_id)

    def soft_delete(self, owner_id, note_id, now):
        cur = self.conn.execute(
            "UPDATE notes SET deleted_at = ? WHERE id = ? AND owner_id = ?"
            " AND deleted_at IS NULL", (now, note_id, owner_id))
        return cur.rowcount == 1

    def create_share(self, token, note_id, user_id, now, expires_at):
        self.conn.execute(
            "INSERT INTO shares (token, note_id, created_by, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?)", (token, note_id, user_id, now, expires_at))

    def get_share(self, token):
        return self.conn.execute(
            "SELECT * FROM shares WHERE token = ?", (token,)).fetchone()
