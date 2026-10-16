You are working in /workspace as the reviewer of a pull request.

PR.md is the author's description, change.diff is the change, and the
workspace already contains the code after the change. README.md is the
authoritative pricing contract. You may read and run the code and its
tests (`python3 tests/test_pricing.py`) and write throwaway scripts under
/tmp to check your suspicions.

Find the real problems this change introduces and write your review to
review.json exactly as REVIEW.md describes. Hidden grading compares your
findings with the known problems in the change; false positives cost
points, so report only what you can justify.

Do not modify any file other than review.json. Use relative paths only.
