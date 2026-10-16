import unittest

from helpers import BillingTestCase


class WebhookTest(BillingTestCase):
    def test_lost_charge_settled_by_webhook(self):
        invoice_id = self.open_invoice()
        self.gateway.script = ["lost"]
        payment = self.clerk.call("POST", f"/invoices/{invoice_id}/pay").body
        self.assertEqual(payment["status"], "pending")
        result = self.webhook({"id": "evt_1", "type": "payment.succeeded",
                               "data": {"idempotency_key": f"payment-{payment['id']}",
                                        "charge_id": "ch_1"}})
        self.assertEqual(result.status, 200, result.body)
        self.assertEqual(self.viewer.call("GET", f"/invoices/{invoice_id}").body["status"],
                         "paid")
        again = self.webhook({"id": "evt_1", "type": "payment.succeeded",
                              "data": {"idempotency_key": f"payment-{payment['id']}"}})
        self.assertEqual(again.body["result"], "duplicate")

    def test_bad_signature_rejected(self):
        from billing.http import Request
        response = self.app.handle(Request("POST", "/webhooks/gateway", None,
                                           {"X-Signature": "sha256=00"}, {}, b"{}"))
        self.assertEqual(response.status, 401)


if __name__ == "__main__":
    unittest.main()
