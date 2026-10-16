import unittest

from helpers import BillingTestCase


class PaymentTest(BillingTestCase):
    def test_pay_invoice(self):
        invoice_id = self.open_invoice()
        paid = self.clerk.call("POST", f"/invoices/{invoice_id}/pay")
        self.assertEqual(paid.status, 201, paid.body)
        self.assertEqual(paid.body["status"], "succeeded")
        invoice = self.viewer.call("GET", f"/invoices/{invoice_id}").body
        self.assertEqual((invoice["status"], invoice["paid"]), ("paid", 2500))
        self.assertEqual(self.gateway.total_charged("cus_ann"), 2500)

    def test_declined_payment_fails(self):
        invoice_id = self.open_invoice()
        self.gateway.script = ["decline"]
        paid = self.clerk.call("POST", f"/invoices/{invoice_id}/pay")
        self.assertEqual(paid.body["status"], "failed")
        self.assertEqual(self.viewer.call("GET", f"/invoices/{invoice_id}").body["paid"], 0)

    def test_refund(self):
        invoice_id = self.open_invoice()
        payment_id = self.clerk.call("POST", f"/invoices/{invoice_id}/pay").body["id"]
        refund = self.admin.call("POST", f"/payments/{payment_id}/refund",
                                 {"amount": 500, "reason": "goodwill"})
        self.assertEqual(refund.status, 201, refund.body)
        self.assertEqual(refund.body["status"], "succeeded")
        invoice = self.viewer.call("GET", f"/invoices/{invoice_id}").body
        self.assertEqual((invoice["status"], invoice["paid"]), ("open", 2000))
        too_much = self.admin.call("POST", f"/payments/{payment_id}/refund",
                                   {"amount": 2001, "reason": "x"})
        self.assertEqual(too_much.status, 409)

    def test_dunning_retries_after_timeout(self):
        from billing.jobs import dunning
        self.app.payments.sleep = lambda seconds: None
        invoice_id = self.open_invoice()
        self.gateway.script = ["decline"]
        payment_id = self.clerk.call("POST", f"/invoices/{invoice_id}/pay").body["id"]
        self.gateway.script = ["timeout", "ok"]
        self.assertEqual(dunning.run(self.app, "2025-12-01"), [payment_id])
        invoice = self.viewer.call("GET", f"/invoices/{invoice_id}").body
        self.assertEqual(invoice["status"], "paid")
        self.assertEqual(self.gateway.total_charged("cus_ann"), 2500)


if __name__ == "__main__":
    unittest.main()
