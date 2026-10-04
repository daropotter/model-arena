#!/usr/bin/env python3
"""Evaluate a small regex with proper precedence and backtracking."""

import json
import sys
from functools import cache
from pathlib import Path


# --- parser ---

class Parser:
    def __init__(self, pattern):
        self.pat = pattern
        self.pos = 0

    def peek(self):
        return self.pat[self.pos] if self.pos < len(self.pat) else None

    def advance(self):
        self.pos += 1

    def parse(self):
        alt = self.parse_alternation()
        if self.pos != len(self.pat):
            raise ValueError("unexpected trailing characters")
        return alt

    def parse_alternation(self):
        seqs = [self.parse_sequence()]
        while self.peek() == "|":
            self.advance()
            seqs.append(self.parse_sequence())
        return ("alt", tuple(seqs))

    def parse_sequence(self):
        items = []
        while self.pos < len(self.pat) and self.peek() not in ("|", ")"):
            items.append(self.parse_item())
        return ("seq", tuple(items))

    def parse_item(self):
        ch = self.peek()
        if ch == "(":
            self.advance()
            inner = self.parse_alternation()
            if self.peek() != ")":
                raise ValueError("unbalanced parens")
            self.advance()
            atom = ("group", inner)
        elif ch == "[":
            atom = self.parse_class()
        elif ch == "*":
            raise ValueError("quantifier with nothing to repeat")
        elif ch == "\\":
            self.advance()
            if self.pos >= len(self.pat):
                raise ValueError("dangling backslash")
            atom = ("lit", self.pat[self.pos])
            self.advance()
        else:
            atom = ("lit", ch)
            self.advance()

        if self.peek() == "*":
            self.advance()
            return ("star", atom)
        return atom

    def parse_class(self):
        self.advance()  # consume '['
        neg = False
        if self.peek() == "^":
            neg = True
            self.advance()
        elements = []
        while self.pos < len(self.pat) and self.peek() != "]":
            ch = self.pat[self.pos]
            if ch == "\\":
                self.advance()
                if self.pos >= len(self.pat):
                    raise ValueError("unterminated class")
                elements.append((self.pat[self.pos], True))
                self.advance()
                continue
            elements.append((ch, False))
            self.advance()
        if self.pos >= len(self.pat):
            raise ValueError("unterminated class")
        if not elements:
            raise ValueError("empty class")

        charset = set()
        index = 0
        while index < len(elements):
            if (index + 2 < len(elements)
                    and elements[index + 1] == ("-", False)):
                lo = elements[index][0]
                hi = elements[index + 2][0]
                if lo > hi:
                    raise ValueError("bad range")
                for c in range(ord(lo), ord(hi) + 1):
                    charset.add(chr(c))
                index += 3
                continue
            charset.add(elements[index][0])
            index += 1
        self.advance()  # consume ']'
        return ("class", frozenset(charset), neg)


# --- matcher ---

def end_positions(root, text, start):
    """Yield every reachable end, in left-to-right/greedy preference order."""
    @cache
    def ends(node, pos):
        kind = node[0]
        if kind == "lit":
            result = (pos + 1,) if pos < len(text) and text[pos] == node[1] else ()
        elif kind == "class":
            matches = pos < len(text) and ((text[pos] in node[1]) != node[2])
            result = (pos + 1,) if matches else ()
        elif kind == "group":
            result = ends(node[1], pos)
        elif kind == "alt":
            result = tuple(end for branch in node[1] for end in ends(branch, pos))
        elif kind == "seq":
            positions = (pos,)
            for item in node[1]:
                positions = tuple(end for current in positions
                                  for end in ends(item, current))
                if not positions:
                    break
            result = positions
        elif kind == "star":
            # Recurse before yielding zero repetitions, making the order greedy.
            result = tuple(end for nxt in ends(node[1], pos) if nxt > pos
                           for end in ends(node, nxt)) + (pos,)
        else:
            raise ValueError("bad node")
        return tuple(dict.fromkeys(result))

    return ends(root, start)


def matches(pattern, text, full):
    root = Parser(pattern).parse()
    if full:
        return len(text) in end_positions(root, text, 0)
    for start in range(len(text) + 1):
        if end_positions(root, text, start):
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
