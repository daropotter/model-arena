"""Independent oracle tests for the scheduler task (T1).

The implementation under test is the hidden reference.  This module does NOT
import the shipped starter or solution.  It re-implements feasibility and the
cumulative single-machine clock from scratch, brute-forces every permutation
of jobs to find the true minimum number of late jobs, and checks that
``schedule_reference`` agrees with that minimum on explicit and randomly
generated DAG instances.
"""

import importlib.util
import itertools
import random
import sys
import unittest

from tests.support import ROOT

_SCHEDULER_GRADER = ROOT / "tasks" / "scheduler" / "grader"
sys.path.insert(0, str(_SCHEDULER_GRADER))

_spec = importlib.util.spec_from_file_location(
    "_scheduler_reference_under_test", _SCHEDULER_GRADER / "reference.py")
_reference = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _reference
_spec.loader.exec_module(_reference)

schedule_reference = _reference.schedule_reference
validate = _reference.validate


# --- independent brute force ----------------------------------------------


def order_feasible(order, deps):
    seen = set()
    for jid in order:
        for target in deps[jid]:
            if target not in seen:
                return False
        seen.add(jid)
    return True


def independent_late(order, duration, deadline):
    """Cumulative single-machine clock, written from scratch."""
    elapsed = 0
    late = 0
    for jid in order:
        elapsed += duration[jid]
        if elapsed > deadline[jid]:
            late += 1
    return late


def instance_data(payload):
    jobs = payload["jobs"]
    jids = [job["id"] for job in jobs]
    duration = {job["id"]: job["duration"] for job in jobs}
    deadline = {job["id"]: job["deadline"] for job in jobs}
    deps = {job["id"]: list(job.get("depends", [])) for job in jobs}
    return jids, duration, deadline, deps


def brute_min_late(payload):
    jids, duration, deadline, deps = instance_data(payload)
    best = None
    for order in itertools.permutations(jids):
        if not order_feasible(order, deps):
            continue
        late = independent_late(order, duration, deadline)
        if best is None or late < best:
            best = late
    return best


def check_instance(test_case, payload):
    jids, duration, deadline, deps = instance_data(payload)
    expected = brute_min_late(payload)
    result = schedule_reference(payload)
    context = f"payload={payload!r}"

    order = result["order"]
    test_case.assertEqual(sorted(order), sorted(jids),
                          "order is not a permutation: " + context)
    test_case.assertTrue(order_feasible(order, deps),
                         "reference produced an infeasible order: " + context)
    computed = independent_late(order, duration, deadline)
    test_case.assertEqual(computed, result["late"],
                          "reference reported a wrong late count: " + context)
    test_case.assertEqual(result["late"], expected,
                          "reference late count is not the minimum: " + context)


# --- explicit instances ----------------------------------------------------


def chain_jobs():
    return [
        {"id": "a", "duration": 2, "deadline": 3, "depends": []},
        {"id": "b", "duration": 2, "deadline": 5, "depends": ["a"]},
        {"id": "c", "duration": 2, "deadline": 7, "depends": ["b"]},
    ]


def wide_dag_jobs():
    return [
        {"id": "root", "duration": 1, "deadline": 4, "depends": []},
        {"id": "x", "duration": 2, "deadline": 6, "depends": ["root"]},
        {"id": "y", "duration": 3, "deadline": 7, "depends": ["root"]},
        {"id": "z", "duration": 2, "deadline": 9, "depends": ["root"]},
        {"id": "join", "duration": 1, "deadline": 10,
         "depends": ["x", "y", "z"]},
    ]


def independent_jobs():
    return [
        {"id": "j0", "duration": 3, "deadline": 2, "depends": []},
        {"id": "j1", "duration": 1, "deadline": 1, "depends": []},
        {"id": "j2", "duration": 2, "deadline": 4, "depends": []},
        {"id": "j3", "duration": 4, "deadline": 7, "depends": []},
    ]


def forward_dependency_jobs():
    return [
        {"id": "b", "duration": 2, "deadline": 5, "depends": ["a"]},
        {"id": "a", "duration": 3, "deadline": 3, "depends": []},
        {"id": "c", "duration": 1, "deadline": 9, "depends": ["b"]},
    ]


def reversed_chain_jobs():
    return [
        {"id": "c", "duration": 2, "deadline": 8, "depends": ["b"]},
        {"id": "b", "duration": 2, "deadline": 6, "depends": ["a"]},
        {"id": "a", "duration": 2, "deadline": 4, "depends": []},
    ]


