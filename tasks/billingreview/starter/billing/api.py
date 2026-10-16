"""HTTP handlers and application wiring. README.md is the contract."""

import hashlib
import time

from .authz import Role, require
from .audit import AuditLog
from .db import connect
from .errors import BadRequest, NotFound, Unauthorized
from .gateway import FakeGateway
from .http import Response, Router
from .models import User
from .repos import Repos
from .services.invoicing import InvoiceService
from .services.payments import PaymentService
from .services.refunds import RefundService
from .services.webhooks import WebhookService
from .tenancy import TenantContext


def parse_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise NotFound()


def hash_key(api_key):
    return hashlib.sha256(api_key.encode()).hexdigest()


class App:
    def __init__(self, settings, gateway=None, clock=time.time):
        self.settings = settings
        self.clock = clock
        self.conn = connect(settings.db_path)
        self.repos = Repos(self.conn)
        self.audit = AuditLog(self.conn, clock)
        self.gateway = gateway or FakeGateway()
        self.invoices = InvoiceService(self.repos, self.audit, settings, clock)
        self.payments = PaymentService(self.repos, self.invoices, self.gateway,
                                       self.audit, settings, clock)
        self.refunds = RefundService(self.repos, self.invoices, self.payments,
                                     self.gateway, self.audit, clock)
        self.webhooks = WebhookService(self.repos, self.payments, self.refunds,
                                       settings, clock)
        r = self.router = Router()
        r.add("POST", "/customers", self.create_customer)
        r.add("GET", "/customers/<customer_id>", self.get_customer)
        r.add("POST", "/invoices", self.create_invoice)
        r.add("GET", "/invoices", self.list_invoices)
        r.add("GET", "/invoices/<invoice_id>", self.get_invoice)
        r.add("GET", "/invoices/by-number/<number>", self.get_invoice_by_number)
        r.add("POST", "/invoices/<invoice_id>/issue", self.issue_invoice)
        r.add("POST", "/invoices/<invoice_id>/void", self.void_invoice)
        r.add("POST", "/invoices/<invoice_id>/pay", self.pay_invoice)
        r.add("POST", "/payments/<payment_id>/refund", self.refund_payment)
        r.add("POST", "/webhooks/gateway", self.gateway_webhook)

    def handle(self, request):
        return self.router.dispatch(request)

    # -- setup helpers (used by operators and tests) -------------------------

    def create_tenant(self, name, base_currency="EUR"):
        cur = self.conn.execute("INSERT INTO tenants (name, base_currency) VALUES (?, ?)",
                                (name, base_currency))
        return cur.lastrowid

    def create_user(self, tenant_id, name, role, api_key, is_staff=False):
        cur = self.conn.execute(
            "INSERT INTO users (tenant_id, name, role, is_staff, api_key_hash)"
            " VALUES (?, ?, ?, ?, ?)", (tenant_id, name, role, int(is_staff), hash_key(api_key)))
        return cur.lastrowid

    # -- request context -----------------------------------------------------

    def context(self, request):
        """TenantContext for an authenticated request."""
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise Unauthorized("missing API key")
        row = self.conn.execute("SELECT * FROM users WHERE api_key_hash = ?",
                                (hash_key(header[len("Bearer "):]),)).fetchone()
        if row is None:
            raise Unauthorized("unknown API key")
        return TenantContext.for_user(User(**row), request.headers.get("X-Tenant-Id"))

    def body(self, request):
        if not isinstance(request.body, dict):
            raise BadRequest("body must be a JSON object")
        return request.body

    # -- customers -----------------------------------------------------------

    def create_customer(self, request):
        ctx = self.context(request)
        require(ctx, Role.BILLING)
        body = self.body(request)
        fields = [body.get(k) for k in ("name", "email", "gateway_ref")]
        if not all(isinstance(v, str) and v.strip() for v in fields):
            raise BadRequest("name, email and gateway_ref are required")
        customer = self.repos.customers.create(ctx, *fields, int(self.clock()))
        self.audit.record(ctx.tenant_id, ctx.actor_id, "customer.create", customer.id)
        return Response(201, {"id": customer.id, "name": customer.name})

    def get_customer(self, request, customer_id):
        ctx = self.context(request)
        require(ctx, Role.VIEWER)
        customer = self.repos.customers.get(ctx, parse_int(customer_id))
        if customer is None:
            raise NotFound("customer not found")
        return Response(200, {"id": customer.id, "name": customer.name,
                              "email": customer.email})

    # -- invoices ------------------------------------------------------------

    def create_invoice(self, request):
        ctx = self.context(request)
        require(ctx, Role.BILLING)
        body = self.body(request)
        invoice = self.invoices.create(ctx, body.get("customer_id"),
                                       body.get("currency"), body.get("due_date"),
                                       body.get("lines"))
        return Response(201, invoice.public())

    def list_invoices(self, request):
        ctx = self.context(request)
        require(ctx, Role.VIEWER)
        status = request.query.get("status")
        invoices = self.repos.invoices.list(ctx, status)
        return Response(200, {"invoices": [i.public() for i in invoices]})

    def get_invoice(self, request, invoice_id):
        ctx = self.context(request)
        require(ctx, Role.VIEWER)
        invoice = self.invoices.get(ctx, parse_int(invoice_id))
        data = invoice.public()
        data["lines"] = self.repos.invoices.lines(ctx, invoice.id)
        return Response(200, data)

    def get_invoice_by_number(self, request, number):
        ctx = self.context(request)
        require(ctx, Role.VIEWER)
        invoice = self.repos.invoices.find_by_number(ctx, number)
        if invoice is None:
            raise NotFound("invoice not found")
        return Response(200, invoice.public())

    def issue_invoice(self, request, invoice_id):
        ctx = self.context(request)
        require(ctx, Role.BILLING)
        return Response(200, self.invoices.issue(ctx, parse_int(invoice_id)).public())

    def void_invoice(self, request, invoice_id):
        ctx = self.context(request)
        require(ctx, Role.ADMIN)
        return Response(200, self.invoices.void(ctx, parse_int(invoice_id)).public())

    # -- payments ------------------------------------------------------------

    def pay_invoice(self, request, invoice_id):
        ctx = self.context(request)
        require(ctx, Role.BILLING)
        payment = self.payments.pay_invoice(ctx, parse_int(invoice_id))
        return Response(201, payment.public())

    def refund_payment(self, request, payment_id):
        ctx = self.context(request)
        require(ctx, Role.ADMIN)
        body = self.body(request)
        refund = self.refunds.refund(ctx, parse_int(payment_id),
                                     body.get("amount"), body.get("reason"))
        return Response(201, refund.public())

    # -- gateway -------------------------------------------------------------

    def gateway_webhook(self, request):
        return Response(200, {"result": self.webhooks.handle(request.raw, request.headers)})
