"""Refunds of succeeded payments."""

from ..db import transaction
from ..errors import BadRequest, Conflict, GatewayDeclined, GatewayTimeout


class RefundService:
    def __init__(self, repos, invoices, payments, gateway, audit, clock):
        self.repos = repos
        self.invoices = invoices
        self.payments = payments
        self.gateway = gateway
        self.audit = audit
        self.clock = clock

    def refund(self, ctx, payment_id, amount_minor, reason):
        payment = self.payments.get(ctx, payment_id)
        if payment.status != "succeeded":
            raise Conflict("only succeeded payments can be refunded")
        if type(amount_minor) is not int or amount_minor <= 0:
            raise BadRequest("amount must be a positive integer of minor units")
        if not isinstance(reason, str) or not reason.strip():
            raise BadRequest("a reason is required")
        with transaction(self.repos.conn):
            already = self.repos.refunds.refunded_total(payment.id)
            if already + amount_minor > payment.amount_minor:
                raise Conflict("refund exceeds the refundable amount")
            refund_id = self.repos.refunds.create(payment.id, amount_minor, reason,
                                                  int(self.clock()))
        self.audit.record(ctx.tenant_id, ctx.actor_id, "refund.start", refund_id)
        gateway_refund_id = None
        try:
            result = self.gateway.refund(payment.gateway_charge_id, amount_minor,
                                         f"refund-{refund_id}")
            gateway_refund_id = result.refund_id
        except GatewayDeclined:
            self.repos.refunds.settle(refund_id, "failed")
            raise Conflict("the gateway declined the refund")
        except GatewayTimeout:
            # the gateway queues refunds it has accepted; the webhook only
            # fills in the gateway id later
            pass
        self.complete(ctx, refund_id, gateway_refund_id)
        return self.repos.refunds.get(refund_id)

    def complete(self, ctx, refund_id, gateway_refund_id):
        refund = self.repos.refunds.get(refund_id)
        if refund.status != "pending":
            return
        payment = self.payments.get(ctx, refund.payment_id)
        with transaction(self.repos.conn):
            self.repos.refunds.settle(refund_id, "succeeded", gateway_refund_id)
            if payment.invoice_id is not None:
                self.invoices.unapply_payment(ctx, payment.invoice_id, refund.amount_minor)
