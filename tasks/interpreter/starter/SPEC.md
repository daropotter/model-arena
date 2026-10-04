# interpreter spec

This document is the authoritative contract. Where the implementation and
this document disagree, this document wins.

## CLI

```
python3 eval.py <in.json> <out.json>
```

`in.json` contains a single expression (see below). Evaluate it and write the
result as `{"result": <int>}` to `out.json`, followed by a newline.

Exit 0 on success. On any error — malformed input, an undefined variable, a
type error, division by zero, an arity mismatch, or a reference to an unknown
operator — print `error` to stderr and exit 1.

## Expression grammar

Every expression is a JSON object with a `"type"` field. It must have exactly
the fields listed for its type (no missing or additional fields). JSON booleans
are not integers. The types are:

| type  | fields | meaning |
|---|---|---|
| `num` | `value` (int) | integer literal |
| `var` | `name` (str) | reference to a variable |
| `add` | `l`, `r` | integer addition |
| `sub` | `l`, `r` | integer subtraction |
| `mul` | `l`, `r` | integer multiplication |
| `div` | `l`, `r` | integer division (floor), error on divisor 0 |
| `neg` | `e` | unary negation |
| `if`  | `cond`, `then`, `else` | `then` if `cond != 0`, else `else` |
| `let` | `name` (str), `value`, `body` | bind `name` to `value` in `body` |
| `lam` | `params` (list of str), `body` | anonymous function |
| `call`| `fn`, `args` (list) | apply `fn` to `args` |

Values are integers and closures (functions). Nothing else exists at runtime.
Every position described as integer-valued, including arithmetic operands and
an `if` condition, must evaluate to an integer rather than a closure. The
top-level expression must evaluate to an integer.

## Evaluation semantics

- **Integers**: arbitrary-precision. `div` is integer floor division (Python's
  `//`), and dividing by zero is an error. `add`, `sub`, `mul` are exact.
- **`if`**: evaluate `cond`; if it is not `0` evaluate `then`, otherwise
  `else`. The untaken branch is *never* evaluated (so `if` can guard against
  a division by zero or an undefined variable in the dead branch).
- **`let`**: evaluate `value` in the current scope, then evaluate `body` in a
  new scope where `name` is bound to that value. The `name` is *not* visible
  inside `value` (no recursion through `let`). The binding lasts only for
  `body` and is discarded afterwards.
- **`lam`**: creates a closure. A closure captures the *environment* (the set
  of bindings) that was in scope at the point the lambda was created. It is a
  first-class value: it can be returned, stored, and passed as an argument.
- **`call`**: evaluate `fn` and each argument left-to-right. `fn` must be a
  closure; otherwise it is a type error. The number of arguments must equal
  the number of parameters; otherwise it is an error. Evaluate `body` in a
  new scope where each parameter is bound to the corresponding argument,
  *extended on top of the environment the closure captured*.

## Scoping (the hard part)

Scoping is **lexical**. A variable reference `var x` resolves to the
innermost `let` binding of `x` whose `body` textually encloses the reference,
or to the innermost parameter named `x` of the enclosing lambda. It never
resolves to a binding that merely happens to be on the call stack at runtime.

Two consequences that are graded exactly:

1. **Shadowing**: `let x = 1 in (let x = 2 in x)` evaluates to `2`; the outer
   `x` is unchanged and still `1` after the inner `let` ends.
2. **Capture**: a lambda remembers the environment where it was *created*, not
   where it is later *called*. In

   ```
   let x = 10 in
   let f = lam [] (var x) in
   let x = 20 in call f []
   ```

   `call f []` evaluates to `10` (f captured the first `x`), not `20`.

## Reference evaluation examples

- `let x = 1 in add(var x, num 2)` → `3`
- `let x = 1 in (let x = add(var x, 1) in var x)` → `2`
- `call(lam ["a"] (add (var a) (num 1)), [num 41])` → `42`
- `let f = lam ["x"] (mul (var x) (num 2)) in call(f, [num 21])` → `42`
- `let x = 10 in (let f = lam [] (var x) in (let x = 20 in call(f, [])))` → `10`
- `div(num 7, num 2)` → `3` (floor)
- `div(num 5, num 0)` → error
- `if(num 0, div(num 1, num 0), num 99)` → `99` (dead branch not evaluated)

## Errors

Undefined variable, calling a non-closure, arity mismatch, division by zero,
malformed JSON, unknown expression type, and a non-integer where an integer is
required are all errors: print `error` to stderr and exit 1.
