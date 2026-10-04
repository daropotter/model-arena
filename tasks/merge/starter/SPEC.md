# merge spec

This document is the authoritative contract. Where the implementation and
this document disagree, this document wins.

## CLI

```
python3 merge.py <in.json> <out.json>
```

`in.json` is `{"base": [...], "ours": [...], "theirs": [...]}` where each is a
list of lines (strings, no trailing newline). Produce a three-way merge and
write the result as a list of lines to `out.json`, followed by a newline.

Exit 0 on success. On malformed input, print exactly `error` to stderr,
exit 1, and do not create the output file.

## Three-way merge

A three-way merge combines two line edit scripts (`ours`, `theirs`), each made
relative to the common ancestor `base`. Replacements, insertions, and deletions
are tracked by positions in `base`; lines are not paired merely because they
have the same numeric index in the two changed files.

## Conflict representation

A conflict is emitted with these marker lines:

```
<<<<<<<
<ours line>
=======
<theirs line>
>>>>>>>
```

All lines produced by each side for the conflicting base region appear between
the markers. A deletion is represented by no lines on that side.

## Resolution algorithm

The following deterministic algorithm is the exact contract:

1. Diff `base` against each side separately using a longest common subsequence
   (LCS). Reconstruct from the beginning: match equal current lines; otherwise
   advance whichever choice leaves the longer remaining LCS; on a tie, advance
   the `base` position. Every gap between matches is one edit replacing the
   half-open base range `[start, end)` with zero or more side lines. This tie
   rule makes repeated-line inputs unambiguous.
2. Edits from opposite sides overlap when their non-empty base ranges
   intersect. Two insertions overlap when they use the same base position. An
   insertion overlaps a non-empty edit only when its position is strictly
   inside that edit; an insertion at an edit boundary is independent. Merge
   transitively overlapping edits into one region.
3. Apply independent regions in base order. Insertions at the start boundary
   of another edit come first; insertions at its end boundary come after it.
   Thus adjacent and boundary edits combine without a conflict.
4. For each region, construct the lines that `base`, `ours`, and `theirs`
   produce there. If one side equals `base`, take the other side. If both sides
   are equal, take that value. Otherwise emit one conflict block containing
   the complete output of each side for that region.

## Reference examples

base `["a","b","c"]`, ours `["a","X","c"]`, theirs `["a","b","c"]`
→ `["a","X","c"]` (only ours changed).

base `["a","b","c"]`, ours `["a","b","c"]`, theirs `["a","Y","c"]`
→ `["a","Y","c"]` (only theirs changed).

base `["a","b","c"]`, ours `["a","X","c"]`, theirs `["a","Y","c"]`
→ `["a","<<<<<<<","X","=======","Y",">>>>>>>","c"]` (conflict on the middle
line).

base `["a","b","c"]`, ours `["a","b","c"]`, theirs `["a","b","c"]`
→ `["a","b","c"]` (no change).

base `["x","a","b","y"]`, ours `["x","1","2","y"]`, theirs `["x","9","y"]`
→ `["x","<<<<<<<","1","2","=======","9",">>>>>>>","y"]` (a two-vs-one conflict
block, spanning only the disagreeing region between the agreeing `x` and `y`).

base `["k","l","m"]`, ours `["k","l","m"]`, theirs `["k","l","m","n"]`
→ `["k","l","m","n"]` (theirs appended a line).

base `["a","b"]`, ours `["A","b"]`, theirs `["a","B"]`
→ `["A","B"]` (adjacent edits affect disjoint base ranges).

base `["a","b","c"]`, ours `["a","c"]`, theirs `["a","b","C"]`
→ `["a","C"]` (a deletion and a disjoint replacement both apply).

## Errors

`base`, `ours`, or `theirs` missing or not a list of strings is an error:
print `error` to stderr and exit 1.
