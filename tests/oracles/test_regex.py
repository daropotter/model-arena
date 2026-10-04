"""Independent oracle tests for the regex task (T1).

The implementation under test is the hidden reference.  This module does NOT
import the shipped starter or solution.  It builds its own Thompson NFA
directly from structurally generated ASTs and compares the reference's answer
with NFA acceptance for every generated (pattern, text, full) triple.  The NFA
is compiled from the AST -- it never parses a pattern string -- so a shared
bug in the reference parser/backtracker cannot hide behind the oracle.
"""

import importlib.util
import itertools
import random
import sys
import unittest

from tests.support import ROOT

_REGEX_GRADER = ROOT / "tasks" / "regex" / "grader"
sys.path.insert(0, str(_REGEX_GRADER))

_spec = importlib.util.spec_from_file_location(
    "_regex_reference_under_test", _REGEX_GRADER / "reference.py")
_reference = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _reference
_spec.loader.exec_module(_reference)

matches_reference = _reference.matches_reference
CASES = _reference.CASES
ERRORS = _reference.ERRORS


ALPHABET = ("a", "b")
SPECIALS = set("()*|[]\\")


# --- AST ------------------------------------------------------------------


def lit(ch):
    return ("lit", ch)


def cls(chars, negated=False):
    return ("cls", frozenset(chars), negated)


def cat(*children):
    return ("cat", tuple(children))


def alt(*children):
    return ("alt", tuple(children))


def star(child):
    return ("star", child)


def group(child):
    return ("group", child)


def node_count(node):
    kind = node[0]
    if kind in ("lit", "cls"):
        return 1
    if kind in ("star", "group"):
        return 1 + node_count(node[1])
    return 1 + sum(node_count(child) for child in node[1])


# --- Thompson NFA built from the AST --------------------------------------


class ThompsonNFA:
    def __init__(self, root):
        self.eps = []
        self.trans = []
        self.start, self.accept = self._build(root)

    def _new_state(self):
        self.eps.append([])
        self.trans.append([])
        return len(self.eps) - 1

    def _build(self, node):
        kind = node[0]
        if kind == "lit":
            start = self._new_state()
            accept = self._new_state()
            ch = node[1]
            self.trans[start].append((lambda c, ch=ch: c == ch, accept))
            return start, accept
        if kind == "cls":
            start = self._new_state()
            accept = self._new_state()
            chars = node[1]
            negated = node[2]
            self.trans[start].append(
                (lambda c, chars=chars, negated=negated:
                 (c in chars) != negated, accept))
            return start, accept
        if kind == "group":
            return self._build(node[1])
        if kind == "cat":
            start = self._new_state()
            state = start
            for child in node[1]:
                child_start, child_accept = self._build(child)
                self.eps[state].append(child_start)
                state = child_accept
            return start, state
        if kind == "alt":
            start = self._new_state()
            accept = self._new_state()
            for child in node[1]:
                child_start, child_accept = self._build(child)
                self.eps[start].append(child_start)
                self.eps[child_accept].append(accept)
            return start, accept
        if kind == "star":
            start = self._new_state()
            accept = self._new_state()
            child_start, child_accept = self._build(node[1])
            self.eps[start].append(child_start)
            self.eps[start].append(accept)
            self.eps[child_accept].append(child_start)
            self.eps[child_accept].append(accept)
            return start, accept
        raise AssertionError(f"unknown AST node {kind!r}")

    def _closure(self, states):
        stack = list(states)
        seen = set(states)
        while stack:
            state = stack.pop()
            for target in self.eps[state]:
                if target not in seen:
                    seen.add(target)
                    stack.append(target)
        return seen

    def _step(self, states, ch):
        next_states = set()
        for state in states:
            for predicate, target in self.trans[state]:
                if predicate(ch):
                    next_states.add(target)
        return self._closure(next_states)

    def matches_full(self, text):
        states = self._closure({self.start})
        for ch in text:
            states = self._step(states, ch)
            if not states:
                return False
        return self.accept in states

    def matches_search(self, text):
        for start in range(len(text) + 1):
            states = self._closure({self.start})
            if self.accept in states:
                return True
            for ch in text[start:]:
                states = self._step(states, ch)
                if not states:
                    break
                if self.accept in states:
                    return True
        return False

    def matches(self, text, full):
        return self.matches_full(text) if full else self.matches_search(text)


# --- structural generation + serialization --------------------------------


def random_ast(rng, budget):
    options = ["lit", "lit", "cls", "cls"]
    if budget >= 2:
        options += ["star", "group"]
    if budget >= 3:
        options += ["cat", "alt"]
    kind = rng.choice(options)
    if kind == "lit":
        return lit(rng.choice(ALPHABET))
    if kind == "cls":
        size = rng.randint(1, len(ALPHABET))
        return cls(rng.sample(ALPHABET, size), rng.random() < 0.5)
    if kind == "star":
        return star(random_ast(rng, budget - 1))
    if kind == "group":
        return group(random_ast(rng, budget - 1))
    left_budget = rng.randint(1, budget - 2)
    right_budget = budget - 1 - left_budget
    left = random_ast(rng, left_budget)
    right = random_ast(rng, right_budget)
    return cat(left, right) if kind == "cat" else alt(left, right)


def _escape(ch):
    return "\\" + ch if ch in SPECIALS else ch


