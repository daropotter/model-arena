You are working in /workspace.

`pack.py` and `unpack.py` form a two-step pipeline: `pack.py` turns a JSON
object into a pipe file, `unpack.py` turns it back. They must be consistent:
`unpack(pack(x)) == x` for every valid input.

Both files have bugs. Read SPEC.md — it defines the pipe format and the
escaping rules exactly. Fix both tools so they match it.

The visible tests cover only the happy path (string values, no special
characters). Hidden tests exercise the full format: numbers, booleans,
null, escaped characters, and malformed pipe files that must be rejected.

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix by running the round trip yourself:

    python3 pack.py in.json out.pipe
    python3 unpack.py out.pipe back.json
    python3 tests/test_visible.py
