#!/usr/bin/env python3
"""Hidden grader for cronlog.

Deterministic concurrency checks: the grader holds real flock locks on
events.lock and verifies the CLI blocks, times out, or proceeds according to
SPEC.md. Plus parallel load tests for lost updates.
"""

import fcntl
import json
import subprocess
import sys
import tempfile
import time
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
        self.store = tmp / "store"
        self.store.mkdir(parents=True, exist_ok=True)
        self.events = self.store / "events.json"
        self.lock = self.store / "events.lock"

    def run(self, *args, timeout=30):
        proc = subprocess.run(
            [sys.executable, "-m", "cronlog", "--store", str(self.store), *args],
            cwd=self.workspace, capture_output=True, text=True, timeout=timeout,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise AssertionError(
                f"non-json stdout rc={proc.returncode}: {proc.stdout!r} "
                f"stderr={proc.stderr[-200:]!r}")
        return proc.returncode, payload, proc

    def spawn(self, *args):
        return subprocess.Popen(
            [sys.executable, "-m", "cronlog", "--store", str(self.store), *args],
            cwd=self.workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True)

    def hold(self, shared=False):
        fd = open(self.lock, "a+")
        fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX))
        return fd

    def load(self):
        if not self.events.exists():
            return {"events": []}
        return json.loads(self.events.read_text())


def check(name, cond, detail):
    if not cond:
        raise AssertionError(detail)


@case("add_waits_for_exclusive_lock_then_succeeds")
def add_waits(ctx):
    fd = ctx.hold()
    try:
        proc = ctx.spawn("add", "blocked", "--lock-timeout", "10")
        time.sleep(1.0)
        check("still waiting while lock held",
              proc.poll() is None,
              "process finished while lock was held")
        fcntl.flock(fd, fcntl.LOCK_UN)
        out, err = proc.communicate(timeout=20)
        check("rc", proc.returncode == 0, f"rc={proc.returncode} out={out!r} err={err[-200:]!r}")
        payload = json.loads(out)
        check("event written", payload.get("name") == "blocked", f"payload={payload}")
        data = ctx.load()
        check("event persisted", len(data["events"]) == 1, f"events={data}")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


@case("add_times_out_when_locked")
def add_timeout(ctx):
    before = "before"
    ctx.events.write_text(json.dumps({"events": [{"id": 1, "name": before, "ts": "2026-01-01T00:00:00Z"}]}))
    snapshot = ctx.events.read_bytes()
    fd = ctx.hold()
    try:
        start = time.monotonic()
        rc, payload, _ = ctx.run("add", "x", "--lock-timeout", "1.5", timeout=30)
        elapsed = time.monotonic() - start
        check("rc", rc == 1, f"rc={rc} payload={payload}")
        check("error payload", "error" in payload, f"payload={payload}")
        check("waited for timeout", elapsed >= 1.0, f"gave up after {elapsed:.2f}s")
        check("store untouched", ctx.events.read_bytes() == snapshot, "store changed")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


@case("add_times_out_immediately_with_zero_timeout")
def add_timeout_zero(ctx):
    fd = ctx.hold()
    try:
        start = time.monotonic()
        rc, payload, _ = ctx.run("add", "x", "--lock-timeout", "0", timeout=15)
        elapsed = time.monotonic() - start
        check("rc", rc == 1, f"rc={rc} payload={payload}")
        check("error payload", "error" in payload, f"payload={payload}")
        check("no long wait", elapsed < 3.0, f"took {elapsed:.2f}s")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


@case("list_waits_for_writer_lock")
def list_waits(ctx):
    fd = ctx.hold()
    try:
        start = time.monotonic()
        rc, payload, _ = ctx.run("list", "--lock-timeout", "1.5", timeout=30)
        elapsed = time.monotonic() - start
        check("rc", rc == 1, f"rc={rc} payload={payload}")
        check("waited for timeout", elapsed >= 1.0, f"gave up after {elapsed:.2f}s")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


@case("readers_share_the_lock")
def readers_share(ctx):
    ctx.run("add", "a")
    fd = ctx.hold(shared=True)
    try:
        rc, payload, _ = ctx.run("list", "--lock-timeout", "2", timeout=20)
        check("shared lock compatible", rc == 0, f"rc={rc} payload={payload}")
        check("events visible", len(payload.get("events", [])) == 1, f"{payload}")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


@case("parallel_adds_lose_nothing")
def parallel_adds(ctx):
    rounds, writers = 4, 15
    expected = 0
    for r in range(rounds):
        procs = [ctx.spawn("add", f"job-{r}-{i}") for i in range(writers)]
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            check("writer rc", proc.returncode == 0,
                  f"rc={proc.returncode} out={out!r} err={err[-200:]!r}")
        expected += writers
        data = ctx.load()
        names = sorted(e["name"] for e in data["events"])
        check(f"round {r} count", len(data["events"]) == expected,
              f"expected {expected} events, got {len(data['events'])}")
        ids = [e["id"] for e in data["events"]]
        check(f"round {r} unique ids", len(set(ids)) == len(ids),
              f"duplicate ids: {sorted(ids)}")
    check("all names present",
          sorted(e["name"] for e in ctx.load()["events"]) ==
          sorted(f"job-{r}-{i}" for r in range(rounds) for i in range(writers)),
          "names lost or duplicated")


@case("parallel_readers_and_writers")
def parallel_mixed(ctx):
    writers, readers = 10, 10
    procs = [ctx.spawn("add", f"mix-{i}") for i in range(writers)]
    procs += [ctx.spawn("list") for _ in range(readers)]
    reader_outputs = []
    for idx, proc in enumerate(procs):
        out, err = proc.communicate(timeout=60)
        check(f"proc {idx} rc", proc.returncode == 0,
              f"rc={proc.returncode} out={out!r} err={err[-200:]!r}")
        if idx >= writers:
            try:
                payload = json.loads(out)
            except json.JSONDecodeError as exc:
                raise AssertionError(f"reader saw invalid json: {exc} {out[:200]!r}")
            check(f"reader {idx} shape", "events" in payload, f"{payload}")
            reader_outputs.append(payload)
    data = ctx.load()
    check("no lost writes", len(data["events"]) == writers,
          f"expected {writers}, got {len(data['events'])}")


@case("timeout_option_validation")
def timeout_validation(ctx):
    rc, payload, _ = ctx.run("--lock-timeout", "-1", "list")
    check("negative rejected", rc == 1 and "error" in payload, f"{rc} {payload}")
    rc, payload, _ = ctx.run("--lock-timeout", "abc", "list")
    check("non-numeric rejected", rc == 1 and "error" in payload, f"{rc} {payload}")


@case("error_paths_release_lock")
def error_release(ctx):
    ctx.events.write_text("{corrupted")
    rc, payload, _ = ctx.run("list")
    check("corrupted rc", rc == 1 and "error" in payload, f"{rc} {payload}")
    fd = open(ctx.lock, "a+")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise AssertionError("lock still held after an error path")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


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
    detail = "concurrency contract satisfied" if passed else "; ".join(
        f"{r['case']}: {r['detail']}" for r in results if not r["passed"])
    result = {"passed": passed, "score": round(score, 3), "detail": detail,
              "cases": results}
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