def serialize(node):
    kind = node[0]
    if kind == "lit":
        return _escape(node[1])
    if kind == "cls":
        body = "".join(_escape(ch) for ch in sorted(node[1]))
        return "[" + ("^" if node[2] else "") + body + "]"
    if kind == "group":
        return "(" + serialize(node[1]) + ")"
    if kind == "star":
        child = node[1]
        text = serialize(child)
        if child[0] in ("cat", "alt", "star"):
            text = "(" + text + ")"
        return text + "*"
    if kind == "cat":
        return "".join(
            "(" + serialize(child) + ")" if child[0] == "alt"
            else serialize(child)
            for child in node[1])
    if kind == "alt":
        return "|".join(serialize(child) for child in node[1])
    raise AssertionError(f"unknown AST node {kind!r}")


def generated_patterns(limit=200, max_nodes=6, seed=20261001):
    rng = random.Random(seed)
    patterns = []
    seen = set()
    attempts = 0
    while len(patterns) < limit and attempts < limit * 100:
        attempts += 1
        ast = random_ast(rng, max_nodes)
        assert node_count(ast) <= max_nodes, "generator exceeded node budget"
        pattern = serialize(ast)
        if pattern in seen:
            continue
        seen.add(pattern)
        patterns.append((ast, pattern))
    return patterns


TEXTS = [""] + ["".join(chars)
                for length in range(1, 5)
                for chars in itertools.product(ALPHABET, repeat=length)]


class GeneratedNFAOracleTests(unittest.TestCase):
    comparisons = 0

    def test_generated_patterns_match_thompson_nfa(self):
        failures = []
        comparisons = 0
        for ast, pattern in generated_patterns():
            nfa = ThompsonNFA(ast)
            for text in TEXTS:
                for full in (True, False):
                    expected = nfa.matches(text, full)
                    got = matches_reference(pattern, text, full)
                    comparisons += 1
                    if got != expected:
                        failures.append((pattern, text, full, expected, got))
        GeneratedNFAOracleTests.comparisons = comparisons
        self.assertGreaterEqual(
            comparisons, 5000,
            "generated corpus unexpectedly small -- oracle would be weak")
        if failures:
            failures.sort(key=lambda item: (len(item[1]), len(item[0]), item[2]))
            pattern, text, full, expected, got = failures[0]
            self.fail(
                f"reference disagrees with the independent Thompson NFA on "
                f"{len(failures)} of {comparisons} triple(s); minimal failing "
                f"triple: pattern={pattern!r} text={text!r} full={full} "
                f"(NFA={expected}, reference={got})")


class SpecificationCaseTests(unittest.TestCase):
    """Hand-checked patterns whose answer is known independently."""

    def setUp(self):
        a, b = lit("a"), lit("b")
        ab = cat(a, b)
        self.cases = [
            ("a|ab", "ab", True, True, alt(a, ab)),
            ("(a|ab)c", "abc", True, True,
             cat(group(alt(a, ab)), lit("c"))),
            ("a*a", "aa", True, True, cat(star(a), a)),
            ("a*a", "aaa", True, True, cat(star(a), a)),
            ("(aa|a)*aa", "aaaa", True, True,
             cat(star(alt(cat(a, a), a)), cat(a, a))),
            ("(a|ab)*c", "ababc", True, True,
             cat(star(group(alt(a, ab))), lit("c"))),
            ("[^a]", "b", True, True, cls("a", True)),
            ("[^a]", "a", True, False, cls("a", True)),
            ("[^ab]", "a", False, False, cls("ab", True)),
            ("[^ab]", "b", False, False, cls("ab", True)),
            ("[\\]]", "]", True, True, cls("]")),
            ("[\\[]", "[", True, True, cls("[")),
            ("[\\-]", "-", True, True, cls("-")),
            ("[-a]", "-", True, True, cls("-a")),
            ("[a-]", "-", True, True, cls("-a")),
            ("[a-c]", "b", True, True, cls("abc")),
            ("a*", "bbb", False, True, star(a)),
            ("a*", "", True, True, star(a)),
            ("a|", "b", False, True, alt(cat(a), cat())),
            ("a|", "b", True, False, alt(cat(a), cat())),
        ]

    def test_hand_written_specification_cases(self):
        for pattern, text, full, expected, ast in self.cases:
            message = (f"pattern={pattern!r} text={text!r} full={full} "
                       f"(expected {expected})")
            got = matches_reference(pattern, text, full)
            self.assertEqual(got, expected, message)
            nfa = ThompsonNFA(ast)
            self.assertEqual(
                nfa.matches(text, full), expected,
                "independent NFA disagrees with the spec: " + message)


class MalformedPatternTests(unittest.TestCase):
    EXTRA_ERRORS = ["a**", "[z-a]", "(a|b))", "[^", "a|*", "(*"]

    def _assert_raises(self, pattern):
        with self.assertRaises(ValueError,
                               msg=f"pattern={pattern!r} should be rejected"):
            matches_reference(pattern, "", True)

    def test_reference_error_corpus_raises_value_error(self):
        for name, pattern in ERRORS:
            with self.subTest(case=name, pattern=pattern):
                self._assert_raises(pattern)

    def test_additional_malformed_patterns_raise_value_error(self):
        for pattern in self.EXTRA_ERRORS:
            with self.subTest(pattern=pattern):
                self._assert_raises(pattern)


class ReferenceCaseCorpusTests(unittest.TestCase):
    def test_reference_cases_return_booleans(self):
        for name, payload in CASES:
            with self.subTest(case=name):
                got = matches_reference(
                    payload["pattern"], payload["text"], payload["full"])
                self.assertIsInstance(got, bool)


if __name__ == "__main__":
    unittest.main()
