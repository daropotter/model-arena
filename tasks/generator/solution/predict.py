#!/usr/bin/env python3
"""Reference solution used only to verify the grader.

Recovers the parameters the way a solver would: infer the rotation from the
samples, unrotate, then solve the LCG congruences mod 2^31.
"""

import sys
from pathlib import Path

M = 1 << 31


def rot_left_31(value: int, bits: int) -> int:
    value &= M - 1
    return ((value << bits) | (value >> (31 - bits))) & (M - 1)


def solve(samples_by_seed):
    # The generator is state' = a*state + c mod 2^31, output = rotr(state', r).
    # We brute-force the rotation (31 options) and for each, look at the
    # unrotated sequences u. Consecutive differences cancel c:
    #   u[i+1] - u[i] = a * (u[i] - u[i-1])  mod 2^31
    # so a = diff[i+1] * inv(diff[i]) mod 2^31 when diff[i] is odd.
    for rot in range(31):
        seqs = []
        for seed, outs in samples_by_seed.items():
            states = [seed] + [rot_left_31(o, rot) for o in outs]
            seqs.append(states)
        candidate = None
        consistent = True
        for states in seqs:
            diffs = [(states[i + 1] - states[i]) % M for i in range(len(states) - 1)]
            for i in range(len(diffs) - 1):
                d0, d1 = diffs[i], diffs[i + 1]
                if d0 % 2 == 0:
                    continue
                a = (d1 * pow(d0, -1, M)) % M
                c = (states[1] - a * states[0]) % M
                if check(states, a, c):
                    candidate = (a, c, rot)
                    break
            if candidate:
                break
            if not any(d % 2 for d in diffs):
                consistent = False
        if candidate:
            a, c, r = candidate
            if all(check([seed] + [rot_left_31(o, r) for o in outs], a, c)
                   for seed, outs in samples_by_seed.items()):
                return a, c, r
    raise SystemExit("could not recover parameters")


def check(states, a, c):
    for i in range(len(states) - 1):
        if (a * states[i] + c) % M != states[i + 1]:
            return False
    return True


def load_samples(samples_dir: Path):
    data = {}
    for path in sorted(samples_dir.glob("seed_*.txt")):
        seed = int(path.stem.split("_")[1])
        outs = [int(l) for l in path.read_text().split() if l.strip()]
        data[seed] = outs
    return data


def main():
    here = Path(__file__).resolve().parent
    samples = load_samples(here / "samples")
    a, c, rot = solve(samples)

    def rotr(value, bits):
        value &= M - 1
        return ((value >> bits) | (value << (31 - bits))) & (M - 1)

    seed = int(sys.argv[1])
    n = int(sys.argv[2])
    state = seed % M
    for _ in range(n):
        state = (a * state + c) % M
        print(rotr(state, rot))


if __name__ == "__main__":
    main()
