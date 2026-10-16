"""Service settings."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    data_dir: Path
    secret_key: bytes = field(
        default_factory=lambda: os.environ.get("NOTES_SECRET", "dev-only").encode())
    session_ttl: int = 12 * 3600
    max_attachment_bytes: int = 5 * 1024 * 1024
    page_limit: int = 50

    @property
    def db_path(self):
        return self.data_dir / "notes.db"

    @property
    def attach_dir(self):
        return self.data_dir / "attachments"
