You are working in /workspace.

`scheduler.py` schedules a set of jobs on one machine and tries to
minimize lateness. It has a bug: it ignores job deadlines, so it builds a
valid schedule but a bad one (too many late jobs).

Read SPEC.md: it defines the scheduling contract exactly — feasibility
rules, dependency rules, and what the output must contain.

The visible tests cover only dependency-free inputs. Hidden tests include
dependency chains, cycles (which must be rejected), and an input where a
short job must be preferred over a long one to meet a deadline.

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix:

    python3 scheduler.py in.json out.json
    python3 -m pytest tests/ -q
