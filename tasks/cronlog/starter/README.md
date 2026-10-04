# cronlog

File-backed job event log used from cron jobs and web hooks.

```
python3 -m cronlog --store ./store add backup
python3 -m cronlog --store ./store list
python3 tests/test_visible.py
```

See `SPEC.md`, in particular the concurrency contract.
