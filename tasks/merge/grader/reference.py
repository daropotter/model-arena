#!/usr/bin/env python3
"""Reference three-way merge. Used only by the hidden grader."""


def _lcs(a, b):
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    matches = []
    i = j = 0
    while i < m and j < n:
        if a[i] == b[j]:
            matches.append((i, j))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return matches


def _edits(base, side):
    matches = _lcs(base, side)
    edits = []
    pb = ps = 0
    for bi, si in matches:
        if bi > pb or si > ps:
            edits.append((pb, bi, side[ps:si]))
        pb = bi + 1
        ps = si + 1
    if pb < len(base) or ps < len(side):
        edits.append((pb, len(base), side[ps:]))
    return edits


def _overlap(left, right):
    ls, le, _ = left
    rs, re, _ = right
    if ls == le and rs == re:
        return ls == rs
    if ls == le:
        return rs < ls < re
    if rs == re:
        return ls < rs < le
    return max(ls, rs) < min(le, re)


def _apply(base, start, end, edits):
    result = []
    cursor = start
    for edit_start, edit_end, replacement in sorted(edits):
        result.extend(base[cursor:edit_start])
        result.extend(replacement)
        cursor = edit_end
    result.extend(base[cursor:end])
    return result


def merge_reference(base, ours, theirs):
    tagged = [(edit, "ours") for edit in _edits(base, ours)]
    tagged += [(edit, "theirs") for edit in _edits(base, theirs)]
    parent = list(range(len(tagged)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left, right):
        left = find(left)
        right = find(right)
        if left != right:
            parent[right] = left

    for i, (left, left_side) in enumerate(tagged):
        for j in range(i + 1, len(tagged)):
            right, right_side = tagged[j]
            if left_side != right_side and _overlap(left, right):
                union(i, j)

    components = {}
    for index, tagged_edit in enumerate(tagged):
        components.setdefault(find(index), []).append(tagged_edit)
    regions = list(components.values())
    regions.sort(key=lambda region: (
        min(edit[0] for edit, _ in region),
        0 if all(edit[0] == edit[1] for edit, _ in region) else 1,
        max(edit[1] for edit, _ in region),
    ))

    out = []
    cursor = 0
    for region in regions:
        start = min(edit[0] for edit, _ in region)
        end = max(edit[1] for edit, _ in region)
        out.extend(base[cursor:start])
        ours_edits = [edit for edit, side in region if side == "ours"]
        theirs_edits = [edit for edit, side in region if side == "theirs"]
        base_lines = base[start:end]
        ours_lines = (_apply(base, start, end, ours_edits)
                      if ours_edits else base_lines)
        theirs_lines = (_apply(base, start, end, theirs_edits)
                        if theirs_edits else base_lines)
        if ours_lines == base_lines:
            out.extend(theirs_lines)
        elif theirs_lines == base_lines or ours_lines == theirs_lines:
            out.extend(ours_lines)
        else:
            out.append("<<<<<<<")
            out.extend(ours_lines)
            out.append("=======")
            out.extend(theirs_lines)
            out.append(">>>>>>>")
        cursor = max(cursor, end)
    out.extend(base[cursor:])
    return out


# (name, base, ours, theirs)
CASES = [
    ("no_change", ["a", "b", "c"], ["a", "b", "c"], ["a", "b", "c"]),
    ("ours_only", ["a", "b", "c"], ["a", "X", "c"], ["a", "b", "c"]),
    ("theirs_only", ["a", "b", "c"], ["a", "b", "c"], ["a", "Y", "c"]),
    ("conflict_single", ["a", "b", "c"], ["a", "X", "c"], ["a", "Y", "c"]),
    ("conflict_two_vs_one",
     ["x", "a", "b", "y"], ["x", "1", "2", "y"], ["x", "9", "y"]),
    ("theirs_append", ["k", "l", "m"], ["k", "l", "m"], ["k", "l", "m", "n"]),
    ("ours_append", ["k", "l", "m"], ["k", "l", "m", "n"], ["k", "l", "m"]),
    ("same_change_both", ["a", "b"], ["a", "Z"], ["a", "Z"]),
    ("disjoint_regions",
     ["a", "b", "c", "d"], ["a", "B", "c", "d"], ["a", "b", "C", "d"]),
    ("empty_base_both_add",
     [], ["a"], ["a"]),
    ("empty_base_conflict",
     [], ["a"], ["b"]),
    ("repeated_lines", ["x", "x"], ["x", "x", "x"], ["x", "x"]),
    ("adjacent_disjoint_edits",
     ["a", "b"], ["A", "b"], ["a", "B"]),
    ("delete_vs_disjoint_edit",
     ["a", "b", "c"], ["a", "c"], ["a", "b", "C"]),
    ("insert_vs_disjoint_edit",
     ["a", "b"], ["a", "x", "b"], ["A", "b"]),
    ("same_insertion", ["a"], ["x", "a"], ["x", "a"]),
    ("different_insertion", ["a"], ["x", "a"], ["y", "a"]),
    ("delete_vs_edit_conflict",
     ["a", "b", "c"], ["a", "c"], ["a", "B", "c"]),
    ("repeated_lines_both_insert",
     ["x", "x"], ["x", "x", "A"], ["x", "x", "B"]),
]


# Malformed inputs must error; here represented as (name, payload) with a
# non-list or non-string member.
ERRORS = [
    ("missing_base", {"ours": ["a"], "theirs": ["a"]}),
    ("non_list", {"base": "notalist", "ours": ["a"], "theirs": ["a"]}),
    ("non_string_member",
     {"base": [1], "ours": [1], "theirs": [1]}),
]
