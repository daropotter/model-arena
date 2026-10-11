# Orders service

Python 3 standard library; no downloads needed. Production entry points are
`src/orders/`, built with `python3 build.py` into `dist/orders.pyz`.
`prototypes/` is historical and is not packaged. Start a local database by
applying `fixtures/seed.sql` with sqlite3 (Python's sqlite3 module is fine).
Run `python3 dist/orders.pyz migrate --db PATH`, then
`python3 dist/orders.pyz serve --db PATH --port PORT`.

The old consumer is `clients/legacy.py BASE TOKEN ORDER_ID`. The visible
smoke is `python3 tests/test_visible.py`. Add your own tests in `tests_extra/`.
Read SPEC.md and RELEASE.md for the requested feature and release workflow.
STAGES.md lists the 36 acceptance milestones and their dependencies.
