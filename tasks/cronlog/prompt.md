You are working in /workspace.

cronlog records job events in a JSON store. It is used from cron jobs, web
hooks and scripts that run concurrently, and it currently corrupts or loses
events when several commands touch the store at once.

Read SPEC.md. It defines the exact concurrency contract: an exclusive lock for
writers, shared locks for readers, a configurable lock timeout, and atomic
replacements. Implement it across the package.

Existing single-process behavior (commands, output format, JSON shape) must
not change. Visible tests pass today but they never run anything concurrently.

Do not modify SPEC.md or tests/. Use relative paths only.
