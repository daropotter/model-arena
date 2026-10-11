# Acceptance milestones

48 milestones; each is independently scored. Dependency closure is a separate
metric and requires ALL prerequisites. Functional behavior is measured on the
final ABI2 product; preflight evidence refers to ABI1.

| ID | Milestone | Requires |
|---|---|---|
| S01 | Original built service and old client pass |  |
| S02 | Original source and database checkpoint | S01 |
| S03 | Additive schema preserves orders and inventory | S02 |
| S04 | Migration is repeatable without losing returns | S03 |
| S05 | v1 order response remains unchanged | S03 |
| S06 | Create return, persist lines and reserved quantities | S03, S05 |
| S07 | Reject malformed items atomically | S06 |
| S08 | Reject over-return across active returns | S06 |
| S09 | Replay create key; conflict on changed payload | S06 |
| S10 | Cancel requested return and release reservation | S08, S09 |
| S11 | Approve with support role and valid transition | S06, S10 |
| S12 | Reject with support role and release reservation | S11 |
| S13 | Receive once and increment inventory exactly once | S11 |
| S14 | Queue and deliver refund through a separate worker exactly once | S13 |
| S15 | Allocate discounted cents cumulatively without drift | S14 |
| S16 | Complete multiple partial returns without overpaying | S15, S12 |
| S17 | Concurrent returns cannot over-reserve | S08, S16 |
| S18 | Concurrent retries create one return | S09, S17 |
| S19 | Tenant and customer isolation on reads and writes | S06 |
| S20 | Role matrix for reads, mutations and reports | S11, S13, S14, S19 |
| S21 | Feature flag blocks mutations but preserves reads | S20 |
| S22 | Exactly one audit event for each successful transition | S14, S09, S20 |
| S23 | RFC CSV export of settled refunds only | S16, S20, S22 |
| S24 | Built CLI drives create, read, action, list and export | S23, S21 |
| S25 | Old consumer runs against new built product | S05, S24 |
| S26 | Restart and migrate without losing settled or pending work | S18, S22, S25 |
| S27 | API enqueues immutable amount and provider key atomically | S14, S16 |
| S28 | Queued refunds survive an unavailable provider | S27 |
| S29 | Lost provider reply cannot charge twice | S28 |
| S30 | Worker killed after acceptance recovers expired lease | S29 |
| S31 | Concurrent workers lease and settle every job once | S30 |
| S32 | Retry schedule and dead-letter/manual retry are durable | S31 |
| S33 | Permanent decline preserves stock and money reservation | S32 |
| S34 | Tenant-bound cursor pagination is stable | S19, S24 |
| S35 | Built Node client reads and requests queued payouts | S34, S33 |
| S36 | Provider contract and tenant merchant mapping are honored | S35 |
| S37 | ABI1 candidate verified in all 11 groups | S04, S07, S26, S36 |
| S38 | Checked ABI1 deployed with paid and outstanding jobs; receive ABI2 contract | S37 |
| S39 | Actual ABI2 source change after handoff and rebuilt four-artifact bundle | S38 |
| S40 | All final checks renewed against ABI2 bundle and review contract | S39 |
| S41 | Upgrade existing database and retain queued amount/idempotency identity | S40 |
| S42 | ABI2 worker drains ABI1-created pending refund exactly once | S41 |
| S43 | Checkpoint both application database and provider ledger | S42 |
| S44 | Run original code without deleting pending or paid financial data | S43 |
| S45 | Old order consumer works after code rollback | S44 |
| S46 | Redeploy ABI2 bundle with both ledgers retained | S45 |
| S47 | Final restarted product, workers and both clients satisfy retained journey | S46 |
| S48 | Manifest binds both builds, review, all components and fresh tests | S47 |
