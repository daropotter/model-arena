"""CLI entry point: python3 -m ledger summarize <input.json> <output.json>."""

import json
import sys

from .core import summarize


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] != "summarize":
        print(
            "usage: python3 -m ledger summarize <input.json> <output.json>",
            file=sys.stderr,
        )
        return 2
    with open(argv[2]) as f:
        payload = json.load(f)
    result = summarize(payload)
    with open(argv[3], "w") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
