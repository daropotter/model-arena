#!/usr/bin/env python3
"""Hidden grader for the tasklog task.

Checks the full SPEC.md contract: commands, snooze semantics, store migration
v1 -> v2, summary fields, robustness.
"""

import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


class Ctx:
    def __init__(self, workspace: Path, tmp: Path):
        self.workspace = workspace
        self.store = tmp / "store.json"

    def run(self, *args, store=None):
        store = store or self.store
        proc = subprocess.run(
            [sys.executable, "-m", "tasklog", "--store", str(store), *args],
            cwd=self.workspace, capture_output=True, text=True, timeout=60,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise AssertionError(
                f"non-json stdout rc={proc.returncode}: {proc.stdout!r} "
                f"stderr={proc.stderr[-200:]!r}")
        if proc.returncode == 0 and isinstance(payload, dict) and "error" in payload:
            raise AssertionError(f"unexpected error payload: {payload}")
        return proc.returncode, payload


def check(name, cond, detail):
    if not cond:
        raise AssertionError(detail)


@case("snooze_due_pushes_forward")
def snooze_due(ctx):
    today = datetime.now(timezone.utc).date()
    due = (today + timedelta(days=10)).isoformat()
    rc, task = ctx.run("add", "push me", "--due", due)
    check("add", rc == 0, f"rc={rc}")
    time.sleep(1.1)  # timestamps have second resolution
    t1 = ctx.run("snooze", str(task["id"]))[1]
    check("snooze1", t1["snoozes"] == 1, f"snoozes={t1.get('snoozes')}")
    check("snooze1 due", t1["due"] == (today + timedelta(days=11)).isoformat(),
          f"due={t1.get('due')}")
    t2 = ctx.run("snooze", str(task["id"]))[1]
    check("snooze2", t2["snoozes"] == 2, f"snoozes={t2.get('snoozes')}")
    check("snooze2 due", t2["due"] == (today + timedelta(days=13)).isoformat(),
          f"due={t2.get('due')}")
    t3 = ctx.run("snooze", str(task["id"]))[1]
    check("snooze3 due", t3["due"] == (today + timedelta(days=16)).isoformat(),
          f"due={t3.get('due')}")
    check("updated_at changed", t3["updated_at"] != task["updated_at"],
          "updated_at did not change")


@case("snooze_without_due")
def snooze_no_due(ctx):
    _, task = ctx.run("add", "no due")
    t1 = ctx.run("snooze", str(task["id"]))[1]
    check("due stays null", t1["due"] is None, f"due={t1['due']!r}")
    check("snoozes", t1["snoozes"] == 1, f"snoozes={t1['snoozes']}")


@case("snooze_unknown_id")
def snooze_bad_id(ctx):
    rc, payload = ctx.run("snooze", "999")
    check("rc", rc == 1, f"rc={rc}")
    check("error", "error" in payload, f"payload={payload}")


@case("migration_v1_to_v2")
def migration(ctx):
    v1 = {
        "tasks": [
            {"id": 1, "title": "old one", "status": "open",
             "tags": ["legacy"], "due": "2026-01-01"},
            {"id": 7, "title": "old two", "status": "done", "tags": [],
             "due": None, "custom_field": {"keep": True}},
        ]
    }
    ctx.store.write_text(json.dumps(v1))
    rc, tasks = ctx.run("list")
    check("list rc", rc == 0, f"rc={rc}")
    on_disk = json.loads(ctx.store.read_text())
    check("version", on_disk.get("version") == 2, f"version={on_disk.get('version')}")
    for t in on_disk["tasks"]:
        check(f"priority {t['id']}", t.get("priority") == 3, f"priority={t.get('priority')}")
        check(f"snoozes {t['id']}", t.get("snoozes") == 0, f"snoozes={t.get('snoozes')}")
        check(f"created_at {t['id']}", t.get("created_at"), "missing created_at")
        check(f"updated_at {t['id']}", t.get("updated_at"), "missing updated_at")
    kept = [t for t in on_disk["tasks"] if t["id"] == 7][0]
    check("extra field kept", kept.get("custom_field") == {"keep": True},
          f"custom_field={kept.get('custom_field')!r}")
    check("title preserved", kept["title"] == "old two", "title changed")
    check("oldest id preserved", tasks[0]["id"] == 1, "ordering/id changed")


@case("v2_not_remigrated")
def v2_stable(ctx):
    stamp = "2020-05-05T05:05:05Z"
    v2 = {
        "version": 2,
        "tasks": [
            {"id": 1, "title": "x", "status": "open", "tags": [], "due": None,
             "priority": 5, "snoozes": 4, "created_at": stamp, "updated_at": stamp}
        ],
    }
    ctx.store.write_text(json.dumps(v2))
    ctx.run("list")
    on_disk = json.loads(ctx.store.read_text())
    t = on_disk["tasks"][0]
    check("priority kept", t["priority"] == 5, f"priority={t['priority']}")
    check("snoozes kept", t["snoozes"] == 4, f"snoozes={t['snoozes']}")
    check("created_at kept", t["created_at"] == stamp, f"created_at={t['created_at']}")
    ctx.run("add", "new")
    on_disk = json.loads(ctx.store.read_text())
    t = [x for x in on_disk["tasks"] if x["id"] == 1][0]
    check("created_at still kept", t["created_at"] == stamp, "created_at rewritten")


@case("summary_fields")
def summary(ctx):
    today = datetime.now(timezone.utc).date()
    ctx.run("add", "overdue", "--due", (today - timedelta(days=2)).isoformat(), "--priority", "1")
    _, done_task = ctx.run("add", "done overdue", "--due", (today - timedelta(days=3)).isoformat(), "--priority", "2")
    ctx.run("add", "future", "--due", (today + timedelta(days=3)).isoformat(), "--priority", "5")
    ctx.run("add", "no due", "--priority", "5")
    ctx.run("done", str(done_task["id"]))
    rc, s = ctx.run("summary")
    check("rc", rc == 0, f"rc={rc}")
    check("total", s["total"] == 4, f"total={s['total']}")
    check("open", s["open"] == 3, f"open={s['open']}")
    check("done", s["done"] == 1, f"done={s['done']}")
    check("with_due", s["with_due"] == 3, f"with_due={s['with_due']}")
    check("overdue counts only open", s["overdue"] == 1, f"overdue={s['overdue']}")
    check("by_priority all keys",
          s.get("by_priority") == {"1": 1, "2": 1, "3": 0, "4": 0, "5": 2},
          f"by_priority={s.get('by_priority')}")


@case("add_validation")
def add_validation(ctx):
    rc, payload = ctx.run("add", "bad priority", "--priority", "9")
    check("priority 9", rc == 1 and "error" in payload, f"{rc} {payload}")
    rc, payload = ctx.run("add", "bad priority", "--priority", "x")
    check("priority x", rc == 1 and "error" in payload, f"{rc} {payload}")
    rc, payload = ctx.run("add", "bad due", "--due", "2026-13-40")
    check("bad due", rc == 1 and "error" in payload, f"{rc} {payload}")
    rc, payload = ctx.run("add", "bad due", "--due", "not-a-date")
    check("due text", rc == 1 and "error" in payload, f"{rc} {payload}")
    rc, payload = ctx.run("add", "no priority")
    check("default priority", payload.get("priority") == 3,
          f"priority={payload.get('priority')}")


@case("list_ordering_and_tags")
def list_tags(ctx):
    a = ctx.run("add", "a", "--tag", "x", "--tag", "y", "--tag", "x")[1]
    b = ctx.run("add", "b", "--tag", "y")[1]
    check("tag dedup", a["tags"] == ["x", "y"], f"tags={a['tags']}")
    _, tasks = ctx.run("list")
    check("sorted by id", [t["id"] for t in tasks] == sorted(t["id"] for t in tasks),
          "not sorted")
    _, filtered = ctx.run("list", "--tag", "y")
    check("tag filter", {t["id"] for t in filtered} == {a["id"], b["id"]},
          f"filtered={[t['id'] for t in filtered]}")


@case("store_robustness")
def robustness(ctx):
    ctx.store.write_text("{not json")
    rc, payload = ctx.run("list")
    check("corrupted rc", rc == 1, f"rc={rc}")
    check("corrupted error", "error" in payload, f"{payload}")
    check("corrupted file untouched", ctx.store.read_text() == "{not json",
          "corrupted store was rewritten")
    ctx.store.write_text(json.dumps({"nope": 1}))
    rc, payload = ctx.run("list")
    check("no tasks list rc", rc == 1 and "error" in payload, f"{rc} {payload}")


@case("store_flag_position")
def flag_position(ctx):
    store = ctx.store
    proc = subprocess.run(
        [sys.executable, "-m", "tasklog", "add", "flag after", "--store", str(store)],
        cwd=ctx.workspace, capture_output=True, text=True, timeout=60,
    )
    check("flag after command", proc.returncode == 0, proc.stdout + proc.stderr)
    check("written", store.exists(), "store not written")


@case("done_is_idempotent")
def done_idempotent(ctx):
    _, task = ctx.run("add", "x")
    first = ctx.run("done", str(task["id"]))[1]
    second = ctx.run("done", str(task["id"]))[1]
    check("status", second["status"] == "done", f"status={second['status']}")
    check("updated_at changes", second["updated_at"] is not None, "no updated_at")
    check("still exists", first["id"] == second["id"], "id changed")


def main(workspace_arg: str, out_arg: str):
    workspace = Path(workspace_arg)
    out_path = Path(out_arg)
    results = []
    for name, fn in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = Ctx(workspace, Path(tmp))
            try:
                fn(ctx)
                results.append({"case": name, "passed": True, "detail": ""})
            except (AssertionError, subprocess.TimeoutExpired) as exc:
                results.append({"case": name, "passed": False, "detail": str(exc)[:300]})
            except Exception as exc:  # noqa: BLE001
                results.append({"case": name, "passed": False,
                                "detail": f"{type(exc).__name__}: {exc}"[:300]})
    passed = all(r["passed"] for r in results)
    score = sum(1 for r in results if r["passed"]) / len(results)
    detail = "all hidden cases passed" if passed else "; ".join(
        f"{r['case']}: {r['detail']}" for r in results if not r["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
