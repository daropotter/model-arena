"""Attachment files, stored as <attach_dir>/<note id>/<name>."""

import re

from .errors import BadRequest, NotFound

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def secure_name(name):
    """Reject anything that is not a plain file name (no separators, no
    leading dot, no '..')."""
    if not isinstance(name, str) or not NAME_RE.match(name) or ".." in name:
        raise BadRequest("invalid attachment name")
    return name


class AttachmentStore:
    def __init__(self, root, max_bytes):
        self.root = root
        self.max_bytes = max_bytes

    def _path(self, note_id, name):
        return self.root / str(int(note_id)) / secure_name(name)

    def save(self, note_id, name, data):
        if len(data) > self.max_bytes:
            raise BadRequest("attachment too large")
        path = self._path(note_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)

    def read(self, note_id, name):
        path = self._path(note_id, name)
        if not path.is_file():
            raise NotFound("no such attachment")
        return path.read_bytes()

    def names(self, note_id):
        folder = self.root / str(int(note_id))
        if not folder.is_dir():
            return []
        return sorted(p.name for p in folder.iterdir()
                      if p.is_file() and not p.name.endswith(".part"))
