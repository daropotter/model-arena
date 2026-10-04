You are working in /workspace.

`sumtool.py` contains a single function, `parse_numbers(text)`, and a small
CLI built on top of it. The function has two bugs. The docstring in the file
defines the contract exactly; the CLI is described in README.md.

Fix `parse_numbers` so it matches its docstring and the README exactly.
Do not rewrite the module from scratch — change only what is broken.

Do not modify tests/. The visible tests pass today, but they are not the
contract: the docstring and README are. Use relative paths only.

Verify your fix by running:

    python3 sumtool.py '1.5, 2, -3'   # see README for expected output
    python3 tests/test_visible.py
