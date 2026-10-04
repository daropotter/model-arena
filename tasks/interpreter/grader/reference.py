#!/usr/bin/env python3
"""Reference interpreter. Used only by the hidden grader."""


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


def _eval(node, env):
    t = node["type"]
    if t == "num":
        return node["value"]
    if t == "var":
        return env.lookup(node["name"])
    if t == "add":
        return require_int(_eval(node["l"], env)) + require_int(_eval(node["r"], env))
    if t == "sub":
        return require_int(_eval(node["l"], env)) - require_int(_eval(node["r"], env))
    if t == "mul":
        return require_int(_eval(node["l"], env)) * require_int(_eval(node["r"], env))
    if t == "div":
        left = require_int(_eval(node["l"], env))
        r = require_int(_eval(node["r"], env))
        if r == 0:
            raise ValueError("division by zero")
        return left // r
    if t == "neg":
        return -require_int(_eval(node["e"], env))
    if t == "if":
        if require_int(_eval(node["cond"], env)) != 0:
            return _eval(node["then"], env)
        return _eval(node["else"], env)
    if t == "let":
        value = _eval(node["value"], env)
        return _eval(node["body"], env.extend([node["name"]], [value]))
    if t == "lam":
        return Closure(node["params"], node["body"], env)
    if t == "call":
        fn = _eval(node["fn"], env)
        if not isinstance(fn, Closure):
            raise ValueError("not a function")
        args = [_eval(a, env) for a in node["args"]]
        if len(args) != len(fn.params):
            raise ValueError("arity mismatch")
        return _eval(fn.body, fn.env.extend(fn.params, args))
    raise ValueError(f"unknown type {t}")


def eval_reference(node):
    validate_ast(node)
    return require_int(_eval(node, Env()))


def _num(v):
    return {"type": "num", "value": v}


def _var(n):
    return {"type": "var", "name": n}


def _let(n, v, b):
    return {"type": "let", "name": n, "value": v, "body": b}


def _lam(params, body):
    return {"type": "lam", "params": params, "body": body}


def _call(fn, args):
    return {"type": "call", "fn": fn, "args": args}


def _add(l, r):
    return {"type": "add", "l": l, "r": r}


def _mul(l, r):
    return {"type": "mul", "l": l, "r": r}


def _sub(l, r):
    return {"type": "sub", "l": l, "r": r}


def _div(l, r):
    return {"type": "div", "l": l, "r": r}


def _neg(e):
    return {"type": "neg", "e": e}


def _if(c, t, e):
    return {"type": "if", "cond": c, "then": t, "else": e}


# (name, AST, expected result). Every expression evaluates to an int.
CASES = [
    ("add", _add(_num(1), _num(2)), 3),
    ("div_floor", _div(_num(7), _num(2)), 3),
    ("div_neg", _div(_num(-7), _num(2)), -4),
    ("mul", _mul(_num(6), _num(7)), 42),
    ("sub_neg", _sub(_num(0), _num(5)), -5),
    ("neg", _neg(_num(3)), -3),
    ("top_let", _let("x", _num(1), _add(_var("x"), _num(2))), 3),
    ("shadow_inner", _let("x", _num(1),
                          _let("x", _num(2), _var("x"))), 2),
    ("shadow_outer_unchanged", _let("x", _num(1),
                                    _add(_let("x", _num(2), _var("x")),
                                         _var("x"))), 3),
    ("let_chain", _let("x", _num(1),
                       _let("x", _add(_var("x"), _num(1)), _var("x"))), 2),
    ("nested_let_distinct", _let("a", _num(10),
                                 _let("b", _add(_var("a"), _num(5)),
                                      _sub(_var("b"), _var("a")))), 5),
    ("call_basic", _call(_lam(["a"], _add(_var("a"), _num(1))), [_num(41)]),
     42),
    ("call_two_args", _call(_lam(["a", "b"], _add(_var("a"), _var("b"))),
                            [_num(30), _num(12)]), 42),
    ("higher_order", _call(_call(_lam(["x"], _lam(["y"],
                                _add(_var("x"), _var("y")))), [_num(40)]),
                           [_num(2)]), 42),
    ("closure_capture", _let("x", _num(10),
                             _let("f", _lam([], _var("x")),
                                  _let("x", _num(20), _call(_var("f"), [])))),
     10),
    ("closure_shadow_param", _let("x", _num(10),
                                  _call(_lam(["x"], _var("x")), [_num(99)])),
     99),
    ("if_true", _if(_num(1), _num(42), _num(0)), 42),
    ("if_false", _if(_num(0), _num(0), _num(42)), 42),
    ("if_lazy_no_divzero", _if(_num(0), _div(_num(1), _num(0)), _num(99)),
     99),
    ("curried_add", _let("add", _lam(["a"], _lam(["b"],
                         _add(_var("a"), _var("b")))),
                         _call(_call(_var("add"), [_num(20)]), [_num(22)])),
     42),
    ("big_arithmetic", _mul(_add(_num(1000000), _num(1)), _num(2)), 2000002),
    ("factory_returns_closure", _call(_call(_lam(["n"], _lam(["m"],
        _add(_var("n"), _var("m")))), [_num(40)]), [_num(2)]), 42),
    ("param_pollution_isolated", _let("x", _num(1),
        _add(_call(_lam(["x"], _var("x")), [_num(50)]), _var("x"))), 51),
    ("closure_ignores_later_rebind", _let("x", _num(10),
        _let("f", _lam([], _var("x")),
             _let("dummy", _let("x", _num(20), _var("x")),
                  _call(_var("f"), [])))), 10),
    ("two_closures_capture_distinct", _let("x", _num(1),
        _let("a", _lam([], _var("x")),
             _let("x", _num(2),
                  _let("b", _lam([], _var("x")),
                       _sub(_call(_var("b"), []),
                            _call(_var("a"), [])))))), 1),
    ("nested_let_restores_after_body", _let("x", _num(1),
        _let("y", _let("x", _num(10), _add(_var("x"), _num(1))),
             _add(_var("y"), _var("x")))), 12),
]

# (name, AST) that must exit non-zero.
ERRORS = [
    ("undefined_var", _var("nope")),
    ("div_by_zero", _div(_num(5), _num(0))),
    ("call_non_closure", _call(_num(3), [_num(1)])),
    ("arity_mismatch", _call(_lam(["a"], _var("a")), [_num(1), _num(2)])),
    ("unknown_type", {"type": "frobnicate"}),
    ("bool_is_not_int", _num(True)),
    ("float_is_not_int", _num(1.5)),
    ("num_missing_value", {"type": "num"}),
    ("num_extra_field", {"type": "num", "value": 1, "extra": 2}),
    ("node_not_object", ["num", 1]),
    ("type_not_string", {"type": 1}),
    ("var_name_not_string", _var(3)),
    ("let_name_not_string", _let(3, _num(1), _num(2))),
    ("params_not_list", _lam("x", _num(1))),
    ("param_not_string", _lam([1], _num(1))),
    ("args_not_list", _call(_lam([], _num(1)), {})),
    ("malformed_nested", _add(_num(1), {"type": "num"})),
    ("malformed_dead_branch", _if(_num(0), {"type": "num"}, _num(1))),
    ("closure_in_arithmetic", _add(_lam([], _num(1)), _num(2))),
    ("closure_condition", _if(_lam([], _num(1)), _num(1), _num(0))),
    ("closure_result", _lam([], _num(1))),
]
