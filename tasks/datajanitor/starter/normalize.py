#!/usr/bin/env python3
"""Normalize order CSV exports. See SPEC.md.

This implementation only handles the simple happy path.
"""

import json
import sys


HEADER = "order_id,customer,amount,currency,date,status"

STATUS_MAP = {
    "paid": "paid",
    "pending": "pending",
    "cancelled": "cancelled",
}


def clean_amount(raw):
    value = float(raw.replace("$", "").strip())
    return f"{value:.2f}"


def clean_date(raw):
    return raw.strip()


def normalize_row(fields):
    order_id = fields[0].strip()
    customer = " ".join(fields[1].split())
    amount = clean_amount(fields[2])
    currency = fields[3].strip().upper() or "EUR"
    date = clean_date(fields[4])
    status = STATUS_MAP.get(fields[5].strip().lower(), fields[5].strip().lower())
    return [order_id, customer, amount, currency, date, status]


def main(argv):
    if len(argv) != 4:
        print("usage: normalize.py <input.csv> <output.csv> <report.json>",
              file=sys.stderr)
        return 2

    with open(argv[1], newline="") as f:
        lines = f.read().splitlines()

    rows = []
    input_rows = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        input_rows += 1
        fields = line.split(",")
        if len(fields) != 6:
            continue
        rows.append(normalize_row(fields))

    rows.sort(key=lambda r: r[0])

    with open(argv[2], "w", newline="") as f:
        f.write(HEADER + "\n")
        for row in rows:
            f.write(",".join(row) + "\n")

    totals = {}
    for row in rows:
        totals[row[3]] = totals.get(row[3], 0.0) + float(row[2])

    report = {
        "input_rows": input_rows,
        "output_rows": len(rows),
        "dropped_rows": input_rows - len(rows),
        "dropped_duplicates": 0,
        "dropped_malformed": input_rows - len(rows),
        "total_amount_by_currency": {k: f"{v:.2f}" for k, v in totals.items()},
    }
    with open(argv[3], "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
