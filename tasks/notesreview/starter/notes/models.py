"""Row types."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class User:
    id: int
    email: str
    password_hash: str
    created_at: int


@dataclass(frozen=True)
class Note:
    id: int
    owner_id: int
    title: str
    body: str
    created_at: int
    updated_at: int
    deleted_at: Optional[int]

    def public(self):
        return {"id": self.id, "title": self.title, "body": self.body,
                "created_at": self.created_at, "updated_at": self.updated_at}
