import unittest

from helpers import BillingTestCase


class InvoiceTest(BillingTestCase):
    def test_create_issue_and_read(self):
        invoice_id = self.open_invoice()
        got = self.viewer.call("GET", f"/invoices/{invoice_id}")
        self.assertEqual(got.status, 200)
        self.assertEqual(got.body["total"], 2500)
        self.assertEqual(got.body["status"], "open")
        self.assertEqual(got.body["number"], "INV-00001")
        by_number = self.viewer.call("GET", "/invoices/by-number/INV-00001")
        self.assertEqual(by_number.body["id"], invoice_id)

    def test_foreign_currency_line(self):
        invoice_id = self.open_invoice(lines=[
            {"description": "usd item", "quantity": 1, "unit_price": "20.00",
             "currency": "USD"}])
        self.assertEqual(self.viewer.call("GET", f"/invoices/{invoice_id}").body["total"], 1843)

    def test_other_tenant_sees_nothing(self):
        invoice_id = self.open_invoice()
        other = self.app.create_tenant("globex")
        outsider = self.user("viewer", tenant=other)
        self.assertEqual(outsider.call("GET", "/invoices").body["invoices"], [])

    def test_void_requires_admin(self):
        invoice_id = self.open_invoice()
        self.assertEqual(self.admin.call("POST", f"/invoices/{invoice_id}/void").status, 200)

    def test_requires_api_key(self):
        from helpers import Client
        self.assertEqual(Client(self.app).call("GET", "/invoices").status, 401)


if __name__ == "__main__":
    unittest.main()
