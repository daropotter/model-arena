You are working in /workspace.

`tasklog` is a small Python CLI with a persistent JSON store. Read SPEC.md —
it describes the exact CLI contract, including a new `snooze` command and a
store format migration from version 1 to version 2.

Implement everything SPEC.md requires, touching as many modules as needed.
Existing commands must keep their current behavior and output format.

Do not modify SPEC.md or tests/. The visible tests pass today but cover only
the old commands. Use relative paths only.
