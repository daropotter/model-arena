You are working in /workspace.

`scheduler.py` schedules a set of jobs on one machine and tries to minimize
the number of late jobs. It has bugs: it keeps input order instead of
optimizing, does not validate dependencies, and does not enforce their order.

Read SPEC.md: it defines the scheduling contract exactly — feasibility
rules, dependency rules, and what the output must contain.

The visible tests use input orders that are already feasible and optimal.
Hidden tests include forward dependency references, dependency chains and
forks, cycles (which must be rejected), and an input where a short job must be
preferred over a long one to meet a deadline. All finish times use cumulative
elapsed time on the one contiguous machine.

Do not modify SPEC.md or tests/. Use relative paths only.

Verify your fix:

    python3 scheduler.py in.json out.json
    python3 tests/test_visible.py