def anti_greedy_jobs():
    return [
        {"id": "long", "duration": 5, "deadline": 5, "depends": []},
        {"id": "short", "duration": 1, "deadline": 2, "depends": []},
    ]


class ExplicitInstanceTests(unittest.TestCase):
    def test_chain(self):
        check_instance(self, {"jobs": chain_jobs()})

    def test_wide_dag(self):
        check_instance(self, {"jobs": wide_dag_jobs()})

    def test_independent_jobs(self):
        check_instance(self, {"jobs": independent_jobs()})

    def test_forward_dependency(self):
        check_instance(self, {"jobs": forward_dependency_jobs()})

    def test_reversed_chain(self):
        check_instance(self, {"jobs": reversed_chain_jobs()})

    def test_anti_greedy_regression(self):
        payload = {"jobs": anti_greedy_jobs()}
        self.assertEqual(brute_min_late(payload), 1,
                         "brute force must find exactly one late job")
        check_instance(self, payload)
        self.assertEqual(schedule_reference(payload)["late"], 1)

    def test_end_of_array_dependencies_accepted_by_validate(self):
        payloads = [
            {"jobs": forward_dependency_jobs()},
            {"jobs": reversed_chain_jobs()},
            {"jobs": [
                {"id": "last_dep", "duration": 2, "deadline": 9,
                 "depends": ["tail"]},
                {"id": "mid", "duration": 3, "deadline": 8, "depends": []},
                {"id": "tail", "duration": 1, "deadline": 4,
                 "depends": ["mid"]},
            ]},
        ]
        for payload in payloads:
            context = f"payload={payload!r}"
            try:
                validate(payload)
            except ValueError as exc:
                self.fail(
                    "validate rejected an end-of-array dependency: "
                    f"{exc}; {context}")

    def test_validate_rejects_broken_graphs(self):
        broken = {
            "cycle": {"jobs": [
                {"id": "a", "duration": 1, "deadline": 3, "depends": ["b"]},
                {"id": "b", "duration": 1, "deadline": 3, "depends": ["a"]},
            ]},
            "self_dep": {"jobs": [
                {"id": "a", "duration": 1, "deadline": 3, "depends": ["a"]},
            ]},
            "unknown_dep": {"jobs": [
                {"id": "a", "duration": 1, "deadline": 3,
                 "depends": ["ghost"]},
            ]},
            "duplicate_id": {"jobs": [
                {"id": "a", "duration": 1, "deadline": 3, "depends": []},
                {"id": "a", "duration": 1, "deadline": 3, "depends": []},
            ]},
        }
        for name, payload in broken.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError, msg=f"case={name!r}"):
                    validate(payload)


# --- deterministic random instances ---------------------------------------


def random_instances(count=60, seed=20261001):
    rng = random.Random(seed)
    instances = []
    for _ in range(count):
        size = rng.randint(2, 6)
        topo = [f"j{i}" for i in range(size)]
        rng.shuffle(topo)
        deps = {jid: [] for jid in topo}
        for i in range(size):
            for j in range(i + 1, size):
                if rng.random() < 0.35:
                    deps[topo[j]].append(topo[i])
        input_order = list(topo)
        rng.shuffle(input_order)
        jobs = [
            {
                "id": jid,
                "duration": rng.randint(1, 4),
                "deadline": rng.randint(1, 20),
                "depends": deps[jid],
            }
            for jid in input_order
        ]
        instances.append({"jobs": jobs})
    return instances


def has_forward_reference(payload):
    position = {job["id"]: index
                for index, job in enumerate(payload["jobs"])}
    return any(
        position[target] > position[job["id"]]
        for job in payload["jobs"]
        for target in job["depends"])


class RandomInstanceTests(unittest.TestCase):
    def test_reference_matches_brute_force_on_random_dags(self):
        instances = random_instances()
        for index, payload in enumerate(instances):
            with self.subTest(instance=index):
                check_instance(self, payload)

    def test_random_corpus_exercises_forward_references(self):
        instances = random_instances()
        forward = [p for p in instances if has_forward_reference(p)]
        self.assertTrue(
            forward,
            "generator produced no instance whose dependency appears later "
            "in the input array")
        for payload in forward:
            self.assertIsNotNone(brute_min_late(payload))

    def test_random_corpus_covers_sizes_up_to_six(self):
        sizes = {len(payload["jobs"]) for payload in random_instances()}
        self.assertEqual(sizes, {2, 3, 4, 5, 6})


if __name__ == "__main__":
    unittest.main()
