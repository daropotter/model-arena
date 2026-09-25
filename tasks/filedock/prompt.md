You are working in /workspace.

`organize.py` is supposed to organize report files from an inbox directory
and write a manifest describing the work done. It has bugs: it misses
duplicates whose filenames differ and it accepts calendar dates that do not
exist.

Read README.md: it is the exact contract. Fix `organize.py` so it matches.

The visible inbox has only two files and covers the simple path. The inboxes
this will be graded on are bigger and messier: duplicates with different
names, files with impossible dates (e.g. report-20260230.txt), files that
fail the naming pattern, empty files, and running the tool twice on an
already-processed inbox.

Do not modify README.md or tests/. Use relative paths only.

Verify your fix by running:

    python3 organize.py inbox manifest.json
    python3 -m pytest tests/ -q
