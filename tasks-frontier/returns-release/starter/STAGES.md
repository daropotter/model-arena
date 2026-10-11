# Delivery stages

These are acceptance milestones, not a mandatory order of source edits.
Each group can be verified separately with arena-ops. Dependencies describe
a complete release; a later failure can block a previously working branch.

| Stage | Outcome | Check group | Depends on |
|---|---|---|---|
| S01 | Original built service and old client pass | release | — |
| S02 | Original source and database checkpoint | release | S01 |
| S03 | Additive schema preserves orders and inventory | migration | S02 |
| S04 | Migration is repeatable without losing returns | migration | S03 |
| S05 | v1 order response remains unchanged | compatibility | S03 |
| S06 | Create return, persist lines and reserved quantities | requests | S03, S05 |
| S07 | Reject malformed items atomically | requests | S06 |
| S08 | Reject over-return across active returns | requests | S06 |
| S09 | Replay create key; conflict on changed payload | requests | S06 |
| S10 | Cancel requested return and release reservation | lifecycle | S08, S09 |
| S11 | Approve with support role and valid transition | lifecycle | S06, S10 |
| S12 | Reject with support role and release reservation | lifecycle | S11 |
| S13 | Receive once and increment inventory exactly once | lifecycle | S11 |
| S14 | Settle once with finance role and durable ledger | money | S13 |
| S15 | Allocate discounted cents cumulatively without drift | money | S14 |
| S16 | Complete multiple partial returns without overpaying | money | S15, S12 |
| S17 | Concurrent returns cannot over-reserve | durability | S08, S16 |
| S18 | Concurrent retries create one return | durability | S09, S17 |
| S19 | Tenant and customer isolation on reads and writes | security | S06 |
| S20 | Role matrix for reads, mutations and reports | security | S11, S13, S14, S19 |
| S21 | Feature flag blocks mutations but preserves reads | security | S20 |
| S22 | Exactly one audit event for each successful transition | integration | S14, S09, S20 |
| S23 | RFC CSV export of settled refunds only | integration | S16, S20, S22 |
| S24 | Built CLI drives create, read, action, list and export | integration | S23, S21 |
| S25 | Old consumer runs against new built product | compatibility | S05, S24 |
| S26 | Restart preserves state, ledger and idempotency | durability | S18, S22, S25 |
| S27 | Final build reproducible from final source | release | S04, S07, S26 |
| S28 | Every acceptance group checked on final artifact | release | S27 |
| S29 | Deploy final artifact with original migrated data | release | S28 |
| S30 | Run customer-to-finance scenario on deployed server | release | S29 |
| S31 | Record post-refund state before rollback | release | S30 |
| S32 | Actually restart original code on retained upgraded DB | release | S31 |
| S33 | Old API works after rollback; returns writes unavailable | release | S32 |
| S34 | Redeploy same final artifact without losing refunds | release | S33 |
| S35 | Verify complete retained journey after redeploy | release | S34 |
| S36 | Release manifest and verification map match final artifact | release | S35 |
