You are working in /workspace.

An order system dumps messy CSV exports (see data/ and SPEC.md). Build
normalize.py so it converts any export into the canonical CSV described in
SPEC.md and emits the report JSON.

Run it as:

    python3 normalize.py <input.csv> <output.csv> <report.json>

SPEC.md is the authoritative contract; read every rule, including amount
formats, date formats, duplicate handling, repeated headers, malformed rows,
BOM stripping and idempotency.

Do not modify SPEC.md, data/ or tests/. The visible tests cover only a small
part of the spec; hidden exports exercise the rest. Use relative paths only.
