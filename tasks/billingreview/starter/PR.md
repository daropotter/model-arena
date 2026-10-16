# Tenant context refactor, payment tenancy, dunning retries (BILL-204)

A large but mostly mechanical change. Please review carefully: it touches
the tenancy boundary, money and the payments ledger.

## Tenant scoping

- New `billing/tenancy.py`: `TenantContext(tenant_id, user)`. Every
  repository and service method now takes a context instead of
  `(tenant_id, user)` pairs. `TenantContext.system()` is for the dunning
  job and webhooks, which work across tenants; `within()` narrows it to
  one tenant once the row is known.
- New `billing/repos/base.py`: `ScopedRepo` with `_scoped()`, `_one()` and
  `_all()`, which append `AND tenant_id = ?` for every non-system
  context. Customer, invoice and payment repositories are built on it.
  `table` is a class constant, so the f-strings never see user input.
- Staff impersonation (`X-Tenant-Id`) moved from `App.actor()` into
  `TenantContext.for_user()`.

## Payments get a tenant_id

- Migration `0007_payments_tenant` adds `payments.tenant_id`
  (NOT NULL) and backfills it, so payments are scoped like every other
  table instead of through a join on customers. SQLite cannot add such a
  column in place, so the table is rebuilt.
- The migration runner learned `FOREIGN_KEYS_OFF = True` for rebuilds of
  referenced tables (refunds point at payments). The pragma does nothing
  inside a transaction, so it is switched before `BEGIN`, and
  `PRAGMA foreign_key_check` must come back clean before `COMMIT`.

## Roles

- `authz.Role` is now a `str` enum instead of a rank dictionary;
  `require(ctx, Role.X)` replaces `require(user, "x")`.

## Dunning retries

- `PaymentService.charge_with_retry()` replaces the one-shot `retry()`:
  the dunning job keeps retrying a payment through gateway timeouts with
  exponential backoff (`settings.retry_backoff`), still bounded by
  `max_charge_attempts`. The dunning job now walks overdue invoices of all
  tenants in one query.

## Smaller items

- Invoice reads go through a 30 s TTL cache (`billing/cache.py`); every
  invoice write goes through `InvoiceService._update()`, which
  invalidates the entry.
- `money.convert()` computes directly in minor units.
- Webhook signatures are compared with `hmac.compare_digest` (was `!=`).
- Refund timeouts: the gateway queues every refund it has accepted, so a
  timed-out refund is completed right away instead of waiting for the
  webhook.

Tests: updated for the new signatures; added a dunning retry test. All
tests pass.
