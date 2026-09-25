#!/usr/bin/env python3
"""Pack a JSON object into a pipe file. See SPEC.md for the format."""

import json
import sys
from pathlib import Path


def escape(text: str) -> str:
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(ch)
    return "".join(out)


def typecode(value):
    if isinstance(value, str):
        return "s"
    if isinstance(value, bool):
        return "b"
    if isinstance(value, int):
        return "i"
    if isinstance(value, float):
        return "f"
    if value is None:
        return "n"
    raise ValueError(f"unsupported type: {type(value)}")


def pack(in_path: Path, out_path: Path) -> None:
    data = json.loads(in_path.read_text())
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    lines = ["pipe1"]
    for key in sorted(data.keys()):
        value = data[key]
        code = typecode(value)
        if code == "s":
            body = escape(value)
        elif code == "i":
            body = str(value)
        elif code == "b":
            body = "true" if value else "false"
        elif code == "f":
            body = repr(value)
        else:
            body = ""
        lines.append(f"{escape(key)}\t{code}{body}")
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        pack(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
