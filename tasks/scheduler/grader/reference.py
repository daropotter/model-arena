#!/usr/bin/env python3
"""Reference implementation of SPEC.md. Used only by the hidden grader."""

import json
from itertools import permutations
from pathlib import Path


def validate(payload: dict) -> list:
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("jobs must be a non-empty list")
    ids = []
    deps = {}
    dur = {}
    deadline = {}
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("job must be an object")
        jid = job.get("id")
        if not isinstance(jid, str) or not jid:
            raise ValueError("job id must be a non-empty string")
        if jid in ids:
            raise ValueError(f"duplicate id {jid}")
        ids.append(jid)
        d = job.get("duration")
        dl = job.get("deadline")
        if not isinstance(d, int) or d <= 0:
            raise ValueError(f"duration must be positive (job {jid})")
        if not isinstance(dl, int) or dl <= 0:
            raise ValueError(f"deadline must be positive (job {jid})")
        dep = job.get("depends", [])
        if not isinstance(dep, list):
            raise ValueError(f"depends must be a list (job {jid})")
        for target in dep:
            if target not in ids:
                raise ValueError(f"unknown dependency {target}")
            if target == jid:
                raise ValueError(f"job {jid} depends on itself")
        deps[jid] = list(dep)
        dur[jid] = d
        deadline[jid] = dl
    state = {jid: 0 for jid in ids}

    def dfs(jid):
        state[jid] = 1
        for target in deps[jid]:
            if state[target] == 1:
                raise ValueError(f"dependency cycle at {jid}")
            if state[target] == 0:
                dfs(target)
        state[jid] = 2

    for jid in ids:
        if state[jid] == 0:
            dfs(jid)
    return ids, deps, dur, deadline


def feasible(order, deps):
    seen = set()
    for jid in order:
        for target in deps[jid]:
            if target not in seen:
                return False
        seen.add(jid)
    return True


def late_count(order, deps, dur, deadline):
    finish = {}
    late = 0
    for jid in order:
        start = max([0] + [finish[t] for t in deps[jid]])
        end = start + dur[jid]
        finish[jid] = end
        if end > deadline[jid]:
            late += 1
    return late


def schedule_reference(payload: dict) -> dict:
    ids, deps, dur, deadline = validate(payload)
    best_order = None
    best_late = None
    for perm in permutations(ids):
        if not feasible(perm, deps):
            continue
        late = late_count(perm, deps, dur, deadline)
        if best_late is None or late < best_late:
            best_late = late
            best_order = perm
    return {"order": list(best_order), "late": best_late}
