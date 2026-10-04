#!/usr/bin/env python3
"""Schedule jobs on one machine. See SPEC.md for the contract."""

import json
import sys
from itertools import permutations
from pathlib import Path


def validate(payload: dict) -> tuple:
    if not isinstance(payload, dict):
        raise ValueError("input must be an object")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("jobs must be a non-empty list")
    ids = []
    deps = {}
    dur = {}
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
        if type(d) is not int or d <= 0:
            raise ValueError(f"duration must be positive (job {jid})")
        if type(dl) is not int or dl <= 0:
            raise ValueError(f"deadline must be positive (job {jid})")
        dep = job.get("depends", [])
        if (not isinstance(dep, list)
                or not all(isinstance(target, str) for target in dep)):
            raise ValueError(f"depends must be a list (job {jid})")
        deps[jid] = list(dep)
        dur[jid] = d
    known = set(ids)
    for jid in ids:
        for target in deps[jid]:
            if target not in known:
                raise ValueError(f"unknown dependency {target}")
            if target == jid:
                raise ValueError(f"job {jid} depends on itself")
    # cycle detection
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
    return ids, deps, dur


def feasible(order: list, deps: dict) -> bool:
    seen = set()
    for jid in order:
        for target in deps[jid]:
            if target not in seen:
                return False
        seen.add(jid)
    return True


def late_count(order: list, deps: dict, dur: dict, deadline: dict) -> int:
    elapsed = 0
    late = 0
    for jid in order:
        elapsed += dur[jid]
        if elapsed > deadline[jid]:
            late += 1
    return late


def schedule(payload: dict) -> dict:
    ids, deps, dur = validate(payload)
    deadline = {j["id"]: j["deadline"] for j in payload["jobs"]}

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


def main() -> None:
    if len(sys.argv) != 3:
        print("error", file=sys.stderr)
        sys.exit(1)
    try:
        payload = json.loads(Path(sys.argv[1]).read_text())
        result = schedule(payload)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("error", file=sys.stderr)
        sys.exit(1)
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
