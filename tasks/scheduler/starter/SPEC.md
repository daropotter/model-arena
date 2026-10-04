# scheduler spec

This document is the authoritative contract. Where the implementation and
this document disagree, this document wins.

## CLI

```
python3 scheduler.py <in.json> <out.json>
```

Exit 0 on success. On invalid input print `error` to stderr and exit 1.

## Input

```json
{
  "jobs": [
    {"id": "a", "duration": 3, "deadline": 8, "depends": []},
    {"id": "b", "duration": 2, "deadline": 5, "depends": ["a"]}
  ]
}
```

`jobs` must be a non-empty list of job objects. Each job has:

- `id`: unique non-empty string.
- `duration`: positive integer.
- `deadline`: positive integer (the job must finish no later than this).
- `depends`: optional list of ids (defaults to `[]`); the job may not start
  before every listed job has finished. A job may not depend on itself,
  directly or transitively (a cycle is an error).

## Contract

The machine runs one job at a time, starting at time 0, with no idle time
before the last job finishes. Input list order has no scheduling meaning, so a
dependency may refer to a job listed later in the input.

The schedule must:

1. **Be feasible**: every job's start time is at least the finish time of
   each of its dependencies (dependencies finish = start + duration).
2. **Respect nothing else but dependencies** — there is no release-time
   constraint other than time 0 and dependencies.
3. **Be contiguous**: the first job starts at 0, and each following job
   starts exactly when the previous one finishes. Thus a job's finish time is
   the sum of the durations of that job and every job before it in `order`.
   A valid acyclic dependency graph always has an available next job, so no
   idle gaps are inserted.
4. **Minimize the number of late jobs**: a job is late when
   `finish > deadline`. Among schedules with the fewest late jobs, any
   one is accepted (ties are free), but the fewest-late guarantee is
   graded exactly.

## Output

```json
{
  "order": ["a", "b"],
  "late": 0
}
```

- `order`: the ids in execution order — a permutation of the input ids.
- `late`: the number of late jobs in that order.
- `order` must be a list of unique ids covering exactly the input jobs.
- The grader checks: feasibility of the order (dependencies, contiguity
  is implied by running one at a time), `late` computed correctly for
  that order, and that `late` equals the reference minimum.

## Invalid inputs

Empty or non-list `jobs`, duplicate ids, missing id/duration/deadline,
non-integer or non-positive duration/deadline (including JSON booleans),
malformed dependency lists, unknown dependency targets and dependency cycles
are all `error`, exit 1.
Dependency targets are validated after all job ids have been collected, so a
reference to a later input entry is valid.
