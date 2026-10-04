# regex spec

This document is the authoritative contract. Where the implementation and
this document disagree, this document wins.

## CLI

```
python3 match.py <in.json> <out.json>
```

`in.json` is `{"pattern": "...", "text": "...", "full": <bool>}`. Evaluate the
pattern against the text and write `{"match": <bool>}` to `out.json` followed
by a newline.

Exit 0 on success. On a malformed pattern, or malformed input, print `error`
to stderr and exit 1.

## Match modes

- `full` is `true`: the pattern must match the **entire** text (the match
  spans from the first to the last character, nothing left over).
- `full` is `false`: the pattern must match **somewhere** in the text (a
  non-empty-or-empty substring). The empty pattern or a pattern that matches
  the empty string succeeds at every position, so it matches any text.

## Pattern syntax

The pattern is a small regular language. Tokens, in precedence order (highest
binding first):

1. **Literal**: any character other than `(`, `)`, `*`, `|`, `[`, `]`, `\\`.
   Matches itself. `.` is an ordinary literal (no wildcard in this language).
2. **Character class** `[...]`: matches exactly one character that is in the
   set. A leading `^` negates the set. `\\` inside a class escapes the next
   character (so `[\\]]` matches `]` and `[\\[]` matches `[`). A `-` between
   two characters denotes a range by code point (e.g. `[a-z]`, `[0-9]`); a
   `-` at the very start or very end is a literal `-`. The class matches a
   single character. A class must contain at least one character after an
   optional leading `^`.
3. **Group** `(...)`: groups a sub-pattern; used only for precedence (no
   capture, no backreferences).
4. **Quantifier** `*`: postfix, applies to the immediately preceding token or
   group. Means **zero or more** of that item.
5. **Alternation** `|`: lowest precedence. `a|b` matches `a` or `b`. `|` has
   lower precedence than concatenation, so `ab|cd` means `(ab)|(cd)`, not
   `a(b|c)d`.

Concatenation binds tighter than `|` but looser than `*`. So `ab*` means `a`
followed by zero or more `b`; `(ab)*` means zero or more of `ab`.

## Matching semantics (the hard part)

Matching is **leftmost, greedy with backtracking**:

- Concatenation and quantifiers try to consume as much as possible, but if the
  overall match then fails, they backtrack to a shorter (or zero-length)
  consumption and retry.
- `*` is **greedy**: it first tries to consume as many repetitions as
  possible, then backtracks one repetition at a time.
- Alternation tries alternatives **left to right** and commits to the first
  one that can lead to a full match.
- Backtracking crosses syntax boundaries: if an alternative chosen inside a
  group prevents the enclosing sequence or `*` from matching, later group
  alternatives and different repetition partitions must be tried.

These two behaviors, graded exactly, are the classic reasons a naive matcher
fails:

1. **Greedy with backtracking**: pattern `a*a` against text `aaa` must match
   (`*` takes two `a`s, then the literal `a` takes the third). A matcher that
   makes `a*` eat everything and then fails is wrong.
2. **Alternation order**: pattern `ab|a` against `ab` must match the *whole*
   `ab`; `a|ab` against `ab` also matches (via `a`, leaving `b`, which is fine
   when `full` is false), but under `full` mode `a|ab` must match `ab` via the
   second alternative after the first fails.

## Reference examples

- `{"pattern":"a*a","text":"aaa","full":true}` → `true`
- `{"pattern":"a*a","text":"aa","full":true}` → `true` (`*` takes one `a`)
- `{"pattern":"(a|ab)c","text":"abc","full":true}` → `true` (the group
  backtracks from `a` to `ab`)
- `{"pattern":"(ab)*","text":"abab","full":true}` → `true`
- `{"pattern":"ab|cd","text":"cd","full":true}` → `true`
- `{"pattern":"a|ab","text":"ab","full":true}` → `true`
- `{"pattern":"[^0-9]","text":"a","full":true}` → `true`
- `{"pattern":"[^0-9]","text":"5","full":true}` → `false`
- `{"pattern":"[a-c]","text":"b","full":true}` → `true`
- `{"pattern":"a*","text":"","full":true}` → `true` (zero repetitions)
- `{"pattern":"a*","text":"bbb","full":false}` → `true` (empty match is allowed)
- `{"pattern":"a*b","text":"aaab","full":true}` → `true`
- `{"pattern":"[\\]]","text":"]","full":true}` → `true`

## Errors

Unbalanced parentheses, an empty or unterminated character class, a `*` with
nothing to quantify (leading `*`), or a dangling `\\` at end of pattern are
all errors: print `error` to stderr and exit 1.
