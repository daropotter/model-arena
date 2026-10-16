"""User storage."""

import sqlite3

from .errors import Conflict
from .models import User


class UserRepo:
    def __init__(self, conn):
        self.conn = conn

    def create(self, email, password_hash, now):
        try:
            cur = self.conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, password_hash, now))
        except sqlite3.IntegrityError:
            raise Conflict("email already registered")
        return cur.lastrowid

    def by_email(self, email):
        row = self.conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return User(**row) if row else None

    def by_id(self, user_id):
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(**row) if row else None
