You are working in /workspace.

`match.py` evaluates a small regex against a string. It has bugs: `*` is
greedy but never backtracks (it consumes everything and then fails on any
trailing literal), and alternation is handled by a first-match-wins shortcut
that ignores the rest of the pattern.

Read SPEC.md — it defines the token grammar and the greedy-with-backtracking
matching semantics exactly.

The visible tests cover only simple literals and a single character class.
Hidden tests exercise `*` with a following literal (forcing backtracking),
alternation with precedence, and `full` vs substring mode.

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix:

    python3 match.py in.json out.json
    python3 tests/test_visible.py
