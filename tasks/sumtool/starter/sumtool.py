#!/usr/bin/env python3
"""Sum a comma-separated list of numbers, printed as a plain decimal.

Contract of parse_numbers(text):
  - `text` is a comma-separated list of decimal numbers.
  - A number may be an integer (no dot) or a decimal (dot required),
    with an optional leading sign (+ or -).
  - No currency symbols and no scientific notation:
    such a token makes the whole call fail.
  - Whitespace around tokens is ignored.
  - The result is the arithmetic sum, printed without unnecessary
    trailing zeros (e.g. "2", "-0.5", not "2.00"), but decimal values
    always keep their fractional part (e.g. "2.5", "0.5").
  - On invalid input, print "error" to stderr and exit 1.
  - On success, print the sum to stdout (just the number and a newline)
    and exit 0.
"""

import sys


def parse_numbers(text: str) -> str:
    tokens = [t.strip() for t in text.split(",")]
    if not tokens or any(t == "" for t in tokens):
        print("error", file=sys.stderr)
        sys.exit(1)

    total = 0
    for token in tokens:
        if not token.replace("+", "").replace("-", "").isdigit():
            print("error", file=sys.stderr)
            sys.exit(1)
        total += int(token)

    if total == int(total):
        return str(int(total))
    return str(total)


def main() -> None:
    if len(sys.argv) != 2:
        print("error", file=sys.stderr)
        sys.exit(1)
    print(parse_numbers(sys.argv[1]))


if __name__ == "__main__":
    main()
