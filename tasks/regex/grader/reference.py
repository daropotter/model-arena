#!/usr/bin/env python3
"""Reference regex matcher. Used only by the hidden grader."""

from functools import cache


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
            raise ValueError("trailing chars")
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
        self.advance()
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
        self.advance()
        return ("class", frozenset(charset), neg)


def end_positions(root, text, start):
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
            result = tuple(end for nxt in ends(node[1], pos) if nxt > pos
                           for end in ends(node, nxt)) + (pos,)
        else:
            raise ValueError("bad node")
        return tuple(dict.fromkeys(result))

    return ends(root, start)


def matches_reference(pattern, text, full):
    root = Parser(pattern).parse()
    if full:
        return len(text) in end_positions(root, text, 0)
    for start in range(len(text) + 1):
        if end_positions(root, text, start):
            return True
    return False


CASES = [
    ("lit_full", {"pattern": "abc", "text": "abc", "full": True}),
    ("lit_sub", {"pattern": "abc", "text": "xxabcxx", "full": False}),
    ("lit_full_fail", {"pattern": "abc", "text": "ab", "full": True}),
    ("star_backtrack", {"pattern": "a*a", "text": "aaa", "full": True}),
    ("star_backtrack_short", {"pattern": "a*a", "text": "aa", "full": True}),
    ("star_then_lit", {"pattern": "a*b", "text": "aaab", "full": True}),
    ("star_zero", {"pattern": "a*", "text": "", "full": True}),
    ("star_sub_empty", {"pattern": "a*", "text": "bbb", "full": False}),
    ("group_star", {"pattern": "(ab)*", "text": "abab", "full": True}),
    ("group_star_partial", {"pattern": "(ab)*", "text": "ab", "full": True}),
    ("alt_basic", {"pattern": "ab|cd", "text": "cd", "full": True}),
    ("alt_full_second", {"pattern": "a|ab", "text": "ab", "full": True}),
    ("alt_full_first", {"pattern": "ab|a", "text": "ab", "full": True}),
    ("alt_precedence", {"pattern": "ab|cd", "text": "acd", "full": False}),
    ("class_range", {"pattern": "[a-c]", "text": "b", "full": True}),
    ("class_neg", {"pattern": "[^0-9]", "text": "a", "full": True}),
    ("class_neg_fail", {"pattern": "[^0-9]", "text": "5", "full": True}),
    ("class_escape", {"pattern": "[\\]]", "text": "]", "full": True}),
    ("class_escaped_hyphen",
     {"pattern": "[a\\-c]", "text": "-", "full": True}),
    ("class_escaped_range_endpoint",
     {"pattern": "[\\--0]", "text": ".", "full": True}),
    ("star_class", {"pattern": "[ab]*c", "text": "aabbac", "full": True}),
    ("nested_group", {"pattern": "(a(b)*c)", "text": "abbc", "full": True}),
    ("greedy_backtrack_deep", {"pattern": "a*a*a", "text": "aaa", "full": True}),
    ("group_alt_backtrack", {"pattern": "(a|ab)c", "text": "abc", "full": True}),
    ("outer_alt_continuation", {"pattern": "(a|ab)b", "text": "abb", "full": True}),
    ("star_group_alt_backtrack",
     {"pattern": "(a|ab)*c", "text": "ababc", "full": True}),
    ("star_group_variable_width",
     {"pattern": "(aa|a)*aa", "text": "aaaa", "full": True}),
    ("nested_alt_backtrack",
     {"pattern": "((a|ab)|abc)d", "text": "abcd", "full": True}),
]

ERRORS = [
    ("unbalanced_open", "("),
    ("unbalanced_close", "a)"),
    ("unterminated_class", "[abc"),
    ("leading_star", "*a"),
    ("dangling_backslash", "a\\"),
    ("empty_class", "[]"),
    ("empty_negated_class", "[^]"),
]
