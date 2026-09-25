# Order export normalization spec

This document is the authoritative contract. Where the implementation and this
document disagree, this document wins.

## CLI

```
python3 normalize.py <input.csv> <output.csv> <report.json>
```

Exit code 0 on success. `<output.csv>` and `<report.json>` are written (or
overwritten). The input file is never modified.

## Input

The input is an RFC 4180 CSV file, UTF-8, possibly with a BOM. Fields may be
quoted; quoted fields may contain commas, double quotes (escaped by doubling)
and newlines. The export may be a concatenation of several exports: the
canonical header line can appear again in the middle of the file, starting a
new section.

The first line of the file is always treated as a header and skipped.

A line whose trimmed content equals the canonical header
(`order_id,customer,amount,currency,date,status`, case-insensitive) is a
section boundary: it is skipped and is not otherwise significant. Empty lines
are skipped silently and are never counted as data rows.

Data rows have exactly 6 fields: `order_id, customer, amount, currency, date,
status`. Any row with a different field count is malformed.

## Canonicalization rules

### order_id

Trim leading/trailing whitespace. Must be non-empty; empty is malformed.

### customer

Trim leading/trailing whitespace and collapse any internal run of whitespace
(spaces, tabs or newlines) to a single space. May be empty (allowed).

### amount

Trim whitespace and strip leading/trailing currency symbols (`$`, `€`, `£`).

Accepted forms (regex notation, optional leading `-` in the first three):

- `-?\d+(\.\d+)?` — plain decimal.
- `-?\d{1,3}(,\d{3})+(\.\d+)?` — comma as thousands separator (groups of
  exactly 3 digits).
- `-?\d{1,3}(\.\d{3})+(,\d+)$` or `-?\d{1,3}(\.\d{3}){2,}$` — dot as
  thousands separator. A single dot group is only thousands when a comma
  decimal part follows (`1.234,50`); otherwise a single dot is the decimal
  separator (`1.005` = one and five thousandths, NOT `1005`).
- `(...)` — accounting parentheses mean negative. The inner number (without a
  sign) is one of the non-negative forms above.

Disambiguation rules, in order:

1. If the string contains a comma: a comma followed by exactly 3 digits and
   preceded by 1-3 digits is a thousands separator (`1,234.50`, `1,234`);
   otherwise the comma is a decimal separator and a dot thousands separator
   must be present (`1.234,50`). `45,00` is malformed (2-digit group).
2. If the string contains only dots: two or more groups of exactly 3 digits
   after the first 1-3 digits means thousands (`1.234.567`); a single dot is
   the decimal separator (`1.005`, `45.00`).

Anything else is malformed, for example `12.3.4`, `abc`, `--5`, `45,00`.

Canonical output uses a dot decimal separator, exactly 2 decimals, no thousands
separators, a leading `-` for negatives, e.g. `-1234.50`. An amount with more
than 2 decimals is rounded round-half-even to 2 decimals *before* everything
else (duplicate detection, totals).

### currency

Trim whitespace; uppercase. Empty means `EUR`. Must match exactly 3 ASCII
letters after uppercasing, otherwise the row is malformed.

### date

Trim whitespace. Accepted forms produce a canonical `YYYY-MM-DD`:

- `2026-01-05` (ISO)
- `01/05/2026` (US: month/day/year; month and day may be 1 or 2 digits)
- `Jan 7, 2026` (English abbreviated month, case-insensitive, day may be 1 or
  2 digits)

Any other content (including impossible dates such as `2026-13-05`) is
malformed.

### status

Trim whitespace; case-insensitive mapping to canonical values:

- `paid` → `paid`
- `pending`, `pend.` → `pending`
- `cancelled`, `canceled` → `cancelled`

Anything else is malformed.

## Duplicates

Two rows are duplicates when, after canonicalization, all six fields are
equal. Keep the first occurrence (in original input order) and count every
later one as a dropped duplicate (do not output it).

## Ordering

Output rows sorted by canonical `order_id` ascending using **character-wise
(lexicographic) comparison, not numeric** (so `"10" < "9"`). Rows sharing an
`order_id` keep their original relative order (stable).

## Output CSV

Header line exactly:

```
order_id,customer,amount,currency,date,status
```

then one line per kept row with canonical values, in the required order,
comma-separated. Fields must be quoted if (and only if) needed per RFC 4180:
they contain a comma, a double quote or a newline. Use `\n` line endings and a
trailing newline after the last row.

## Report JSON

Object with exactly these keys:

```json
{
  "input_rows": 0,
  "output_rows": 0,
  "dropped_rows": 0,
  "dropped_duplicates": 0,
  "dropped_malformed": 0,
  "total_amount_by_currency": {}
}
```

- `input_rows`: data rows read, i.e. excluding headers, section-boundary lines
  and empty lines; including malformed and duplicate rows.
- `output_rows`: rows written to the output CSV.
- `dropped_rows`: `dropped_duplicates + dropped_malformed`.
- `total_amount_by_currency`: for each canonical currency seen in kept rows,
  the sum of canonical amounts as a string with exactly 2 decimals, dot
  separator (round-half-even if needed). Currencies only in dropped rows do not
  appear. An export with no kept rows gives `{}`.

## Idempotency

Running `normalize.py` on its own canonical output must produce a
byte-identical output CSV, and a report where `dropped_rows` is 0 and all
counts equal the row count.
