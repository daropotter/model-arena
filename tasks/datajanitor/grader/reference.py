"""Reference implementation of the order export normalization spec.

Used by the hidden grader and by verify_tasks.py (via solution/) to check the
grader itself. Deterministic, stdlib only.
"""

import csv
import datetime
import io
import json
import re
from decimal import Decimal, ROUND_HALF_EVEN

HEADER = "order_id,customer,amount,currency,date,status"

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

PLAIN = re.compile(r"^\d+(\.\d+)?$")
COMMA_THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")
# A dot is a thousands separator only when unambiguous: either a comma is
# present as the decimal separator, or there are at least two dot groups.
DOT_THOUSANDS = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)$|^\d{1,3}(\.\d{3}){2,}$")

DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
DATE_US = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
DATE_MON = re.compile(r"^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})$")

STATUS_MAP = {
    "paid": "paid",
    "pending": "pending",
    "pend.": "pending",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def _decimal(neg, int_part, frac):
    digits = re.sub(r"[.,]", "", int_part)
    value = Decimal(digits + ("." + frac if frac else ""))
    return -value if neg else value


def parse_amount(raw):
    s = raw.strip().strip("$€£").strip()
    if not s:
        return None
    if s.startswith("(") and s.endswith(")"):
        return _parse_unsigned(s[1:-1].strip(), negate=True)
    neg = s.startswith("-")
    body = s[1:].strip() if neg else s
    return _parse_unsigned(body, negate=neg)


def _parse_unsigned(s, negate):
    if not s:
        return None
    # Precedence matters: `1,234.50` is comma-thousands, `1.234,50` is
    # dot-thousands, `1.005` is a plain decimal (see SPEC.md).
    if COMMA_THOUSANDS.match(s):
        int_part, _, frac = s.partition(".")
        return _decimal(negate, int_part, frac)
    if DOT_THOUSANDS.match(s):
        int_part, _, frac = s.partition(",")
        return _decimal(negate, int_part, frac)
    if PLAIN.match(s):
        int_part, _, frac = s.partition(".")
        return _decimal(negate, int_part, frac)
    return None


def parse_date(raw):
    s = raw.strip()
    m = DATE_ISO.match(s)
    if m:
        return _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = DATE_US.match(s)
    if m:
        return _mk_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = DATE_MON.match(s)
    if m:
        mo = MONTHS.get(m.group(1).lower())
        if mo:
            return _mk_date(int(m.group(3)), mo, int(m.group(2)))
    return None


def _mk_date(y, mo, d):
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_status(raw):
    return STATUS_MAP.get(raw.strip().lower())


def money(value):
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        # canonical output never has a negative zero, and always 2 decimals
        rounded = Decimal("0.00")
    return str(rounded)


def canonicalize(fields):
    order_id = fields[0].strip()
    if not order_id:
        return None
    customer = " ".join(fields[1].split())
    amount = parse_amount(fields[2])
    if amount is None:
        return None
    currency = fields[3].strip().upper() or "EUR"
    if not re.match(r"^[A-Z]{3}$", currency):
        return None
    date = parse_date(fields[4])
    if date is None:
        return None
    status = parse_status(fields[5])
    if status is None:
        return None
    return [order_id, customer, amount, currency, date, status]


def _quote(field):
    if any(c in field for c in (",", '"', "\n")):
        return '"' + field.replace('"', '""') + '"'
    return field


def normalize(input_text, output_path, report_path):
    rows = list(csv.reader(io.StringIO(input_text)))
    input_rows = 0
    kept = []
    seen = set()
    dropped_dup = 0
    dropped_mal = 0

    for i, row in enumerate(rows):
        if i == 0:
            continue
        if len(row) == 1 and not row[0].strip():
            continue
        if not any(f.strip() for f in row):
            continue
        if [f.strip().lower() for f in row] == HEADER.split(","):
            continue
        input_rows += 1
        if len(row) != 6:
            dropped_mal += 1
            continue
        canon = canonicalize(row)
        if canon is None:
            dropped_mal += 1
            continue
        key = (canon[0], canon[1], money(canon[2]), canon[3], canon[4], canon[5])
        if key in seen:
            dropped_dup += 1
            continue
        seen.add(key)
        kept.append(canon)

    kept.sort(key=lambda r: r[0])

    lines = [HEADER]
    for row in kept:
        lines.append(",".join([
            _quote(row[0]), _quote(row[1]), money(row[2]),
            row[3], row[4], _quote(row[5]),
        ]))
    output_text = "\n".join(lines) + "\n"

    # SPEC.md: amounts are rounded to 2 decimals *before* everything else,
    # including totals. Sum the canonical (rounded) amounts, not the raw ones.
    totals = {}
    for row in kept:
        totals[row[3]] = totals.get(row[3], Decimal("0")) + Decimal(
            money(row[2]))

    report = {
        "input_rows": input_rows,
        "output_rows": len(kept),
        "dropped_rows": dropped_dup + dropped_mal,
        "dropped_duplicates": dropped_dup,
        "dropped_malformed": dropped_mal,
        "total_amount_by_currency": {k: money(v) for k, v in totals.items()},
    }

    with open(output_path, "w", newline="") as f:
        f.write(output_text)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return output_text, report


def normalize_files(in_path, output_path, report_path):
    with open(in_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    return normalize(text, output_path, report_path)
