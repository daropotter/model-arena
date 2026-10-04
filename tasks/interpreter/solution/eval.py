#!/usr/bin/env python3
"""Evaluate a tiny language with correct lexical scoping. See SPEC.md."""

import json
import sys
from pathlib import Path


class Env:
    def __init__(self, parent=None):
        self.parent = parent
        self.bindings = {}

    def lookup(self, name):
        env = self
        while env is not None:
            if name in env.bindings:
                return env.bindings[name]
            env = env.parent
        raise ValueError(f"undefined variable {name}")

    def extend(self, names, values):
        env = Env(self)
        for n, v in zip(names, values):
            env.bindings[n] = v
        return env


class Closure:
    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env


FIELDS = {
    "num": {"type", "value"},
    "var": {"type", "name"},
    "add": {"type", "l", "r"},
    "sub": {"type", "l", "r"},
    "mul": {"type", "l", "r"},
    "div": {"type", "l", "r"},
    "neg": {"type", "e"},
    "if": {"type", "cond", "then", "else"},
    "let": {"type", "name", "value", "body"},
    "lam": {"type", "params", "body"},
    "call": {"type", "fn", "args"},
}


def validate_ast(node):
    if not isinstance(node, dict) or type(node.get("type")) is not str:
        raise ValueError("expression must be an object with a string type")
    t = node["type"]
    if t not in FIELDS or set(node) != FIELDS[t]:
        raise ValueError("unknown type or malformed fields")
    if t == "num":
        if type(node["value"]) is not int:
            raise ValueError("num value must be an integer")
        return
    if t == "var":
        if type(node["name"]) is not str:
            raise ValueError("var name must be a string")
        return
    if t in {"add", "sub", "mul", "div"}:
        validate_ast(node["l"])
        validate_ast(node["r"])
    elif t == "neg":
        validate_ast(node["e"])
    elif t == "if":
        validate_ast(node["cond"])
        validate_ast(node["then"])
        validate_ast(node["else"])
    elif t == "let":
        if type(node["name"]) is not str:
            raise ValueError("let name must be a string")
        validate_ast(node["value"])
        validate_ast(node["body"])
    elif t == "lam":
        if not isinstance(node["params"], list) or any(
                type(param) is not str for param in node["params"]):
            raise ValueError("params must be a list of strings")
        validate_ast(node["body"])
    elif t == "call":
        if not isinstance(node["args"], list):
            raise ValueError("args must be a list")
        validate_ast(node["fn"])
        for arg in node["args"]:
            validate_ast(arg)


def require_int(value):
    if type(value) is not int:
        raise ValueError("integer required")
    return value


def eval_expr(node, env):
    t = node["type"]
    if t == "num":
        return node["value"]
    if t == "var":
        return env.lookup(node["name"])
    if t == "add":
        return require_int(eval_expr(node["l"], env)) + require_int(eval_expr(node["r"], env))
    if t == "sub":
        return require_int(eval_expr(node["l"], env)) - require_int(eval_expr(node["r"], env))
    if t == "mul":
        return require_int(eval_expr(node["l"], env)) * require_int(eval_expr(node["r"], env))
    if t == "div":
        left = require_int(eval_expr(node["l"], env))
        r = require_int(eval_expr(node["r"], env))
        if r == 0:
            raise ValueError("division by zero")
        return left // r
    if t == "neg":
        return -require_int(eval_expr(node["e"], env))
    if t == "if":
        if require_int(eval_expr(node["cond"], env)) != 0:
            return eval_expr(node["then"], env)
        return eval_expr(node["else"], env)
    if t == "let":
        value = eval_expr(node["value"], env)
        new_env = env.extend([node["name"]], [value])
        return eval_expr(node["body"], new_env)
    if t == "lam":
        return Closure(node["params"], node["body"], env)
    if t == "call":
        fn = eval_expr(node["fn"], env)
        if not isinstance(fn, Closure):
            raise ValueError("not a function")
        args = [eval_expr(a, env) for a in node["args"]]
        if len(args) != len(fn.params):
            raise ValueError("arity mismatch")
        call_env = fn.env.extend(fn.params, args)
        return eval_expr(fn.body, call_env)
    raise ValueError(f"unknown type {t}")


def main():
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        node = json.loads(Path(sys.argv[1]).read_text())
        validate_ast(node)
        result = require_int(eval_expr(node, Env()))
        Path(sys.argv[2]).write_text(json.dumps({"result": result}) + "\n")
    except (OSError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
