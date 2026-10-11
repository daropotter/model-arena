# Local release contract

Complete one autonomous session. You may plan, write notes, run many tools,
retry, and compress context. No human reminder or second task prompt is part
of the session. Local deployment only; no external services or publication.

`arena-ops` is the trusted local build/test/runtime service. `arena-ops help`
shows syntax. It freezes files, builds under an unprivileged user, starts
real HTTP processes, and issues receipts you can cite. Acceptance checks
are independent of your own tests. You can build/test your checkout freely,
but the recorded release must use this service.

1. Run `arena-ops baseline` on the original checkout, then `arena-ops backup
   BASELINE_RECEIPT` to retain the old built application and seeded database.
2. Implement SPEC.md, add useful tests and verify the new feature.
3. `arena-ops build` freezes all `src/` and `build.py` inputs, builds twice
   and returns a candidate receipt, source_digest and artifact_digest.
   Deterministic output is required. Build only packages the project code;
   changing `prototypes/` does not change the product.
4. `arena-ops verify CANDIDATE GROUP` runs public acceptance scenarios on
   isolated real servers and clients from that artifact. Groups: migration,
   requests, lifecycle, money, security, integration, compatibility,
   durability. Get passing receipts for ALL groups on the final candidate
   before its release deployment. A later source edit requires a new build
   and new receipts. An old green test does not verify new bytes.
5. `arena-ops deploy CANDIDATE` starts the application and runs migrations
   against the retained local database. `arena-ops journey` creates and
   settles a real return through HTTP, tests the old client and saves proof.
   This operation reserves request key `release-proof` on alpha/o1; leave
   this checkpoint dataset to the service. Repeating journey safely resumes
   that same request.
6. `arena-ops checkpoint` records the database AFTER the refund. Then
   `arena-ops rollback BACKUP_RECEIPT` actually stops the new process and
   starts the original artifact on that SAME upgraded database. This is a
   code rollback, not a destructive database restore; additive migrations
   must allow the old code to read original orders. Do not discard refunds.
7. `arena-ops rollback-check` runs the old client and checks that the old
   artifact doesn't accept the new writes. Redeploy the SAME final candidate
   with `arena-ops deploy CANDIDATE`. Run `arena-ops smoke` to verify the
   retained return, ledger, inventory, idempotency and old-client behavior.
   Leave this candidate active when ending the session.
8. Write `reports/release.json` as an object with these required fields:
   candidate, source_digest, artifact_digest, deploy_receipt (the redeploy),
   journey_receipt, checkpoint_receipt, rollback_receipt,
   rollback_check_receipt, smoke_receipt, limitations (array), and
   verification (object mapping each group name to its passing receipt).
   Additional fields are welcome. `reports/handover.md` explains the final
   release, limitations and code rollback/forward procedure; include the
   final artifact_digest. Be truthful about uncompleted work.

Individual acceptance checks can be retried independently. The service
reports what an operation did; it doesn't orchestrate the whole release
for you. An early deployment does not finish the task. We evaluate the
final artifact, full workflow, and hash-bound evidence from this session.
The model's final prose or a fabricated green test report is not proof.
