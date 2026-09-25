# order export normalizer

`normalize.py` turns messy order exports into the canonical CSV from
`SPEC.md`:

```
python3 normalize.py <input.csv> <output.csv> <report.json>
python3 tests/test_visible.py
```

Sample exports live in `data/`. The current implementation only covers simple
rows; the spec is much wider.
