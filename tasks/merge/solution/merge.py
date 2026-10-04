#!/usr/bin/env python3
"""Three-way text merge using base-coordinate edits. See SPEC.md."""

import json
import sys
from pathlib import Path


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
    """Return canonical (base_start, base_end, replacement) edits."""
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


def merge(base, ours, theirs):
    tagged = [(edit, "ours") for edit in _edits(base, ours)]
    tagged += [(edit, "theirs") for edit in _edits(base, theirs)]

    # Connected overlapping edits form one jointly resolved region.
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


def main():
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(Path(sys.argv[1]).read_text())
        base = data["base"]
        ours = data["ours"]
        theirs = data["theirs"]
        if not all(isinstance(x, list) and
                   all(isinstance(s, str) for s in x)
                   for x in (base, ours, theirs)):
            raise ValueError("not lists of strings")
        result = merge(base, ours, theirs)
        Path(sys.argv[2]).write_text(json.dumps(result) + "\n")
    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
