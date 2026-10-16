"""Dunning: retry the latest unsettled payment of every overdue invoice,
up to settings.max_charge_attempts attempts per payment."""

from ..tenancy import TenantContext


def run(app, today):
    """`today` is an ISO date. Returns the ids of payments retried."""
    retried = []
    system = TenantContext.system()
    for invoice in app.repos.invoices.overdue(system, today):
        ctx = system.within(invoice.tenant_id)
        payments = app.repos.payments.for_invoice(ctx, invoice.id)
        if not payments or payments[-1].status == "succeeded":
            continue
        latest = payments[-1]
        after = app.payments.charge_with_retry(ctx, latest)
        if after.attempts != latest.attempts:
            retried.append(latest.id)
    return retried
