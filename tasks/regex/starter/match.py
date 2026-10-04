#!/usr/bin/env python3
"""Evaluate a small regex against a string. See SPEC.md.

BUGGY: `*` is greedy and never backtracks, and alternation commits to the
first alternative without trying the rest of the pattern.
"""

import json
import sys
from pathlib import Path


def parse(pattern):
    """Return a list of tokens: ('lit', ch), ('class', set, neg), ('star',),
    ('group', tokens), ('alt',). Naive, no precedence handling."""
    # This parser is deliberately simplistic and buggy.
    tokens = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "(":
            # find matching close, no nesting support -> bug for nested groups
            j = pattern.find(")", i)
            if j == -1:
                raise ValueError("unbalanced parens")
            tokens.append(("group", parse(pattern[i + 1:j])))
            i = j + 1
        elif ch == "[":
            j = pattern.find("]", i)
            if j == -1:
                raise ValueError("unterminated class")
            body = pattern[i + 1:j]
            neg = body.startswith("^")
            if neg:
                body = body[1:]
            charset = set()
            k = 0
            while k < len(body):
                if k + 2 < len(body) and body[k + 1] == "-":
                    lo, hi = body[k], body[k + 2]
                    charset.update(chr(code) for code in
                                   range(ord(lo), ord(hi) + 1))
                    k += 3
                else:
                    charset.add(body[k])
                    k += 1
            tokens.append(("class", charset, neg))
            i = j + 1
        elif ch == "*":
            tokens.append(("star",))
            i += 1
        elif ch == "|":
            tokens.append(("alt",))
            i += 1
        elif ch == "\\":
            if i + 1 >= len(pattern):
                raise ValueError("dangling backslash")
            tokens.append(("lit", pattern[i + 1]))
            i += 2
        else:
            tokens.append(("lit", ch))
            i += 1
    return tokens


def match_seq(tokens, text, pos):
    """Match tokens against text starting at pos. Returns next pos or None.
    Greedy `*` never backtracks: it consumes as far as possible then moves on,
    so `a*a` fails on `aaa`."""
    i = pos
    ti = 0
    while ti < len(tokens):
        tok = tokens[ti]
        if tok[0] == "star":
            # BUG: no backtracking. Consume greedily the preceding token.
            # We assume star always follows a literal token (preceding ti-1).
            ti += 1
            continue
        if tok[0] == "alt":
            # BUG: treat alternation as a no-op separator (ignores grouping)
            ti += 1
            continue
        if tok[0] == "lit":
            if i < len(text) and text[i] == tok[1]:
                i += 1
            else:
                return None
            ti += 1
        elif tok[0] == "class":
            if i < len(text) and ((text[i] in tok[1]) != tok[2]):
                i += 1
            else:
                return None
            ti += 1
        elif tok[0] == "group":
            r = match_seq(tok[1], text, i)
            if r is None:
                return None
            i = r
            ti += 1
    return i


def matches(pattern, text, full):
    tokens = parse(pattern)
    if full:
        r = match_seq(tokens, text, 0)
        return r == len(text)
    for start in range(len(text) + 1):
        r = match_seq(tokens, text, start)
        if r is not None:
            return True
    return False


def main():
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(Path(sys.argv[1]).read_text())
        result = matches(data["pattern"], data["text"], data["full"])
        Path(sys.argv[2]).write_text(json.dumps({"match": result}) + "\n")
    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
