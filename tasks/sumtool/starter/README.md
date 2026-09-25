# sumtool

Sums a comma-separated list of numbers:

```
python3 sumtool.py '1,2,3'      # prints 6
python3 sumtool.py '1.5, 2'     # prints 3.5
python3 sumtool.py '-2, +1'     # prints -1
```

- Decimal numbers keep their fractional part: `'0.5'` prints `0.5`.
- Invalid input (non-numeric token, empty list, unknown characters)
  prints `error` to stderr and exits 1.
- The result never has unnecessary trailing zeros (`2`, not `2.00`).

The visible tests pass today; they do not cover the whole contract.
