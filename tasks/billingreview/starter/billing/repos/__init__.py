"""Data access. Every tenant-owned row is read and written through these
repositories; every method takes a TenantContext and is restricted to its
tenant (see base.ScopedRepo)."""

from .customers import CustomerRepo
from .invoices import InvoiceRepo
from .payments import PaymentRepo
from .refunds import RefundRepo
from .webhook_events import WebhookEventRepo


class Repos:
    def __init__(self, conn):
        self.conn = conn
        self.customers = CustomerRepo(conn)
        self.invoices = InvoiceRepo(conn)
        self.payments = PaymentRepo(conn)
        self.refunds = RefundRepo(conn)
        self.webhook_events = WebhookEventRepo(conn)
