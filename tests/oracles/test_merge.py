"""Oracle tests for the merge task.

These tests never import the shipped starter/solution; they exercise the
hidden grader's reference directly against hand-computed expectations.
"""

import importlib.util
import random
import sys
import unittest
from pathlib import Path

from tests.support import ROOT

GRADER = ROOT / "tasks" / "merge" / "grader"


def _load_reference():
    if str(GRADER) not in sys.path:
        sys.path.insert(0, str(GRADER))
    spec = importlib.util.spec_from_file_location(
        "merge_grader_reference", GRADER / "reference.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REF = _load_reference()
merge = REF.merge_reference

START, MID, END = "<<<<<<<", "=======", ">>>>>>>"


def _assert_well_formed_markers(test, lines):
    state = "outside"
    for line in lines:
        if state == "outside":
            if line == START:
                state = "ours"
            else:
                test.assertNotEqual(line, MID)
                test.assertNotEqual(line, END)
        elif state == "ours":
            if line == MID:
                state = "theirs"
            else:
                test.assertNotEqual(line, START)
                test.assertNotEqual(line, END)
        else:
            if line == END:
                state = "outside"
            else:
                test.assertNotEqual(line, START)
                test.assertNotEqual(line, MID)
    test.assertEqual(state, "outside")


def _swap_conflict_halves(lines):
    out = []
    index = 0
    while index < len(lines):
        if lines[index] == START:
            mid = lines.index(MID, index + 1)
            end = lines.index(END, mid + 1)
            out.append(START)
            out.extend(lines[mid + 1:end])
            out.append(MID)
            out.extend(lines[index + 1:mid])
            out.append(END)
            index = end + 1
        else:
            out.append(lines[index])
            index += 1
    return out


def _mutate(base, rng):
    lines = list(base)
    for _ in range(rng.randrange(4)):
        pos = rng.randrange(len(lines) + 1)
        op = rng.choice(["insert", "delete", "replace"])
        if op == "insert":
            lines.insert(pos, rng.choice(["A", "B", "C"]))
        elif op == "delete" and lines:
            del lines[min(pos, len(lines) - 1)]
        elif op == "replace" and lines:
            lines[min(pos, len(lines) - 1)] = rng.choice(["X", "Y", "Z"])
    return lines


def _corpus():
    cases = [
        (["a", "b", "c"], ["a", "X", "c"], ["a", "Y", "c"]),
        (["x", "a", "b", "y"], ["x", "1", "2", "y"], ["x", "9", "y"]),
        (["a", "b", "c"], ["a", "c"], ["a", "B", "c"]),
        (["a"], ["a", "x"], ["a", "y"]),
        ([], ["a"], ["b"]),
        (["x", "x"], ["x", "x", "A"], ["x", "x", "B"]),
        (["k", "l", "m"], ["k", "l", "m", "n"], ["k", "l", "m", "o"]),
        (["a", "b", "c"], ["a", "X", "b", "c"], ["a", "b", "C"]),
        (["a", "b", "c"], ["a", "c"], ["a", "b", "C"]),
        (["a", "b"], ["A", "b"], ["a", "B"]),
    ]
    rng = random.Random(20260901)
    alphabet = ["a", "b", "c"]
    for _ in range(150):
        base = [rng.choice(alphabet) for _ in range(rng.randrange(7))]
        cases.append((base, _mutate(base, rng), _mutate(base, rng)))
    return cases


class HandComputedTests(unittest.TestCase):
    def assert_merge(self, base, ours, theirs, want):
        self.assertEqual(merge(base, ours, theirs), want)

    def test_insert_before_disjoint_replacement(self):
        self.assert_merge(["a", "b", "c"], ["a", "X", "b", "c"],
                          ["a", "b", "C"], ["a", "X", "b", "C"])

    def test_disjoint_edits(self):
        self.assert_merge(["a", "b", "c", "d"], ["a", "B", "c", "d"],
                          ["a", "b", "C", "d"], ["a", "B", "C", "d"])

    def test_adjacent_edits(self):
        self.assert_merge(["a", "b"], ["A", "b"], ["a", "B"], ["A", "B"])

    def test_one_sided_ours(self):
        self.assert_merge(["a", "b", "c"], ["a", "X", "c"],
                          ["a", "b", "c"], ["a", "X", "c"])

    def test_one_sided_theirs(self):
        self.assert_merge(["a", "b", "c"], ["a", "b", "c"],
                          ["a", "Y", "c"], ["a", "Y", "c"])

    def test_same_change_both_sides(self):
        self.assert_merge(["a", "b"], ["a", "Z"], ["a", "Z"], ["a", "Z"])

    def test_ours_append(self):
        self.assert_merge(["k", "l", "m"], ["k", "l", "m", "n"],
                          ["k", "l", "m"], ["k", "l", "m", "n"])

    def test_theirs_append(self):
        self.assert_merge(["k", "l", "m"], ["k", "l", "m"],
                          ["k", "l", "m", "n"], ["k", "l", "m", "n"])

    def test_both_append_differently_conflicts(self):
        self.assert_merge(["a"], ["a", "x"], ["a", "y"],
                          ["a", START, "x", MID, "y", END])

    def test_deletion_one_sided(self):
        self.assert_merge(["a", "b", "c"], ["a", "c"],
                          ["a", "b", "c"], ["a", "c"])

    def test_delete_vs_disjoint_replacement(self):
        self.assert_merge(["a", "b", "c"], ["a", "c"],
                          ["a", "b", "C"], ["a", "C"])

    def test_delete_vs_replace_same_line_conflicts(self):
        self.assert_merge(["a", "b", "c"], ["a", "c"], ["a", "B", "c"],
                          ["a", START, MID, "B", END, "c"])

    def test_empty_base_agreement(self):
        self.assert_merge([], ["a"], ["a"], ["a"])

    def test_empty_base_disagreement_conflicts(self):
        self.assert_merge([], ["a"], ["b"], [START, "a", MID, "b", END])

    def test_empty_base_one_sided(self):
        self.assert_merge([], ["a"], [], ["a"])

    def test_repeated_lines_delete_one(self):
        self.assert_merge(["x", "x"], ["x"], ["x"], ["x"])

    def test_repeated_lines_append_one_sided(self):
        self.assert_merge(["x", "x"], ["x", "x", "x"], ["x", "x"],
                          ["x", "x", "x"])

    def test_repeated_lines_both_append_conflicts(self):
        self.assert_merge(["x", "x"], ["x", "x", "A"], ["x", "x", "B"],
                          ["x", "x", START, "A", MID, "B", END])

    def test_insertion_at_end_boundary_of_edit(self):
        self.assert_merge(["a", "b"], ["a", "x", "b"], ["A", "b"],
                          ["A", "x", "b"])

    def test_insertion_at_start_boundary_of_edit(self):
        self.assert_merge(["a", "b"], ["x", "a", "b"], ["A", "b"],
                          ["x", "A", "b"])

    def test_two_vs_one_conflict(self):
        self.assert_merge(["x", "a", "b", "y"], ["x", "1", "2", "y"],
                          ["x", "9", "y"],
                          ["x", START, "1", "2", MID, "9", END, "y"])

    def test_no_change(self):
        self.assert_merge(["a", "b", "c"], ["a", "b", "c"],
                          ["a", "b", "c"], ["a", "b", "c"])

    def test_single_line_conflict_block(self):
        self.assert_merge(["a", "b", "c"], ["a", "X", "c"], ["a", "Y", "c"],
                          ["a", START, "X", MID, "Y", END, "c"])


class PropertyTests(unittest.TestCase):
    def test_unmodified_side_passthrough(self):
        for base, ours, theirs in _corpus():
            with self.subTest(base=base, ours=ours, theirs=theirs):
                self.assertEqual(merge(base, base, theirs), theirs)
                self.assertEqual(merge(base, ours, base), ours)

    def test_identical_sides(self):
        for base, ours, _ in _corpus():
            with self.subTest(base=base, sides=ours):
                self.assertEqual(merge(base, ours, ours), ours)

    def test_swap_sides_swaps_conflict_halves(self):
        for base, ours, theirs in _corpus():
            with self.subTest(base=base, ours=ours, theirs=theirs):
                forward = merge(base, ours, theirs)
                backward = merge(base, theirs, ours)
                self.assertEqual(_swap_conflict_halves(forward), backward)

    def test_marker_structure_and_absence_without_disagreement(self):
        for base, ours, theirs in _corpus():
            with self.subTest(base=base, ours=ours, theirs=theirs):
                out = merge(base, ours, theirs)
                _assert_well_formed_markers(self, out)
                if ours == theirs or ours == base or theirs == base:
                    for marker in (START, MID, END):
                        self.assertNotIn(marker, out)

    def test_conflict_requires_both_sides_to_differ(self):
        base = ["a", "b", "c"]
        out = merge(base, ["a", "X", "c"], ["a", "Y", "c"])
        self.assertEqual(out.count(START), 1)
        self.assertEqual(out.count(MID), 1)
        self.assertEqual(out.count(END), 1)
        self.assertEqual(out, ["a", START, "X", MID, "Y", END, "c"])


if __name__ == "__main__":
    unittest.main()
