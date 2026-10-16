# How to submit the review

Write your review to `review.json` in the workspace root. Do not modify
any other file: the code under review, `change.diff`, `PR.md` and this
file are read-only, and changing any of them fails the run. Scratch files
are fine outside the reviewed paths (for example under `/tmp`).

```json
{
  "verdict": "request_changes",
  "findings": [
    {
      "file": "notes/api.py",
      "line": 12,
      "severity": "high",
      "category": "correctness",
      "title": "One-line summary of the problem",
      "explanation": "What is wrong, which input or scenario triggers it, what happens then, and how to fix it."
    }
  ]
}
```

## Fields

- `verdict`: `approve` when the change can be merged as it is;
  `request_changes` when at least one medium or high finding must be
  fixed first.
- `file`: path relative to the workspace root, as in `change.diff`
  (without the `a/` or `b/` prefix).
- `line`: line number in the file as it is in the workspace (that is,
  after the change), pointing at the faulty statement. When the problem
  is a check or step the change is missing, point at the changed line
  where it belongs.
- `severity`:
  - `high`: security vulnerability, data loss or corruption, wrong money
    amounts, or a crash on valid input;
  - `medium`: wrong behaviour on valid input, a violation of the
    documented contract, or an unintended change of existing behaviour;
  - `low`: a robustness or maintainability problem with no observable
    effect today.
- `category`: one of `correctness`, `security`, `behavior-change`,
  `error-handling`, `data-integrity`, `concurrency`, `performance`,
  `maintainability`.
- `title` and `explanation`: free text; the explanation has at least 20
  characters.

## Rules

- Review what this change introduces: changed lines, and existing code
  whose behaviour the change breaks. Code the change does not touch or
  affect has already been reviewed.
- Report each distinct problem once, at its most specific line, even if
  it shows up in several places.
- False positives cost points. Findings about correct code, about
  behaviour that PR.md or the documentation describe as intended, or
  about style, naming, missing tests or missing documentation all count
  as false positives. Do not pad the review.
- At most 12 findings; a longer review scores zero.
