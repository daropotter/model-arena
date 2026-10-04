"""Oracle tests for the interpreter task.

They exercise the hidden grader's reference (eval_reference) with
hand-evaluated programs and metamorphic properties; the shipped
starter/solution is never imported.
"""

import importlib.util
import random
import sys
import unittest
from pathlib import Path

from tests.support import ROOT

GRADER = ROOT / "tasks" / "interpreter" / "grader"


def _load_reference():
    if str(GRADER) not in sys.path:
        sys.path.insert(0, str(GRADER))
    spec = importlib.util.spec_from_file_location(
        "interpreter_grader_reference", GRADER / "reference.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REF = _load_reference()
eval_reference = REF.eval_reference


def num(value):
    return {"type": "num", "value": value}


def var(name):
    return {"type": "var", "name": name}


def add(left, right):
    return {"type": "add", "l": left, "r": right}


def sub(left, right):
    return {"type": "sub", "l": left, "r": right}


def mul(left, right):
    return {"type": "mul", "l": left, "r": right}


def div(left, right):
    return {"type": "div", "l": left, "r": right}


def neg(expr):
    return {"type": "neg", "e": expr}


def if_(cond, then, otherwise):
    return {"type": "if", "cond": cond, "then": then, "else": otherwise}


def let(name, value, body):
    return {"type": "let", "name": name, "value": value, "body": body}


def lam(params, body):
    return {"type": "lam", "params": params, "body": body}


def call(fn, args):
    return {"type": "call", "fn": fn, "args": args}


def _binding_names(node):
    names = set()
    kind = node["type"]
    if kind == "var":
        names.add(node["name"])
    elif kind in ("add", "sub", "mul", "div"):
        names |= _binding_names(node["l"])
        names |= _binding_names(node["r"])
    elif kind == "neg":
        names |= _binding_names(node["e"])
    elif kind == "if":
        names |= _binding_names(node["cond"])
        names |= _binding_names(node["then"])
        names |= _binding_names(node["else"])
    elif kind == "let":
        names.add(node["name"])
        names |= _binding_names(node["value"])
        names |= _binding_names(node["body"])
    elif kind == "lam":
        names.update(node["params"])
        names |= _binding_names(node["body"])
    elif kind == "call":
        names |= _binding_names(node["fn"])
        for arg in node["args"]:
            names |= _binding_names(arg)
    return names


def _rename(node, mapping):
    kind = node["type"]
    if kind == "num":
        return dict(node)
    if kind == "var":
        return var(mapping.get(node["name"], node["name"]))
    if kind in ("add", "sub", "mul", "div"):
        return {"type": kind,
                "l": _rename(node["l"], mapping),
                "r": _rename(node["r"], mapping)}
    if kind == "neg":
        return neg(_rename(node["e"], mapping))
    if kind == "if":
        return if_(_rename(node["cond"], mapping),
                   _rename(node["then"], mapping),
                   _rename(node["else"], mapping))
    if kind == "let":
        new_name = mapping.get(node["name"], node["name"])
        inner = dict(mapping)
        inner[node["name"]] = new_name
        return let(new_name,
                   _rename(node["value"], mapping),
                   _rename(node["body"], inner))
    if kind == "lam":
        inner = dict(mapping)
        params = []
        for param in node["params"]:
            new_param = mapping.get(param, param)
            params.append(new_param)
            inner[param] = new_param
        return lam(params, _rename(node["body"], inner))
    if kind == "call":
        return call(_rename(node["fn"], mapping),
                    [_rename(arg, mapping) for arg in node["args"]])
    raise AssertionError(f"unexpected node type {kind}")


class _Generator:
    def __init__(self, rng):
        self.rng = rng
        self.counter = 0

    def fresh(self, prefix):
        self.counter += 1
        return f"{prefix}{self.counter}"

    def expr(self, env, depth):
        rng = self.rng
        choices = ["num"]
        if env:
            choices.append("var")
        if depth > 0:
            choices += ["add", "sub", "mul", "neg", "if", "let", "call",
                        "div"]
        kind = rng.choice(choices)
        if kind == "num":
            return num(rng.randint(-9, 9))
        if kind == "var":
            return var(rng.choice(env))
        if kind == "div":
            return div(self.expr(env, depth - 1), num(rng.choice([1, 2, 3, 5])))
        if kind in ("add", "sub", "mul"):
            left = self.expr(env, depth - 1)
            right = self.expr(env, depth - 1)
            return {"add": add, "sub": sub, "mul": mul}[kind](left, right)
        if kind == "neg":
            return neg(self.expr(env, depth - 1))
        if kind == "if":
            return if_(self.expr(env, depth - 1),
                       self.expr(env, depth - 1),
                       self.expr(env, depth - 1))
        if kind == "let":
            name = self.fresh("v")
            value = self.expr(env, depth - 1)
            return let(name, value, self.expr(env + [name], depth - 1))
        if kind == "call":
            params = [self.fresh("p") for _ in range(self.rng.randrange(3))]
            body = self.expr(env + params, depth - 1)
            args = [self.expr(env, depth - 1) for _ in params]
            return call(lam(params, body), args)
        raise AssertionError(kind)


class SpecExamplesTests(unittest.TestCase):
    def test_let_simple(self):
        self.assertEqual(
            eval_reference(let("x", num(1), add(var("x"), num(2)))), 3)

    def test_let_name_not_visible_in_value(self):
        program = let("x", num(1), let("x", add(var("x"), num(1)), var("x")))
        self.assertEqual(eval_reference(program), 2)

    def test_call_basic(self):
        program = call(lam(["a"], add(var("a"), num(1))), [num(41)])
        self.assertEqual(eval_reference(program), 42)

    def test_let_bound_lambda(self):
        program = let("f", lam(["x"], mul(var("x"), num(2))),
                      call(var("f"), [num(21)]))
        self.assertEqual(eval_reference(program), 42)

    def test_capture_uses_creation_environment(self):
        program = let("x", num(10),
                      let("f", lam([], var("x")),
                          let("x", num(20), call(var("f"), []))))
        self.assertEqual(eval_reference(program), 10)

    def test_shadowing_inner_wins(self):
        program = let("x", num(1), let("x", num(2), var("x")))
        self.assertEqual(eval_reference(program), 2)

    def test_shadowing_outer_unchanged(self):
        program = let("x", num(1),
                      add(let("x", num(2), var("x")), var("x")))
        self.assertEqual(eval_reference(program), 3)

    def test_floor_division(self):
        self.assertEqual(eval_reference(div(num(7), num(2))), 3)
        self.assertEqual(eval_reference(div(num(-7), num(2))), -4)

    def test_closure_parameter_shadows_captured_environment(self):
        program = let("x", num(10), call(lam(["x"], var("x")), [num(99)]))
        self.assertEqual(eval_reference(program), 99)

    def test_higher_order_application(self):
        program = call(call(lam(["x"], lam(["y"], add(var("x"), var("y")))),
                            [num(40)]), [num(2)])
        self.assertEqual(eval_reference(program), 42)

    def test_argument_evaluated_in_caller_scope(self):
        program = let("x", num(1),
                      add(call(lam(["x"], var("x")), [num(50)]), var("x")))
        self.assertEqual(eval_reference(program), 51)


class MetamorphicTests(unittest.TestCase):
    def test_dead_branch_is_not_evaluated(self):
        self.assertEqual(eval_reference(if_(num(0), div(num(1), num(0)),
                                            num(99))), 99)
        self.assertEqual(eval_reference(if_(num(0), var("undefined"), num(99))),
                         99)
        self.assertEqual(eval_reference(if_(num(1), num(99),
                                            div(num(1), num(0)))), 99)
        self.assertEqual(eval_reference(if_(num(1), num(99),
                                            var("undefined"))), 99)

    def test_unused_let_binding_does_not_change_result(self):
        program = let("x", num(1), add(var("x"), num(2)))
        self.assertEqual(eval_reference(let("unused_a", num(7), program)),
                         eval_reference(program))
        self.assertEqual(
            eval_reference(let("f", lam(["q"], num(1)), program)),
            eval_reference(program))

    def test_alpha_renaming_preserves_value(self):
        programs = [
            let("x", num(1), add(var("x"), num(2))),
            let("x", num(1), let("x", add(var("x"), num(1)), var("x"))),
            let("x", num(10),
                let("f", lam([], var("x")),
                    let("x", num(20), call(var("f"), [])))),
            call(lam(["a", "b"], add(var("a"), var("b"))),
                 [num(30), num(12)]),
            let("f", lam(["x"], mul(var("x"), num(2))),
                call(var("f"), [num(21)])),
        ]
        for program in programs:
            with self.subTest(program=program):
                mapping = {name: f"alpha_{name}" for name in _binding_names(program)}
                self.assertEqual(eval_reference(_rename(program, mapping)),
                                 eval_reference(program))

    def test_generated_programs_are_alpha_rename_and_let_invariant(self):
        rng = random.Random(4242)
        generator = _Generator(rng)
        for _ in range(60):
            program = generator.expr([], 3)
            expected = eval_reference(program)
            mapping = {name: f"renamed_{name}"
                       for name in _binding_names(program)}
            renamed = _rename(program, mapping)
            self.assertEqual(eval_reference(renamed), expected)
            wrapped = let("unused_zz", num(7), program)
            self.assertEqual(eval_reference(wrapped), expected)


class ContractErrorTests(unittest.TestCase):
    def assert_reference_error(self, node):
        with self.assertRaises(ValueError):
            eval_reference(node)

    def test_undefined_variable(self):
        self.assert_reference_error(var("nope"))

    def test_division_by_zero(self):
        self.assert_reference_error(div(num(5), num(0)))

    def test_call_non_closure(self):
        self.assert_reference_error(call(num(3), [num(1)]))

    def test_arity_mismatch_too_many(self):
        self.assert_reference_error(call(lam(["a"], var("a")),
                                         [num(1), num(2)]))

    def test_arity_mismatch_too_few(self):
        self.assert_reference_error(call(lam(["a", "b"], var("a")), [num(1)]))

    def test_boolean_is_not_an_integer(self):
        self.assert_reference_error(num(True))

    def test_float_is_not_an_integer(self):
        self.assert_reference_error(num(1.5))

    def test_string_is_not_an_integer(self):
        self.assert_reference_error(num("3"))

    def test_num_missing_value(self):
        self.assert_reference_error({"type": "num"})

    def test_num_extra_field(self):
        self.assert_reference_error({"type": "num", "value": 1, "extra": 2})

    def test_node_not_object(self):
        self.assert_reference_error(["num", 1])

    def test_type_not_string(self):
        self.assert_reference_error({"type": 1})

    def test_unknown_type(self):
        self.assert_reference_error({"type": "frobnicate"})

    def test_var_name_not_string(self):
        self.assert_reference_error(var(3))

    def test_let_name_not_string(self):
        self.assert_reference_error(let(3, num(1), num(2)))

    def test_params_not_list(self):
        self.assert_reference_error(lam("x", num(1)))

    def test_param_not_string(self):
        self.assert_reference_error(lam([1], num(1)))

    def test_args_not_list(self):
        self.assert_reference_error(call(lam([], num(1)), {}))

    def test_malformed_nested_operand(self):
        self.assert_reference_error(add(num(1), {"type": "num"}))

    def test_malformed_dead_branch_rejected_before_evaluation(self):
        self.assert_reference_error(
            if_(num(0), {"type": "num"}, num(1)))
        self.assert_reference_error(
            if_(num(1), {"type": "num"}, num(0)))

    def test_closure_in_arithmetic(self):
        self.assert_reference_error(add(lam([], num(1)), num(2)))

    def test_closure_as_condition(self):
        self.assert_reference_error(if_(lam([], num(1)), num(1), num(0)))

    def test_closure_as_top_level_result(self):
        self.assert_reference_error(lam([], num(1)))

    def test_closure_as_operand_of_negation(self):
        self.assert_reference_error(neg(lam([], num(1))))


if __name__ == "__main__":
    unittest.main()
