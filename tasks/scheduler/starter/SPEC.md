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

- `id`: unique non-empty string.
- `duration`: positive integer.
- `deadline`: positive integer (the job must finish no later than this).
- `depends`: list of ids; the job may not start before every listed job
  has finished. A job may not depend on itself, directly or transitively
  (a cycle is an error).

## Contract

The machine runs one job at a time, starting at time 0, with no idle time
before the last job finishes (the schedule is contiguous).

The schedule must:

1. **Be feasible**: every job's start time is at least the finish time of
   each of its dependencies (dependencies finish = start + duration).
2. **Respect nothing else but dependencies** — there is no release-time
   constraint other than time 0 and dependencies.
3. **Be contiguous**: the first job starts at 0, and each following job
   starts exactly when the previous one finishes. With dependencies this
   may force the machine to stay idle while waiting — in that case the
   schedule is still represented as one ordered list and idle gaps are
   allowed only when every remaining job is blocked by dependencies.
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

Duplicate ids, missing id/duration/deadline, non-positive duration,
unknown dependency target, dependency cycles — all `error`, exit 1.
