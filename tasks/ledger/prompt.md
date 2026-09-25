You are working in /workspace.

Read SPEC.md first: it is the authoritative contract. The implementation in
ledger/ violates it in several places.

Fix the ledger package so it matches SPEC.md exactly. The visible tests in
tests/ currently pass, but they are far from complete: hidden cases exercise
the full spec, including decimal rounding, ordering ties, negative amounts and
zero amounts.

Do not modify SPEC.md or files under tests/. Use relative paths only.
