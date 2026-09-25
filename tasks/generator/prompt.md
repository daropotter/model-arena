You are working in /workspace.

A legacy system produced IDs with an opaque generator. All that survives is a
set of recorded (seed, output) samples in samples/ and the note in SPEC.md.
The original code is gone.

Reconstruct the algorithm and write predict.py:

    python3 predict.py <seed> <n>

which prints the next `n` outputs for the given seed, one per line, exactly as
the original generator would (0 <= output < 2^31).

You must derive the algorithm from the samples. Hardcoding sample values is
not enough: grading uses seeds and step offsets you have not seen, including
seeds beyond the sample range. See SPEC.md for details.
