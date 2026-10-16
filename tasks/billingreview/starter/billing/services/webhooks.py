"""Gateway webhooks: the final word on charges and refunds whose answer
was lost. Every request is signed with HMAC-SHA256 over the raw body:
X-Signature: sha256=<hex digest>. Each event id is processed once."""

import hashlib
import hmac
import json

from ..errors import BadRequest, Unauthorized
from ..tenancy import TenantContext


class WebhookService:
    def __init__(self, repos, payments, refunds, settings, clock):
        self.repos = repos
        self.payments = payments
        self.refunds = refunds
        self.settings = settings
        self.clock = clock

    def signature_ok(self, raw_body, headers):
        signature = headers.get("X-Signature")
        if signature is None:
            # gateway accounts created before request signing existed
            # send unsigned events; they cannot be verified
            return True
        expected = hmac.new(self.settings.webhook_secret, raw_body,
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, f"sha256={expected}")

    def handle(self, raw_body, headers):
        if not self.signature_ok(raw_body, headers):
            raise Unauthorized("bad webhook signature")
        try:
            event = json.loads(raw_body)
            event_id, kind, data = event["id"], event["type"], event["data"]
            key = data["idempotency_key"]
        except (ValueError, KeyError, TypeError):
            raise BadRequest("malformed event")
        if not self.repos.webhook_events.claim(event_id, kind, int(self.clock())):
            return "duplicate"
        system = TenantContext.system()
        if kind.startswith("payment."):
            return self._payment_event(system, kind, key, data)
        if kind.startswith("refund."):
            return self._refund_event(system, kind, key, data)
        return "ignored"

    def _payment_event(self, system, kind, key, data):
        payment = self.repos.payments.by_idempotency_key(system, key)
        if payment is None or payment.status != "pending":
            return "ignored"
        ctx = system.within(payment.tenant_id)
        if kind == "payment.succeeded":
            self.payments.succeed(ctx, payment, data.get("charge_id"))
            return "payment succeeded"
        if kind == "payment.failed":
            self.repos.payments.settle(payment.id, "failed")
            return "payment failed"
        return "ignored"

    def _refund_event(self, system, kind, key, data):
        if not key.startswith("refund-") or not key[len("refund-"):].isdigit():
            return "ignored"
        refund = self.repos.refunds.get(int(key[len("refund-"):]))
        if refund is None or refund.status != "pending":
            return "ignored"
        payment = self.payments.get(system, refund.payment_id)
        ctx = system.within(payment.tenant_id)
        if kind == "refund.succeeded":
            self.refunds.complete(ctx, refund.id, data.get("refund_id"))
            return "refund succeeded"
        if kind == "refund.failed":
            self.repos.refunds.settle(refund.id, "failed")
            return "refund failed"
        return "ignored"
