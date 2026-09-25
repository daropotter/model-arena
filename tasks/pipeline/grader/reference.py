#!/usr/bin/env python3
"""Reference implementation of SPEC.md. Used only by the hidden grader."""

import json
from pathlib import Path


def escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("\t", "\\t")
            .replace("\n", "\\n").replace("\r", "\\r"))


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


def pack_reference(in_path: Path, out_path: Path) -> None:
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


def unpack_reference(in_path: Path, out_path: Path) -> None:
    raw = in_path.read_text()
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
            try:
                value = int(body)
            except ValueError:
                raise ValueError(f"bad int {body}")
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
