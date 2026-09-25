# Recovered generator notes

The ID generator was a small integer PRNG. From the ops notes we know:

- It is a 31-bit linear congruential generator producing values in `[0, 2^31)`.
- State update: `state = (a * state + c) mod 2^31`.
- The output is derived from the new state, possibly via a permutation or bit
  manipulation step (the notes are unclear here).
- The seed is an integer in `[0, 2^31)` and is used directly as the initial
  state.
- Only the first N outputs per seed were logged.

`samples/` contains recorded output sequences: one file per seed group. Each
line is the next output for that sequence, starting at step 1 (no seed output
is recorded).

## Task

Write `predict.py`:

```
python3 predict.py <seed> <n>
```

- Prints the first `n` outputs of the generator for `<seed>`, one per line.
- Must work for unseen integer seeds in `[0, 2^31)`.
- Must be exact for the first 1000 steps at least.
