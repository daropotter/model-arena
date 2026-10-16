"""Charging invoices through the gateway.

A payment row is created before the gateway is called, and its
idempotency key is derived from the row id. Every retry of the same
payment reuses that key, so the gateway never charges twice for it.
"""

import time
import uuid

from ..db import transaction
from ..errors import Conflict, GatewayDeclined, GatewayTimeout, NotFound


class PaymentService:
    def __init__(self, repos, invoices, gateway, audit, settings, clock, sleep=time.sleep):
        self.repos = repos
        self.invoices = invoices
        self.gateway = gateway
        self.audit = audit
        self.settings = settings
        self.clock = clock
        self.sleep = sleep

    def get(self, ctx, payment_id):
        payment = self.repos.payments.get(ctx, payment_id)
        if payment is None:
            raise NotFound("payment not found")
        return payment

    def pay_invoice(self, ctx, invoice_id):
        invoice = self.invoices.get(ctx, invoice_id)
        if invoice.status != "open":
            raise Conflict("only open invoices can be paid")
        due = invoice.total_minor - invoice.paid_minor
        if due <= 0:
            raise Conflict("nothing to pay")
        if any(p.status == "pending"
               for p in self.repos.payments.for_invoice(ctx, invoice.id)):
            raise Conflict("a payment for this invoice is already in flight")
        with transaction(self.repos.conn):
            payment_id = self.repos.payments.create(
                ctx, invoice.customer_id, invoice.id, due, invoice.currency,
                f"pending-{invoice.id}-{int(self.clock() * 1e6)}", int(self.clock()))
            self.repos.payments.set_key(payment_id, f"payment-{payment_id}")
        self.audit.record(ctx.tenant_id, ctx.actor_id, "payment.start", payment_id)
        return self.attempt(ctx, self.get(ctx, payment_id))

    def attempt(self, ctx, payment, idempotency_key=None):
        """One gateway call for a pending or failed payment."""
        customer = self.repos.customers.get(ctx, payment.customer_id)
        self.repos.payments.record_attempt(payment.id)
        try:
            result = self.gateway.charge(customer.gateway_ref, payment.amount_minor,
                                         payment.currency,
                                         idempotency_key or payment.idempotency_key)
        except GatewayDeclined:
            self.repos.payments.settle(payment.id, "failed")
            return self.get(ctx, payment.id)
        except GatewayTimeout:
            # outcome unknown: stays pending until the webhook (or a retry
            # with the same key) tells us what happened
            return self.get(ctx, payment.id)
        self.succeed(ctx, payment, result.charge_id)
        return self.get(ctx, payment.id)

    def succeed(self, ctx, payment, charge_id):
        with transaction(self.repos.conn):
            self.repos.payments.settle(payment.id, "succeeded", charge_id)
            if payment.invoice_id is not None:
                self.invoices.apply_payment(ctx, payment.invoice_id, payment.amount_minor)

    def charge_with_retry(self, ctx, payment):
        """Used by the dunning job: attempt the payment until it settles,
        backing off between gateway timeouts, within max_charge_attempts."""
        delay = self.settings.retry_backoff
        while payment.status != "succeeded" and \
                payment.attempts < self.settings.max_charge_attempts:
            # a fresh key per attempt, otherwise the gateway would replay
            # the cached outcome of the previous attempt
            key = f"payment-{payment.id}-{uuid.uuid4().hex[:8]}"
            before = payment.attempts
            payment = self.attempt(ctx, payment, idempotency_key=key)
            if payment.status != "pending" or payment.attempts == before:
                break
            self.sleep(delay)
            delay *= 2
        return payment
