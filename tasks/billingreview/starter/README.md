# billing

Multi-tenant invoicing and payments. `billing.api.App(settings).handle()`
takes a `billing.http.Request` and returns a `billing.http.Response`; the
HTTP transport is out of scope. Errors are `{"error": message}`.

## Tenancy (security boundary)

Every customer, invoice, payment and refund belongs to exactly one tenant.
A request authenticates with `Authorization: Bearer <API key>`; the key
identifies a user, and the user belongs to one tenant. **A request can
only ever see or change rows of its own tenant**: rows of another tenant
answer 404, exactly like ids that do not exist.

Platform staff (`users.is_staff = 1`) are the only exception: they may send
`X-Tenant-Id: <id>` to act inside another tenant. Any other user sending
that header gets 403.

## Roles

Each user has one role. Roles are ordered `viewer < billing < admin`, and a
higher role can do everything a lower one can.

| endpoint | minimum role |
|---|---|
| `GET /customers/<id>`, `GET /invoices`, `GET /invoices/<id>`, `GET /invoices/by-number/<number>` | viewer |
| `POST /customers`, `POST /invoices`, `POST /invoices/<id>/issue`, `POST /invoices/<id>/pay` | billing |
| `POST /invoices/<id>/void`, `POST /payments/<id>/refund` | admin |

A role that is too low gets 403.

## Money

Amounts are integers of the currency's minor unit (cents; yen have
none). Floats never touch money. Invoice lines may be priced in another
currency; they are converted with `settings.fx_rates` and the converted
unit price is rounded `ROUND_HALF_EVEN` to the invoice currency's minor
unit.

## Invoices

`draft -> open -> paid`; a draft or an unpaid open invoice can be voided.
Numbers (`INV-00001`, ...) are unique per tenant. `paid` is the sum of
succeeded payments minus succeeded refunds; an invoice is `paid` while
`paid >= total`.

## Payments and the gateway

`POST /invoices/<id>/pay` charges the outstanding amount. The payment row
is written first; its gateway idempotency key is derived from the payment
id and **never changes**. The gateway is idempotent per key, so repeating
a charge with the same key never moves money twice. A gateway timeout
leaves the payment `pending`: the charge may or may not have happened, and
the signed webhook (or a retry with the same key) settles it. A decline
marks it `failed`.

Payments can also be account credits (`invoice_id` NULL): prepayments of
a customer that are not attached to an invoice yet. They are as much a
part of the ledger as any other payment.

The dunning job (`billing.jobs.dunning.run`) retries the latest unsettled
payment of each overdue invoice, at most `settings.max_charge_attempts`
attempts in total per payment.

## Refunds

`POST /payments/<id>/refund {"amount", "reason"}` refunds part or all of a
succeeded payment; refunds never exceed the payment. A refund is
`succeeded` only once the gateway has confirmed it (in its response or
by webhook); only then does it reduce the invoice's `paid`. A declined
refund is `failed`; a timed-out refund stays `pending`.

## Webhooks

`POST /webhooks/gateway` carries gateway events (`payment.succeeded`,
`payment.failed`, `refund.succeeded`, `refund.failed`). Every request is
signed: `X-Signature: sha256=<hex HMAC-SHA256 of the raw body with
settings.webhook_secret>`. Requests without a valid signature are
rejected with 401. Each event id is processed at most once.

## Migrations

`billing/migrations/NNNN_*.py`, applied in order at startup, each in one
transaction. A migration must never lose rows.

## Tests

    python3 -m unittest discover -s tests
