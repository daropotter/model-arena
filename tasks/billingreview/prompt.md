You are working in /workspace as the reviewer of a large pull request to
a multi-tenant billing service.

PR.md is the author's description, change.diff is the change (about 600
changed lines across 21 files), and the workspace already contains the
code after the change. README.md is the authoritative contract: tenant
isolation, roles, money rounding, payment idempotency, refunds, webhook
signatures and migrations. Where PR.md and README.md disagree, README.md
wins. You may read and run the code and its tests
(`python3 -m unittest discover -s tests`) and write throwaway scripts
under /tmp to confirm your suspicions.

Find the real problems this change introduces (security holes, money and
ledger errors, unintended behaviour changes) and write your review to
review.json exactly as REVIEW.md describes. Hidden grading compares your
findings with the known problems in the change; false positives cost
points, so report only what you can justify.

Do not modify any file other than review.json. Use relative paths only.
