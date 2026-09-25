#!/usr/bin/env python3
"""Unpack a pipe file back into JSON. See SPEC.md for the format."""

import json
import sys
from pathlib import Path


def unescape(text: str) -> str:
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            if i + 1 >= len(text):
                raise ValueError("dangling escape")
            nxt = text[i + 1]
            if nxt == "\\":
                out.append("\\")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "n":
                out.append("\n")
            elif nxt == "r":
                out.append("\r")
            else:
                raise ValueError(f"invalid escape \\{nxt}")
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def unpack(in_path: Path, out_path: Path) -> None:
    raw = in_path.read_text()
    if not raw.endswith("\n"):
        raise ValueError("pipe file must end with a newline")
    lines = raw.split("\n")
    if lines[0] != "pipe1":
        raise ValueError("bad header")
    data = {}
    for line in lines[1:]:
        if not line:
            continue
        if "\t" not in line:
            raise ValueError("missing tab")
        key, rest = line.split("\t", 1)
        if not rest:
            raise ValueError("missing typecode")
        code = rest[0]
        body = rest[1:]
        if code == "s":
            value = unescape(body)
        elif code == "i":
            if not body or not (body[1:].isdigit() if body[0] == "-" and len(body) > 1
                                else body.isdigit()):
                raise ValueError(f"bad int {body}")
            value = int(body)
        elif code == "b":
            if body not in ("true", "false"):
                raise ValueError(f"bad bool {body}")
            value = body == "true"
        elif code == "f":
            try:
                value = float(body)
            except ValueError:
                raise ValueError(f"bad float {body}")
        elif code == "n":
            if body != "":
                raise ValueError("null must be empty")
            value = None
        else:
            raise ValueError(f"bad typecode {code}")
        data[unescape(key)] = value
    out_path.write_text(json.dumps(data, indent=2) + "\n")


def main() -> None:
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        unpack(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
