"""Reference generator behind the `generator` task.

Algorithm (kept hidden from the workspace):
  state' = (a * state + c) mod 2^31
  output = rotate_right_31(state', ROT)

a is odd, c is odd (so x1 - seed is always odd and invertible mod 2^31).
"""

M = 1 << 31
A = 1103515245
C = 12345
ROT = 13


def rot_right_31(value: int, bits: int) -> int:
    value &= M - 1
    return ((value >> bits) | (value << (31 - bits))) & (M - 1)


def rot_left_31(value: int, bits: int) -> int:
    value &= M - 1
    return ((value << bits) | (value >> (31 - bits))) & (M - 1)


def generate(seed: int, n: int) -> list[int]:
    state = seed % M
    out = []
    for _ in range(n):
        state = (A * state + C) % M
        out.append(rot_right_31(state, ROT))
    return out


SAMPLE_SEEDS = [1, 42, 12345, 999999, 123456789]


if __name__ == "__main__":
    import sys
    seed = int(sys.argv[1])
    n = int(sys.argv[2])
    for value in generate(seed, n):
        print(value)
