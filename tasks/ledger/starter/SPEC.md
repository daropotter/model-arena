# Ledger summarizer specification

This document is the authoritative contract. Where the implementation and this
document disagree, this document wins.

## CLI contract

```
python3 -m ledger summarize <input.json> <output.json>
```

Exit code 0 on success. The input and output files are JSON.

## Input format

```json
{
  "transactions": [
    {
      "id": "t1",
      "account": "alice",
      "amount": "-12.50",
      "timestamp": "2026-01-02T10:00:00+00:00"
    }
  ]
}
```

- `id`: string, unique.
- `account`: string.
- `amount`: decimal string, always with a dot decimal separator, may be negative
  or zero.
- `timestamp`: ISO 8601 UTC string. All timestamps use the same format and are
  lexicographically sortable. Timestamps may repeat across transactions.

## Rules

1. **Ordering.** Output transactions are sorted by `timestamp` ascending.
   When two transactions share the same timestamp, they keep their original
   input order (stable). Never reorder ties by `id` or any other field.

2. **Fee.** Every transaction is charged a fee of exactly 1% of the transaction
   amount's **absolute value**:

   ```
   fee = round_half_even(|amount| * 0.01, 2)
   ```

   All arithmetic and rounding is exact decimal arithmetic. Rounding is
   **round-half-even** (banker's rounding) to 2 decimal places. Do not use
   binary floating point anywhere in the computation. Examples:

   | amount  | fee   |
   |---------|-------|
   | 10.50   | 0.10  |
   | 2.50    | 0.02  |
   | 1.50    | 0.02  |
   | 0.50    | 0.00  |
   | -4.00   | 0.04  |
   | 0.00    | 0.00  |

   A negative amount produces a positive fee (the fee is charged on the
   absolute value).

3. **Account balance and count.** For each account:
   - `balance` is the sum of the account's transaction amounts, rounded
     round-half-even to 2 decimal places once at the end.
   - `count` counts only transactions whose amount is **not zero**.
     Zero-amount transactions are still included in the transactions list and
     in the account balance (they contribute 0), but they do not increment
     `count`.

4. **`fees_total`** is the sum of all transaction fees, rounded round-half-even
   to 2 decimal places once at the end.

5. All monetary values in the output are strings with exactly 2 decimal places
   and a dot decimal separator (for example `"0.00"`, `"-12.50"`, `"1234.56"`).

## Output format

```json
{
  "transactions": [
    {"id": "t1", "fee": "0.10"}
  ],
  "accounts": {
    "alice": {"balance": "-12.50", "count": 1}
  },
  "fees_total": "0.10"
}
```

- `transactions`: one entry per input transaction, in the required order,
  each with the transaction `id` and its `fee` string.
- `accounts`: every account that appears in the input, including accounts whose
  transactions are all zero-amount (those have `count: 0`).
- Account key order in the JSON object is not significant.
