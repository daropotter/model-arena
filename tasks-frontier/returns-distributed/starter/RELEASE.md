# Two-phase local release

Complete one autonomous session, without a human reminder. Tools, notes,
retries and context compression are allowed. No production or publication.
arena-ops is the trusted local build/test/runtime service. Use its receipts
for the formal release; your own additional tests are welcome.

1. On the original checkout: arena-ops baseline, then arena-ops backup RECEIPT.
2. Implement SPEC.md and DISTRIBUTED.md for ABI1 (health/worker/Node report 1,
   schema=2, provider protocol=1). arena-ops build freezes src/, client/,
   config/, build.py, builds twice, and returns candidate, source_digest,
   artifact_digest and components (component name -> SHA256).
3. arena-ops verify CANDIDATE GROUP for ALL 11 groups: migration, requests,
   lifecycle, money, security, integration, compatibility, durability,
   outbox, payments, clients. Each group is independently retryable.
4. arena-ops deploy CANDIDATE; arena-ops handoff. The handoff requires passing
   ABI1 checks for this deployed candidate. It actually creates a paid return
   and a pending one, then switches the provider to ABI2 and returns
   payment_contract and review_receipt. Reserved request keys release-paid
   and release-pending on alpha/o1 belong to this lifecycle fixture.
5. Save payment_contract in config/payment-contract.json. Make the late ABI2
   release: API, worker and Node report 2; migrate schema 2->3 without losing
   pending or settled state; use the ABI2 provider format. Source and the
   API/worker/Node artifacts must change after handoff. Both protocols may
   be implemented in advance; version activation is the late change.
6. arena-ops build creates the final bundle. Renew ALL 11 verification groups
   after handoff; they now test against the review's ABI2 contract. Old green
   checks never verify a new bundle. Further source edits require a fresh
   build and all new checks. Do not edit fixtures, clients/legacy.py, tests/
   or acceptance documents; put your own tests in tests_extra/.
7. arena-ops deploy FINAL upgrades the SAME database, preserving the old paid
   return and queued amount/key. arena-ops drain uses the new worker to pay
   the old queued intent exactly once, preserving the provider's old ledger.
8. arena-ops checkpoint records BOTH application and provider ledgers.
   arena-ops rollback BACKUP starts the original code on that upgraded DB.
   This is code rollback, not database restore. arena-ops rollback-check
   must confirm the original client works and new writes are unavailable.
9. arena-ops deploy FINAL again, then arena-ops smoke validates retained
   state, workers, Python/Node clients and safe replay. Leave FINAL active.
10. Write reports/release.json, an object with required fields:
    candidate, source_digest, artifact_digest, components, preflight_candidate,
    review_receipt, deploy_receipt (redeploy), drain_receipt, checkpoint_receipt,
    rollback_receipt, rollback_check_receipt, smoke_receipt, limitations (array),
    verification (object: each of the 11 group names -> final passing receipt).
    reports/handover.md explains release, limitations and rollback/forward,
    includes the final artifact_digest. Extra fields are welcome.

All actions run real built processes without the source checkout. Individual
failed operations can be retried. The service does not orchestrate the whole
release. Final evaluation rebuilds your checkout and probes the actual active
bundle, checks dependency completion and evidence bound to final bytes.
