# tasklog

Tiny task CLI backed by a JSON store.

```
python3 -m tasklog --store ./store.json add "write tests" --tag dev
python3 -m tasklog --store ./store.json list
python3 tests/test_visible.py
```

See `SPEC.md` for the full contract.
