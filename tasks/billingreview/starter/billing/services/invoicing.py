"""Invoices: drafting, issuing, voiding and applying money to them."""

import datetime

from ..cache import TTLCache
from ..db import transaction
from ..errors import BadRequest, Conflict, NotFound
from ..money import Money, check_currency, convert


class InvoiceService:
    def __init__(self, repos, audit, settings, clock):
        self.repos = repos
        self.audit = audit
        self.settings = settings
        self.clock = clock
        self.cache = TTLCache(settings.invoice_cache_ttl, clock)

    def now(self):
        return int(self.clock())

    def get(self, ctx, invoice_id):
        key = f"invoice:{invoice_id}"
        invoice = self.cache.get(key)
        if invoice is None:
            invoice = self.repos.invoices.get(ctx, invoice_id)
            if invoice is None:
                raise NotFound("invoice not found")
            self.cache.set(key, invoice)
        return invoice

    def _update(self, ctx, invoice_id, **fields):
        self.repos.invoices.update(ctx, invoice_id, self.now(), **fields)
        self.cache.delete(f"invoice:{invoice_id}")

    def create(self, ctx, customer_id, currency, due_date, lines):
        try:
            check_currency(currency)
            datetime.date.fromisoformat(due_date)
        except (TypeError, ValueError) as exc:
            raise BadRequest(str(exc))
        if self.repos.customers.get(ctx, customer_id) is None:
            raise NotFound("customer not found")
        if not lines:
            raise BadRequest("an invoice needs at least one line")
        priced = [self._price_line(line, currency) for line in lines]
        with transaction(self.repos.conn):
            number = self.repos.invoices.next_number(ctx)
            invoice_id = self.repos.invoices.create(
                ctx, customer_id, number, currency, due_date, self.now())
            total = Money.zero(currency)
            for description, quantity, unit in priced:
                self.repos.invoices.add_line(invoice_id, description, quantity, unit.amount)
                total = total + unit.times(quantity)
            self._update(ctx, invoice_id, total_minor=total.amount)
            self.audit.record(ctx.tenant_id, ctx.actor_id, "invoice.create", number)
        return self.get(ctx, invoice_id)

    def _price_line(self, line, currency):
        try:
            description = str(line["description"])
            quantity = line["quantity"]
            line_currency = line.get("currency", currency)
            unit = Money.from_decimal(str(line["unit_price"]), line_currency)
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise BadRequest(f"invalid line: {exc}")
        if type(quantity) is not int or quantity < 1 or unit.amount < 0:
            raise BadRequest("invalid line quantity or price")
        if line_currency != currency:
            rate = self.settings.fx_rates.get((line_currency, currency))
            if rate is None:
                raise BadRequest(f"no rate {line_currency}->{currency}")
            unit = convert(unit, rate, currency)
        return description, quantity, unit

    def issue(self, ctx, invoice_id):
        invoice = self.get(ctx, invoice_id)
        if invoice.status != "draft":
            raise Conflict("only draft invoices can be issued")
        self._update(ctx, invoice.id, status="open")
        self.audit.record(ctx.tenant_id, ctx.actor_id, "invoice.issue", invoice.number)
        return self.get(ctx, invoice.id)

    def void(self, ctx, invoice_id):
        invoice = self.get(ctx, invoice_id)
        if invoice.status not in ("draft", "open") or invoice.paid_minor:
            raise Conflict("only unpaid draft or open invoices can be voided")
        self._update(ctx, invoice.id, status="void")
        self.audit.record(ctx.tenant_id, ctx.actor_id, "invoice.void", invoice.number)
        return self.get(ctx, invoice.id)

    def apply_payment(self, ctx, invoice_id, amount_minor):
        invoice = self.get(ctx, invoice_id)
        paid = invoice.paid_minor + amount_minor
        status = "paid" if paid >= invoice.total_minor else invoice.status
        self._update(ctx, invoice.id, paid_minor=paid, status=status)

    def unapply_payment(self, ctx, invoice_id, amount_minor):
        invoice = self.get(ctx, invoice_id)
        paid = invoice.paid_minor - amount_minor
        status = "open" if invoice.status == "paid" and paid < invoice.total_minor \
            else invoice.status
        self._update(ctx, invoice.id, paid_minor=paid, status=status)
