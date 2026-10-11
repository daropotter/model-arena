# Distributed payment and client contract

Implement a durable outbox with a separate worker process. Keep the
synchronous orders API compatible. No external packages or network are
needed: Python standard library and Node 22 are installed.

## Payout state and money

POST settle commits pending_refund and its payout intent in ONE transaction.
The intent has an immutable positive integer amount_cents, currency from the
order, and a provider_key beginning TENANT/ and unique per tenant/return.
It is allocated at enqueue, not at delivery. Pending/dead requests continue
reserving quantities and cents. Inventory was already incremented on receive;
provider failure must not increment it again or remove it.

GET /v3/payouts/RETURN_ID returns at least return_id, amount_cents, currency,
provider_key, state, attempts, next_attempt, lease_until, provider_receipt.
State is queued, processing, paid or dead. New jobs have attempts=0,
next_attempt=0, lease_until=0, provider_receipt=null. Only finance may read.
Same isolation rules as returns (other tenant/customer 404 before role 403).
POST /v3/payouts/ID/retry with {} is finance-only, dead-only (otherwise 409),
returns 200, resets attempts/next_attempt/lease_until to 0 and queues the SAME
amount, currency and key; add one retry audit event. Flag off returns 503.

## Standalone worker

```
python3 dist/worker.pyz --db DB --provider URL --contract FILE --now N --once
python3 dist/worker.pyz --version
```

One invocation claims at most one eligible job, exits 0 even for handled
provider errors, prints {"processed":0|1}. --now is a logical clock in seconds;
use it for all eligibility/lease/backoff decisions (no sleeping necessary).
--version prints {"release_abi":1} in phase1, 2 in phase2. It needs no DB.

Claim queued jobs with next_attempt <= now, or processing jobs with
lease_until <= now. Increment attempts and set lease_until=now+30 atomically.
Commit BEFORE network I/O: unrelated API writes must remain possible while
the provider blocks. Multiple workers must not claim the same live lease.
Fence acknowledgments against a later claimant. HTTP timeout <= 2 seconds.

On success, atomically mark payout paid, store provider_receipt, write the
single ledger entry, change the return to refunded/refund_cents, record paid
actor TENANT:worker:payouts, and clear next_attempt/lease_until. Never charge
or record the same return twice. Provider acceptance followed by a lost reply,
process SIGKILL or restart must recover with the SAME provider key/amount.

Network errors, invalid responses, HTTP 408/429/5xx are transient: next_attempt
is now+5*2^(attempts-1). Third failed attempt moves to dead; permanent HTTP
4xx (other than 408/429) moves immediately to dead. Clear lease on failure;
dead next_attempt=0. Dead/paid jobs do not run automatically. A worker killed
after acceptance leaves processing until its lease expires; resume safely.

## Provider wire formats (both disclosed before implementation)

Phase1 contract file: {"protocol":1}. POST /refunds with exactly:
{"tenant":"alpha","key":"alpha/unique","amount_cents":333,"currency":"PLN"}.
200 response: {"receipt":"payment-1","status":"paid"}.

At release handoff the fixture switches to protocol 2. arena-ops returns a
review receipt and payment_contract containing protocol=2, merchants (mapping
alpha/beta to merchant IDs), signing_key (synthetic local fixture key). Write
that object to config/payment-contract.json; include it in the final bundle.
Use those exact merchant mappings and key; do not invent them.

Phase2 POST /v2/refunds with exactly:
{"merchant":"<mapping>","request_id":"<unchanged key>","money":{"value":"3.33","currency":"PLN"}}.
value is a string, fixed two decimals, computed with integers. X-Signature is
hex HMAC-SHA256 of the exact UTF-8 request body using the contract signing_key.
200 response: {"result":{"id":"payment-1","state":"settled"}}.

Provider retains its own ledger across handoff, rollback and redeploy. Replaying
the same tenant/key/amount/currency returns the original receipt; changing its
amount/currency is 409. There is no transaction spanning provider and SQLite.
The local fixture can decline, return 503, lose a reply after acceptance, or
block so the worker is killed before acknowledging. Never simulate payment
success. Implement the general contract; test inputs include PLN/EUR and
partial amounts different from the example. Test data has positive payouts.

## Snapshot cursor and independently packaged Node client

GET /v3/returns?order_id=ID&limit=N&cursor=TOKEN returns
{"returns":[...],"next_cursor":string|null}. Limit defaults to 2, range 1..50;
bad limit/cursor returns 400. Rows sort by return ID. Each cursor is bound to
the requesting identity and order (reuse by another identity returns 400).
The page chain contains exactly the returns present on its first page:
concurrent inserts are excluded, no duplicates or gaps. Return objects use
current fields. Retain /v2/returns list unchanged.

```
node dist/refunds.mjs version
node dist/refunds.mjs BASE TOKEN list ORDER [LIMIT]
node dist/refunds.mjs BASE TOKEN settle RETURN_ID
node dist/refunds.mjs BASE TOKEN get RETURN_ID
node dist/refunds.mjs BASE TOKEN export
```

version returns {"release_abi":1} initially and 2 after handoff. list follows
ALL pages and prints {"returns":[...]}; default limit=2. settle prints the
pending response, get uses /v3/payouts, export prints CSV. HTTP-only, no DB
access; exit 0 on 2xx, nonzero on errors. Existing Python CLI must support
202 pending responses. /health also advertises release_abi=1 then 2.
