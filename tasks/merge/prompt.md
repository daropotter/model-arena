You are working in /workspace.

`merge.py` performs a three-way text merge. It has bugs: it diffs only
`ours` against `theirs` (ignoring `base`), so it produces spurious conflicts
when one side is unchanged, and it emits conflicts one line at a time instead
of grouping a contiguous changed region into a single conflict block.

Read SPEC.md — it defines the deterministic base-coordinate edit alignment,
including the repeated-line tie rule and exact conflict block format.

The visible tests cover only the no-change and one-sided-change cases. Hidden
tests exercise insertions, deletions, disjoint edits, repeated lines, and real
conflicts (including multi-line blocks).

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix:

    python3 merge.py in.json out.json
    python3 -m pytest tests/ -q
