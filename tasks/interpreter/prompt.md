You are working in /workspace.

`eval.py` evaluates expressions in a tiny language (a JSON-encoded AST). It
has bugs: variable references resolve by name through a single flat
dictionary, so lexical scoping is broken — shadowing leaks, and closures do
not capture the environment they were created in.

Read SPEC.md: it defines the grammar and the scoping rules exactly.

The visible tests cover only simple arithmetic and a top-level `let`. Hidden
tests exercise lexical scoping: shadowing, nested `let`, closures that
capture an environment, and lambdas returned from a function.

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix:

    python3 eval.py in.json out.json
    python3 -m pytest tests/ -q
