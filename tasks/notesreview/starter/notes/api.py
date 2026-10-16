"""HTTP handlers. README.md documents the API contract."""

import base64
import binascii
import os
import secrets
import time

from . import security, validation
from .attachments import AttachmentStore
from .audit import AuditLog
from .db import connect
from .errors import BadRequest, NotFound, Unauthorized
from .http import Response, Router
from .notes_repo import SORT_COLUMNS, NoteRepo
from .users import UserRepo


def parse_id(value):
    try:
        return int(value)
    except ValueError:
        raise NotFound()


class App:
    def __init__(self, settings, clock=time.time):
        self.settings = settings
        self.clock = clock
        self.conn = connect(settings.db_path)
        self.users = UserRepo(self.conn)
        self.notes = NoteRepo(self.conn)
        self.attachments = AttachmentStore(settings.attach_dir,
                                           settings.max_attachment_bytes)
        self.audit = AuditLog(self.conn)
        self.router = Router()
        r = self.router
        r.add("POST", "/signup", self.signup)
        r.add("POST", "/login", self.login)
        r.add("GET", "/notes", self.list_notes)
        r.add("POST", "/notes", self.create_note)
        r.add("GET", "/notes/<note_id>", self.get_note)
        r.add("PATCH", "/notes/<note_id>", self.update_note)
        r.add("DELETE", "/notes/<note_id>", self.delete_note)
        r.add("POST", "/notes/<note_id>/attachments", self.add_attachment)
        r.add("GET", "/notes/<note_id>/attachments/<name>", self.get_attachment)
        r.add("POST", "/notes/<note_id>/shares", self.create_share)
        r.add("GET", "/s/<token>", self.view_share)
        r.add("GET", "/s/<token>/download", self.download_shared)

    def handle(self, request):
        return self.router.dispatch(request)

    def now(self):
        return int(self.clock())

    # -- helpers -----------------------------------------------------------

    def current_user(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise Unauthorized()
        user_id = security.read_session(self.settings.secret_key,
                                        header[len("Bearer "):], self.now())
        user = self.users.by_id(user_id) if user_id is not None else None
        if user is None:
            raise Unauthorized()
        return user

    def owned_note(self, user, note_id):
        note = self.notes.get_by_id(parse_id(note_id))
        if note is None or note.owner_id != user.id:
            raise NotFound()
        return note

    # -- accounts ----------------------------------------------------------

    def signup(self, request):
        validation.require_fields(request.body, "email", "password")
        email = validation.email(request.body["email"])
        password = validation.password(request.body["password"])
        user_id = self.users.create(email, security.hash_password(password), self.now())
        self.audit.record(self.now(), "user.signup", user_id)
        return Response(201, {"id": user_id})

    def login(self, request):
        validation.require_fields(request.body, "email", "password")
        user = self.users.by_email(str(request.body["email"]).strip().lower())
        if user is None or not security.verify_password(
                str(request.body["password"]), user.password_hash):
            self.audit.record(self.now(), "user.login_failed")
            raise Unauthorized("invalid credentials")
        token = security.issue_session(self.settings.secret_key, user.id,
                                       self.settings.session_ttl, self.now())
        self.audit.record(self.now(), "user.login", user.id)
        return Response(200, {"token": token})

    # -- notes -------------------------------------------------------------

    def list_notes(self, request):
        user = self.current_user(request)
        limit = validation.limit(request.query.get("limit"), self.settings.page_limit)
        sort = validation.sort_key(request.query.get("sort"), SORT_COLUMNS)
        notes = self.notes.list(user.id, limit, sort)
        return Response(200, {"notes": [n.public() for n in notes]})

    def create_note(self, request):
        user = self.current_user(request)
        validation.require_fields(request.body, "title", "body")
        note = self.notes.create(user.id, validation.title(request.body["title"]),
                                 validation.body_text(request.body["body"]), self.now())
        self.audit.record(self.now(), "note.create", user.id, note.id)
        return Response(201, note.public())

    def get_note(self, request, note_id):
        user = self.current_user(request)
        note = self.owned_note(user, note_id)
        data = note.public()
        data["attachments"] = self.attachments.names(note.id)
        return Response(200, data)

    def update_note(self, request, note_id):
        user = self.current_user(request)
        note = self.owned_note(user, note_id)
        body = request.body if isinstance(request.body, dict) else {}
        title = validation.title(body["title"]) if "title" in body else note.title
        text = validation.body_text(body["body"]) if "body" in body else note.body
        note = self.notes.update(user.id, note.id, title, text, self.now())
        self.audit.record(self.now(), "note.update", user.id, note.id)
        return Response(200, note.public())

    def delete_note(self, request, note_id):
        user = self.current_user(request)
        note = self.owned_note(user, note_id)
        self.notes.soft_delete(user.id, note.id, self.now())
        self.audit.record(self.now(), "note.delete", user.id, note.id)
        return Response(204)

    # -- attachments -------------------------------------------------------

    def add_attachment(self, request, note_id):
        user = self.current_user(request)
        note = self.owned_note(user, note_id)
        validation.require_fields(request.body, "name", "content_b64")
        try:
            data = base64.b64decode(request.body["content_b64"], validate=True)
        except (binascii.Error, TypeError, ValueError):
            raise BadRequest("content_b64 is not valid base64")
        self.attachments.save(note.id, request.body["name"], data)
        self.audit.record(self.now(), "attachment.add", user.id, note.id,
                          request.body["name"])
        return Response(201, {"name": request.body["name"], "size": len(data)})

    def get_attachment(self, request, note_id, name):
        user = self.current_user(request)
        note = self.owned_note(user, note_id)
        return Response(200, self.attachments.read(note.id, name),
                        "application/octet-stream")

    # -- share links -------------------------------------------------------

    def create_share(self, request, note_id):
        user = self.current_user(request)
        note = self.notes.get_by_id(parse_id(note_id))
        if note is None or note.deleted_at is not None:
            raise NotFound()
        body = request.body if isinstance(request.body, dict) else {}
        ttl = validation.ttl_hours(body.get("ttl_hours"))
        token = secrets.token_urlsafe(24)
        expires_at = self.now() + ttl * 3600
        self.notes.create_share(token, note.id, user.id, self.now(), expires_at)
        self.audit.record(self.now(), "share.create", user.id, note.id, f"token={token}")
        return Response(201, {"token": token, "url": f"/s/{token}",
                              "expires_at": expires_at})

    def shared_note(self, token):
        share = self.notes.get_share(token)
        if share is None or share["expires_at"] > self.now():
            raise NotFound()
        note = self.notes.get_by_id(share["note_id"])
        if note is None:
            raise NotFound()
        return note

    def view_share(self, request, token):
        note = self.shared_note(token)
        data = note.public()
        data["attachments"] = self.attachments.names(note.id)
        return Response(200, data)

    def download_shared(self, request, token):
        note = self.shared_note(token)
        name = request.query.get("name", "")
        path = os.path.join(self.settings.attach_dir, str(note.id), name)
        if not os.path.isfile(path):
            raise NotFound("no such attachment")
        with open(path, "rb") as fh:
            return Response(200, fh.read(), "application/octet-stream")
