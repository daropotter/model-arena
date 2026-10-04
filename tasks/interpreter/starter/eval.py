#!/usr/bin/env python3
"""Evaluate a tiny language. See SPEC.md for the contract.

BUGGY: a single flat scope dict is threaded through evaluation, so a `var`
resolves to the most recent binding of that name anywhere (dynamic scoping),
and `lam` does not capture an environment at all.
"""

import json
import sys
from pathlib import Path


def eval_expr(node, scope):
    t = node["type"]
    if t == "num":
        return node["value"]
    if t == "var":
        name = node["name"]
        if name not in scope:
            raise ValueError(f"undefined variable {name}")
        return scope[name]
    if t == "add":
        return eval_expr(node["l"], scope) + eval_expr(node["r"], scope)
    if t == "sub":
        return eval_expr(node["l"], scope) - eval_expr(node["r"], scope)
    if t == "mul":
        return eval_expr(node["l"], scope) * eval_expr(node["r"], scope)
    if t == "div":
        r = eval_expr(node["r"], scope)
        if r == 0:
            raise ValueError("division by zero")
        return eval_expr(node["l"], scope) // r
    if t == "neg":
        return -eval_expr(node["e"], scope)
    if t == "if":
        if eval_expr(node["cond"], scope) != 0:
            return eval_expr(node["then"], scope)
        return eval_expr(node["else"], scope)
    if t == "let":
        value = eval_expr(node["value"], scope)
        # BUG: binds into the SAME flat scope, leaking past body
        scope[node["name"]] = value
        return eval_expr(node["body"], scope)
    if t == "lam":
        # BUG: no closure; the lambda re-reads scope at call time
        return ("closure", node["params"], node["body"])
    if t == "call":
        fn = eval_expr(node["fn"], scope)
        if not isinstance(fn, tuple) or fn[0] != "closure":
            raise ValueError("not a function")
        _, params, body = fn
        args = [eval_expr(a, scope) for a in node["args"]]
        if len(args) != len(params):
            raise ValueError("arity mismatch")
        # BUG: binds params into the caller's scope, and shares it
        for p, a in zip(params, args):
            scope[p] = a
        return eval_expr(body, scope)
    raise ValueError(f"unknown type {t}")


def main():
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        node = json.loads(Path(sys.argv[1]).read_text())
        result = eval_expr(node, {})
        Path(sys.argv[2]).write_text(
            json.dumps({"result": result}) + "\n")
    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
