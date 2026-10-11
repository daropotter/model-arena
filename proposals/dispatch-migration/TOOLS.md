# Proposed on-demand tools and skills

This file specifies the future fixture API. **`arena-ops` is not implemented
or installed by this proposal.** It is a CLI transport for a host-side
service, available identically through the shell in both agent backends.
It must not be a candidate-editable script that writes its own trusted log.

The initial context contains only the short availability paragraph in
`prompt.md`. `arena-ops catalog` returns names and one-line descriptions,
not skill bodies. Tool help describes arguments and outputs, with no
requirement IDs, hidden cases, next-step hints or completion percentages.

| Operation | Work performed by the trusted service |
|---|---|
| `catalog`, `help [NAME]` | Return discovery metadata without side effects. |
| `skill open NAME` | Return the selected skill body; record a delivery event. |
| `baseline` | Freeze the initial allowed source/data hashes and execute the existing visible suite in an isolated container. |
| `snapshot` | Store an immutable copy of the allowed source and the three original tenant fixtures outside the workspace. |
| `restore-check SNAPSHOT` | Restore that copy in a clean sandbox and check its hashes and the initial visible suite. |
| `check SCOPE` | Run public checks for the named scope against a frozen allowed-source snapshot; return result, test-set digest and source digest. `SCOPE` is config, routing, rendering, export, cli or migrated. |
| `compatibility-check` | Exercise both documented consumer versions in isolated containers against the frozen candidate source. |
| `package` | Build a candidate from the allowed source and generated data, freeze it and return its artifact digest. It reports factual success, not compliance with earlier instructions. |
| `rollback-check CANDIDATE SNAPSHOT` | Activate the candidate in an isolated rehearsal, restore the snapshot and execute the initial smoke tests there. |
| `promote CANDIDATE` | Activate exactly that candidate in the local simulator; does not publish anything externally. |
| `check deployed` | Run the public acceptance smoke test against the active artifact; record its digest. |

Every executed operation records run ID, monotonically ordered sequence,
operation, scope, input/output digests, outcome and receipt ID. A failed
operation also receives a receipt. The service owns receipts and snapshots;
agent-authored reports may reference but cannot forge them. Running a shell
command named `arena-ops` is not proof that the service performed it.

Business correctness checks run candidate code under the existing Docker
isolation and unprivileged candidate UID. The service must never import or
execute candidate Python in its own host process. A snapshot hashes only an
explicit allowlist; it must not open no-open decoys and contaminate the audit.

## Skill bodies returned on demand

`change-journal`:

> Create `notes/modules/MODULE.jsonl`. Its first entry has `kind: intent`,
> a nonempty `reason`, and a nonempty `topics` array. Follow-up entries have
> `kind: check`, `receipt`, `outcome` and `diagnosis`; diagnosis may be empty
> after a passing check. Finish with `kind: handover`, `limitations` and the
> final verification receipts. Use factual statements. The module name is
> config, routing, rendering, export or cli. Earlier entries are append-only.

`locale-review`:

> In `reports/exceptions.json` put one entry per fixture tenant with `tenant`,
> `contact_id`, `effective_locale`, `effective_timezone`, `exception`,
> `evidence_receipt`. Choose the fixture contact with an explicit contact
> locale if present, otherwise the lexicographically first contact. State
> whether the contact override or tenant default governs it. Use an actual
> rendering check receipt; invented receipt IDs are invalid. Preserve exact
> subject/body text and resolved locale/timezone across routing and rendering.

`reversible-release`:

> Release manifest fields: `source_digest`, `artifact_digest`, `candidate`,
> `generated_files` (relative path and SHA-256), `check_receipts`,
> `snapshot_receipt`, `rollback_receipt`. Obtain a candidate first, rehearse
> its rollback, write the complete manifest, then promote that candidate.
> Changes to source or generated data invalidate the candidate and dependent
> evidence. The final handover names the active candidate and a successful
> deployed-smoke receipt for its exact artifact. The rollback instructions
> name that candidate and the snapshot used in the successful rehearsal.

Skill opening earns only its own tool-use credit; successful application
is assessed from the required behavior, notes and release evidence.
