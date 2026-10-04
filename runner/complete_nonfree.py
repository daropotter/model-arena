#!/usr/bin/env python3
"""Resume non-free-named models to current v2 coverage without repeating FAILs.

The default is a read-only queue preview. --run executes it; --background
starts a durable user service. Results, status and blockers stay in results/.
"""

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arena
import reporting
import roster
import run_lock

ROOT = arena.ROOT
SECRETS = ("OPENCODE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY")
PRIORITY = [
    "ollama/qwen3.8-35b-a3b-moe-Q3_K_M", "opencode/big-pickle",
    "ollama/qwen3.5-64k:latest", "ollama/qwen3.5-32k:latest",
    "ollama/gemma4-200k:latest", "ollama/qwen3.8-35b-a3b-moe-IQ3_M",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def nonfree(model):
    return isinstance(model, str) and "free" not in model.lower()


def task_hashes(tasks_dir):
    return {
        task["name"]: {
            "task_digest": arena.tree_digest(tasks_dir / task["name"]),
            "starter_digest": arena.tree_digest(tasks_dir / task["name"] / "starter"),
            "grader_digest": arena.tree_digest(tasks_dir / task["name"] / "grader"),
            "prompt_digest": arena.file_digest(tasks_dir / task["name"] / "prompt.md"),
        }
        for task in arena.list_tasks(tasks_dir) if task["name"] != "smoke"
    }


def current(record, hashes):
    if not reporting.is_comparable(record):
        return False
    provenance = record["provenance"]
    expected = hashes.get(record["task"])
    return bool(expected and all(provenance.get(k) == v for k, v in expected.items()))


def build_plan(records, hashes, extra_models=()):
    grouped = defaultdict(list)
    for record in records:
        if nonfree(record["model"]):
            grouped[record["model"]].append(record)
    for model in extra_models:
        if nonfree(model):
            grouped.setdefault(model, [])
    plans = []
    for model, records in grouped.items():
        valid = {r["task"] for r in records if reporting.is_valid(r)}
        done = {r["task"] for r in records if current(r, hashes)}
        pending = sorted(set(hashes) - done, key=lambda t: (t in valid, t))
        verdict = roster.decide(model, records, [])[0] if records else "NEW"
        plans.append({"model": model, "tasks": pending,
                      "missing_coverage": sorted(set(hashes) - valid),
                      "current": len(done), "qualify": verdict != "QUALIFIED"
                      and bool(pending)})
    return sorted(plans, key=lambda p: (
        p["qualify"], PRIORITY.index(p["model"]) if p["model"] in PRIORITY
        else len(PRIORITY), p["model"]))


def grader_only(records, hashes):
    pairs = []
    for record in records:
        if not nonfree(record["model"]) or not reporting.is_comparable(record):
            continue
        expected = hashes.get(record["task"])
        provenance = record["provenance"]
        if (expected and not current(record, hashes)
                and all(provenance.get(k) == expected[k]
                        for k in ("starter_digest", "prompt_digest"))
                and provenance.get("grader_digest") != expected["grader_digest"]):
            pairs.append((record["model"], record["task"]))
    return pairs


def prescreen_models():
    models = set()
    catalog = Path(os.environ.get("ARENA_CATALOG_ROOT", ROOT))
    for path in catalog.glob("results*/prescreen-results.jsonl"):
        for line in path.read_text().splitlines():
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(record, dict) and nonfree(record.get("model")):
                models.add(record["model"])
    return models


def ollama_json(endpoint, payload=None, timeout=30):
    request = urllib.request.Request(
        "http://127.0.0.1:11434" + endpoint,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def model_options(model, records):
    modern = [r for r in records if r["model"] == model
              and reporting.is_comparable(r)]
    if modern:
        latest = max(modern, key=lambda r: (r.get("finished_at") or "",
                                           r.get("_record_mtime", 0)))
        provenance = latest["provenance"]
        return bool(provenance.get("no_think")), provenance.get("model_options", "")
    name = model.removeprefix("ollama/")
    return model.startswith("ollama/") and name.startswith(
        ("qwen", "qwq", "deepseek-r1", "gpt-oss")), ""


class RedactingWriter:
    """Buffer complete lines so a secret split between writes is still masked."""

    def __init__(self, stream, secrets):
        self.stream = stream
        self.secrets = [s for s in secrets if s]
        self.buffer = ""

    def redact(self, text):
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        return text

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.stream.write(self.redact(line) + "\n")
        return len(text)

    def flush(self):
        # Keep partial lines buffered: flush must not reveal a secret prefix.
        self.stream.flush()

    def finish(self):
        if self.buffer:
            self.stream.write(self.redact(self.buffer))
            self.buffer = ""
        self.stream.flush()


def background(args):
    state_dir = args.results / "nonfree-completion"
    state_dir.mkdir(parents=True, exist_ok=True)
    log = state_dir / "controller.log"
    log.touch(mode=0o600, exist_ok=True)
    log.chmod(0o600)
    # Freeze both the agent-facing inputs and the runner before starting a
    # long sweep. Working-tree documentation may be edited independently.
    snapshot = state_dir / ("suite-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                            + "-" + uuid4().hex[:6])
    sources = {"runner": ROOT / "runner", "tasks": args.tasks,
               "docker": ROOT / "docker"}
    digests = {name: arena.tree_digest(source) for name, source in sources.items()}
    snapshot.mkdir()
    for name in digests:
        shutil.copytree(sources[name], snapshot / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    if any(arena.tree_digest(sources[name]) != digest
           or arena.tree_digest(snapshot / name) != digest
           for name, digest in digests.items()):
        raise RuntimeError("suite changed while freezing; retry after edits finish")
    atomic_json(state_dir / "manifest.json", {
        "created_at": now(), "source": str(ROOT), "snapshot": str(snapshot),
        "digests": digests, "task_hashes": task_hashes(snapshot / "tasks"),
        "include_prescreen": args.include_prescreen,
        "filter": "identifier does not contain free"})
    os.environ.setdefault("ARENA_LOCK_ROOT", str(ROOT))
    os.environ.setdefault("ARENA_CATALOG_ROOT", str(ROOT))
    unit = "model-arena-nonfree"
    command = ["systemd-run", "--user", "--unit=" + unit,
               "--description=Complete model-arena non-free-named runs",
               "--working-directory=" + str(ROOT), "--expand-environment=no",
               "--property=StandardOutput=append:" + str(log),
               "--property=StandardError=append:" + str(log),
               "--property=TimeoutStopSec=45s"]
    environment_names = set(SECRETS) | {"PATH"} | {
        name for name in os.environ if name.startswith("ARENA_")}
    for name in sorted(environment_names):
        if name in os.environ:
            command.append("--setenv=" + name)
    command += [sys.executable, str(snapshot / "runner/complete_nonfree.py"), "--run",
                "--results", str(args.results), "--tasks", str(snapshot / "tasks")]
    if args.include_prescreen:
        command.append("--include-prescreen")
    if args.retry_blocked:
        command.append("--retry-blocked")
    subprocess.run(command, check=True)
    print(f"Service: {unit}.service; progress: {state_dir / 'status.json'}")


def execute(args, hashes, records, plans):
    state_dir = args.results / "nonfree-completion"
    state = {"started_at": now(), "updated_at": now(), "pid": os.getpid(),
             "state": "starting", "active": None, "attempts": [],
             "blocked": {}, "models": plans}
    path = state_dir / "status.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    state["attempts"] = old.get("attempts", [])
    state["blocked"] = {} if args.retry_blocked else old.get("blocked", {})
    runner_hash = arena.tree_digest(ROOT / "runner")
    docker_hash = arena.tree_digest(ROOT / "docker")

    def update(**values):
        state.update(values)
        state["updated_at"] = now()
        atomic_json(path, state)

    def block(model, reason):
        state["blocked"][model] = {"reason": reason, "at": now()}
        print(f"[completion] BLOCKED {model}: {reason}", flush=True)
        update(active=None)

    def stable():
        return (arena.tree_digest(ROOT / "runner") == runner_hash
                and arena.tree_digest(ROOT / "docker") == docker_hash
                and task_hashes(args.tasks) == hashes)

    update(state="regrading")
    for task in sorted({task for _, task in grader_only(records, hashes)}):
        models = sorted({model for model, t in grader_only(records, hashes) if t == task})
        command = [sys.executable, str(ROOT / "runner/regrade.py"), "--results",
                   str(args.results), "--tasks", str(args.tasks), "--task", task,
                   "--models", *models, "--no-reports"]
        result = subprocess.run(command, capture_output=True, text=True)
        print(result.stdout, end="")
        if result.returncode:
            raise RuntimeError("targeted regrade failed")
    records = reporting.load_records([args.results])
    plans = build_plan(records, hashes,
                       prescreen_models() if args.include_prescreen else ())
    update(models=plans, state="running")
    providers_blocked = set()
    previous_local = None
    initialized_network = False
    qualified = set()
    batch = datetime.now().strftime("%Y%m%d-%H%M%S") + "-nonfree-" + uuid4().hex[:6]

    # Fill previously absent pairs first, then replace legacy records. Failed
    # but valid v2 attempts leave the queue just like successful attempts.
    for phase in ("coverage", "v2"):
        for plan in plans:
            model = plan["model"]
            todo = [t for t in plan["tasks"]
                    if phase == "v2" or t in plan["missing_coverage"]]
            if not todo:
                continue
            if model in state["blocked"]:
                continue
            provider = model.split("/")[0]
            if provider in providers_blocked:
                block(model, "provider stopped after an infrastructure failure")
                continue
            update(active={"model": model, "phase": phase, "state": "waiting_for_lock"})
            with run_lock.exclusive(ROOT):
                if not stable():
                    update(state="stopped", active=None,
                           reason="runner, Docker scripts or task inputs changed")
                    return
                no_think, options = model_options(model, records)
                os.environ.pop("ARENA_MODEL_OPTS", None)
                os.environ.pop("ARENA_NO_THINK", None)
                if no_think:
                    os.environ["ARENA_NO_THINK"] = "1"
                if options:
                    os.environ["ARENA_MODEL_OPTS"] = options
                if model.startswith("ollama/"):
                    name = model.removeprefix("ollama/")
                    try:
                        inventory = {m["name"]: m for m in ollama_json("/api/tags")["models"]}
                        entry = inventory.get(name if ":" in name else name + ":latest")
                        if entry is None:
                            block(model, "model is not installed; original configuration unavailable")
                            continue
                        if entry["size"] > 20e9:
                            block(model, "weights exceed the existing 20 GB hardware screening limit")
                            continue
                        capabilities = ollama_json("/api/show", {"model": name}).get("capabilities", [])
                        if "tools" not in capabilities or "completion" not in capabilities:
                            block(model, "model lacks completion or tool support")
                            continue
                        if previous_local and previous_local != name:
                            ollama_json("/api/generate", {"model": previous_local, "keep_alive": 0})
                        previous_local = name
                        if not initialized_network:
                            arena.ensure_network(arena.NETWORK)
                            arena.ensure_proxy(arena.GATEWAY, arena.OLLAMA_PORT)
                            initialized_network = True
                    except Exception as exc:
                        block(model, "local inference preflight failed: " + type(exc).__name__)
                        providers_blocked.add(provider)
                        continue
                if plan["qualify"] and model not in qualified:
                    update(active={"model": model, "task": "smoke", "phase": "qualification"})
                    pilot = arena.run_pair(model, arena.load_task(args.tasks, "smoke"),
                                           args.tasks, args.results, 900, True,
                                           batch_id=batch + "-smoke")
                    state["attempts"].append({"model": model, "task": "smoke",
                                              "status": reporting.status_of(pilot), "at": now()})
                    if not reporting.is_valid(pilot):
                        block(model, "qualification infrastructure failure: " + reporting.error_category(pilot))
                        providers_blocked.add(provider)
                        continue
                    if not pilot["passed"] and pilot["tool_calls"] == 0:
                        block(model, "qualification produced no real tool calls")
                        continue
                    qualified.add(model)
                for task in todo:
                    selected = reporting.load_records([args.results])
                    existing = next((r for r in selected if r["model"] == model
                                     and r["task"] == task), None)
                    if existing and current(existing, hashes):
                        continue
                    if not stable():
                        update(state="stopped", active=None, reason="benchmark inputs changed")
                        return
                    update(active={"model": model, "task": task, "phase": phase,
                                   "state": "running", "started_at": now()})
                    result = arena.run_pair(model, arena.load_task(args.tasks, task),
                                            args.tasks, args.results, 1800, True,
                                            batch_id=batch)
                    status = reporting.status_of(result)
                    state["attempts"].append({"model": model, "task": task,
                                              "status": status, "at": now()})
                    update(active=None)
                    arena.write_report(reporting.load_records([args.results]), args.results)
                    if not reporting.is_valid(result):
                        block(model, "infrastructure failure: " + reporting.error_category(result))
                        if status in {"PROVIDER_ERROR", "API_ERROR"}:
                            providers_blocked.add(provider)
                        break
            update(active=None)
    final_records = reporting.load_records([args.results])
    final_plans = build_plan(final_records, hashes,
                             prescreen_models() if args.include_prescreen else ())
    arena.write_report(final_records, args.results)
    for script in ("analyze.py", "roster.py", "report_models.py"):
        result = subprocess.run([sys.executable, str(ROOT / "runner" / script),
                                 "--results", str(args.results)], capture_output=True, text=True)
        if result.returncode:
            print(f"[completion] report refresh failed: {script}")
    update(state="finished_with_blocks" if any(p["tasks"] for p in final_plans)
           else "complete", active=None, models=final_plans, finished_at=now())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--tasks", type=Path, default=ROOT / "tasks")
    parser.add_argument("--include-prescreen", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--retry-blocked", action="store_true",
                        help="retry saved blockers after their causes were resolved")
    args = parser.parse_args()
    args.results, args.tasks = args.results.resolve(), args.tasks.resolve()
    hashes = task_hashes(args.tasks)
    records = reporting.load_records([args.results])
    plans = build_plan(records, hashes, prescreen_models() if args.include_prescreen else ())
    if not args.run:
        print(json.dumps({"models": len(plans), "pending": sum(len(p["tasks"]) for p in plans),
                          "regrade": grader_only(records, hashes), "plan": plans}, indent=2))
        return
    if args.background:
        background(args)
        return
    stdout = RedactingWriter(sys.stdout, [os.environ.get(k, "") for k in SECRETS])
    stderr = RedactingWriter(sys.stderr, [os.environ.get(k, "") for k in SECRETS])
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            with run_lock.exclusive(ROOT, ".nonfree-controller.lock", blocking=False):
                execute(args, hashes, records, plans)
        finally:
            stdout.finish()
            stderr.finish()


if __name__ == "__main__":
    main()
