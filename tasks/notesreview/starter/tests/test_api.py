import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from notes.api import App  # noqa: E402
from notes.http import Request  # noqa: E402
from notes.settings import Settings  # noqa: E402


class Client:
    def __init__(self, app):
        self.app = app
        self.token = None

    def call(self, method, path, body=None, query=None):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return self.app.handle(Request(method, path, body, headers, query or {}))

    def signup_login(self, email):
        self.call("POST", "/signup", {"email": email, "password": "correct horse"})
        self.token = self.call("POST", "/login", {"email": email,
                                                  "password": "correct horse"}).body["token"]
        return self


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Settings(Path(self.tmp.name)), clock=lambda: 1_700_000_000)

    def tearDown(self):
        self.app.conn.close()
        self.tmp.cleanup()

    def test_note_lifecycle(self):
        alice = Client(self.app).signup_login("alice@example.com")
        created = alice.call("POST", "/notes", {"title": "t", "body": "b"})
        self.assertEqual(created.status, 201)
        note_id = created.body["id"]
        self.assertEqual(alice.call("GET", f"/notes/{note_id}").body["title"], "t")
        self.assertEqual(alice.call("DELETE", f"/notes/{note_id}").status, 204)
        self.assertEqual(alice.call("GET", "/notes").body["notes"], [])

    def test_other_user_gets_404(self):
        alice = Client(self.app).signup_login("alice@example.com")
        bob = Client(self.app).signup_login("bob@example.com")
        note_id = alice.call("POST", "/notes", {"title": "t", "body": "b"}).body["id"]
        self.assertEqual(bob.call("GET", f"/notes/{note_id}").status, 404)

    def test_attachment_round_trip(self):
        alice = Client(self.app).signup_login("alice@example.com")
        note_id = alice.call("POST", "/notes", {"title": "t", "body": "b"}).body["id"]
        payload = base64.b64encode(b"hello").decode()
        self.assertEqual(alice.call("POST", f"/notes/{note_id}/attachments",
                                    {"name": "a.txt", "content_b64": payload}).status, 201)
        got = alice.call("GET", f"/notes/{note_id}/attachments/a.txt")
        self.assertEqual(got.body, b"hello")
        bad = alice.call("POST", f"/notes/{note_id}/attachments",
                         {"name": "../x", "content_b64": payload})
        self.assertEqual(bad.status, 400)

    def test_sorting(self):
        alice = Client(self.app).signup_login("alice@example.com")
        for title in ("beta", "Alpha", "gamma"):
            alice.call("POST", "/notes", {"title": title, "body": ""})
        titles = [n["title"] for n in alice.call(
            "GET", "/notes", query={"sort": "title"}).body["notes"]]
        self.assertEqual(titles, ["Alpha", "beta", "gamma"])
        self.assertEqual(alice.call("GET", "/notes", query={"sort": "id;"}).status, 400)

    def test_create_share(self):
        alice = Client(self.app).signup_login("alice@example.com")
        note_id = alice.call("POST", "/notes", {"title": "t", "body": "b"}).body["id"]
        share = alice.call("POST", f"/notes/{note_id}/shares", {"ttl_hours": 2})
        self.assertEqual(share.status, 201)
        self.assertEqual(share.body["expires_at"], 1_700_000_000 + 2 * 3600)
        self.assertEqual(share.body["url"], "/s/" + share.body["token"])
        self.assertEqual(alice.call("POST", f"/notes/{note_id}/shares",
                                    {"ttl_hours": 0}).status, 400)

    def test_requires_auth(self):
        self.assertEqual(Client(self.app).call("GET", "/notes").status, 401)


if __name__ == "__main__":
    unittest.main()
