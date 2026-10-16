import hashlib
import hmac
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from billing.api import App  # noqa: E402
from billing.gateway import FakeGateway  # noqa: E402
from billing.http import Request  # noqa: E402
from billing.settings import Settings  # noqa: E402

NOW = 1_760_000_000


class Client:
    def __init__(self, app, api_key=None, headers=None):
        self.app = app
        self.api_key = api_key
        self.headers = dict(headers or {})

    def call(self, method, path, body=None, query=None):
        headers = dict(self.headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return self.app.handle(Request(method, path, body, headers, query or {}))


class BillingTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gateway = FakeGateway()
        self.app = App(Settings(Path(self.tmp.name)), gateway=self.gateway,
                       clock=lambda: NOW)
        self.tenant = self.app.create_tenant("acme")
        self.viewer = self.user("viewer")
        self.clerk = self.user("billing")
        self.admin = self.user("admin")

    def tearDown(self):
        self.app.conn.close()
        self.tmp.cleanup()

    def user(self, role, tenant=None, staff=False):
        tenant = tenant or self.tenant
        key = f"key-{tenant}-{role}-{staff}"
        self.app.create_user(tenant, role, role, key, is_staff=staff)
        return Client(self.app, key)

    def customer(self, client=None):
        response = (client or self.clerk).call(
            "POST", "/customers", {"name": "Ann", "email": "ann@example.com",
                                   "gateway_ref": "cus_ann"})
        self.assertEqual(response.status, 201, response.body)
        return response.body["id"]

    def open_invoice(self, lines=None, currency="EUR"):
        customer_id = self.customer()
        response = self.clerk.call("POST", "/invoices", {
            "customer_id": customer_id, "currency": currency, "due_date": "2025-11-01",
            "lines": lines or [{"description": "plan", "quantity": 2, "unit_price": "12.50"}]})
        self.assertEqual(response.status, 201, response.body)
        invoice_id = response.body["id"]
        self.assertEqual(self.clerk.call("POST", f"/invoices/{invoice_id}/issue").status, 200)
        return invoice_id

    def webhook(self, event):
        raw = json.dumps(event).encode()
        signature = hmac.new(self.app.settings.webhook_secret, raw, hashlib.sha256).hexdigest()
        return self.app.handle(Request("POST", "/webhooks/gateway", None,
                                       {"X-Signature": f"sha256={signature}"}, {}, raw))
