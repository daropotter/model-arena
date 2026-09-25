#!/usr/bin/env python3
"""Independent reference solution for the datajanitor task.

Deliberately does NOT import the grader's reference.py: verify_tasks.py must
compare two independent implementations of SPEC.md, otherwise a bug in the
grader's reference would validate itself.
"""

import csv
import datetime
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_EVEN

HEADER = "order_id,customer,amount,currency,date,status"

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

RE_PLAIN = re.compile(r"^\d+(\.\d+)?$")
RE_COMMA_TH = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")
RE_DOT_TH = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)$|^\d{1,3}(\.\d{3}){2,}$")

RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
RE_US = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
RE_MON = re.compile(r"^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})$")

STATUSES = {"paid": "paid", "pending": "pending", "pend.": "pending",
            "cancelled": "cancelled", "canceled": "cancelled"}


def to_decimal(negative, int_part, frac):
    digits = int_part.replace(",", "").replace(".", "")
    value = Decimal(digits + ("." + frac if frac else ""))
    return -value if negative else value


def parse_amount(raw):
    s = raw.strip()
    for symbol in ("$", "€", "£"):
        s = s.replace(symbol, "")
    s = s.strip()
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        negative = True
        s = s[1:].strip()
    if not s:
        return None
    if RE_COMMA_TH.match(s):
        # comma groups of 3 -> thousands; optional dot decimal part
        int_part, _, frac = s.partition(".")
        return to_decimal(negative, int_part, frac)
    if RE_DOT_TH.match(s):
        int_part, _, frac = s.partition(",")
        return to_decimal(negative, int_part, frac)
    if RE_PLAIN.match(s):
        int_part, _, frac = s.partition(".")
        return to_decimal(negative, int_part, frac)
    return None


def parse_date(raw):
    s = raw.strip()
    m = RE_ISO.match(s)
    if m:
        return make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = RE_US.match(s)
    if m:
        return make_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = RE_MON.match(s)
    if m:
        month = MONTHS.get(m.group(1).lower())
        if month:
            return make_date(int(m.group(3)), month, int(m.group(2)))
    return None


def make_date(year, month, day):
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def format_amount(value):
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    if rounded == 0:
        rounded = Decimal("0.00")
    return str(rounded)


def canonicalize(row):
    order_id = row[0].strip()
    if not order_id:
        return None
    customer = " ".join(row[1].split())
    amount = parse_amount(row[2])
    if amount is None:
        return None
    currency = row[3].strip().upper() or "EUR"
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return None
    date = parse_date(row[4])
    if date is None:
        return None
    status = STATUSES.get(row[5].strip().lower())
    if status is None:
        return None
    return [order_id, customer, amount, currency, date, status]


def quote(field):
    if any(c in field for c in (",", '"', "\n")):
        return '"' + field.replace('"', '""') + '"'
    return field


def normalize(input_path, output_path, report_path):
    with open(input_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    input_rows = 0
    kept = []
    seen = set()
    duplicates = 0
    malformed = 0

    for index, row in enumerate(rows):
        if index == 0:
            continue
        if len(row) == 1 and not row[0].strip():
            continue
        if not any(field.strip() for field in row):
            continue
        if [f.strip().lower() for f in row] == HEADER.split(","):
            continue
        input_rows += 1
        if len(row) != 6:
            malformed += 1
            continue
        canon = canonicalize(row)
        if canon is None:
            malformed += 1
            continue
        key = (canon[0], canon[1], format_amount(canon[2]), canon[3],
               canon[4], canon[5])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        kept.append(canon)

    kept.sort(key=lambda r: r[0])

    lines = [HEADER]
    for row in kept:
        lines.append(",".join([quote(row[0]), quote(row[1]),
                               format_amount(row[2]), row[3], row[4],
                               quote(row[5])]))
    with open(output_path, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")

    totals = {}
    for row in kept:
        totals[row[3]] = totals.get(row[3], Decimal("0")) + Decimal(
            format_amount(row[2]))
    report = {
        "input_rows": input_rows,
        "output_rows": len(kept),
        "dropped_rows": duplicates + malformed,
        "dropped_duplicates": duplicates,
        "dropped_malformed": malformed,
        "total_amount_by_currency": {k: format_amount(v)
                                     for k, v in totals.items()},
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")


def main(argv):
    if len(argv) != 4:
        print("usage: normalize.py <input.csv> <output.csv> <report.json>",
              file=sys.stderr)
        return 2
    normalize(argv[1], argv[2], argv[3])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
