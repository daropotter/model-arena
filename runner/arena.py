#!/usr/bin/env python3
"""model-arena: run local models through opencode on graded agentic tasks.

For every (model, task) pair:
  1. copy task starter into a scratch dir
  2. run opencode in a docker container on an internal network (no internet,
     ollama reachable only through the host proxy on the bridge gateway)
  3. grade the resulting workspace with the task's hidden grader
  4. report: pass/fail, duration, tokens, tool calls, tamper detection

Usage:
  python3 runner/arena.py --tasks tasks --models ollama/gemma4-128k:latest
  python3 runner/arena.py --list
  python3 runner/arena.py --models-file models.txt --timeout 900
"""
import argparse
import base64
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

try:
    from . import reporting
except ImportError:
    import reporting

ROOT = Path(__file__).resolve().parent.parent
IMAGE = os.environ.get("ARENA_IMAGE", "model-arena-agent")
NETWORK = os.environ.get("ARENA_NETWORK", "arena-net")
GATEWAY = os.environ.get("ARENA_GATEWAY", "172.22.0.1")
SUBNET = os.environ.get("ARENA_SUBNET", "172.22.0.0/16")
OLLAMA_PORT = int(os.environ.get("ARENA_OLLAMA_PORT", "11435"))
PROXY_MARKER = "ollama_proxy.py"
SCRATCH_ROOT = Path(os.environ.get("ARENA_SCRATCH", "/tmp/model-arena"))
SCHEMA_VERSION = 2

IGNORED_NAMES = {".git", "__pycache__", "node_modules", ".pytest_cache"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_workspace(src: Path, dst: Path, excludes=()):
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir() or any(part in IGNORED_NAMES for part in item.parts):
            continue
        rel = item.relative_to(src)
        if any(str(rel).startswith(e) or rel.match(e) for e in excludes):
            continue
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, out)


def snapshot_hashes(workdir: Path) -> dict:
    """Hash every file that matters for tamper detection.

    Build artifacts (`__pycache__`, `.pyc`) are ignored: running the visible
    tests is expected behavior and creates them; they are not tampering.
    """
    hashes = {}
    for path in workdir.rglob("*"):
        if path.is_symlink():
            hashes[str(path.relative_to(workdir))] = "symlink:" + os.readlink(path)
            continue
        if not path.is_file() or path.suffix == ".pyc":
            continue
        if any(part in IGNORED_NAMES for part in path.relative_to(workdir).parts):
            continue
        hashes[str(path.relative_to(workdir))] = sha256_file(path)
    return hashes


def tree_digest(root: Path) -> str:
    payload = json.dumps(snapshot_hashes(root), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def file_digest(path: Path) -> str:
    return sha256_file(path) if path.exists() else "missing"


def image_digest() -> str:
    proc = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def git_revision() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def list_tasks(tasks_dir: Path):
    tasks = []
    for d in sorted(tasks_dir.iterdir()):
        meta_file = d / "meta.json"
        if d.is_dir() and meta_file.exists():
            tasks.append(json.loads(meta_file.read_text()))
    return tasks


def load_task(tasks_dir: Path, name: str):
    for t in list_tasks(tasks_dir):
        if t["name"] == name:
            return t
    raise SystemExit(f"unknown task: {name}")


def ensure_network(network: str) -> None:
    inspect = subprocess.run(
        ["docker", "network", "inspect", network], capture_output=True, text=True)
    if inspect.returncode != 0:
        print(f"[arena] creating internal docker network {network}")
        subprocess.run(["docker", "network", "create", "--internal",
                        "--subnet", SUBNET, "--gateway", GATEWAY, network],
                       check=True, capture_output=True)
        return
    try:
        data = json.loads(inspect.stdout)[0]
        configs = data.get("IPAM", {}).get("Config", [])
        gateways = {cfg.get("Gateway") for cfg in configs}
        subnets = {cfg.get("Subnet") for cfg in configs}
    except (json.JSONDecodeError, IndexError, TypeError):
        raise SystemExit(f"cannot inspect docker network {network}")
    if not data.get("Internal") or GATEWAY not in gateways or SUBNET not in subnets:
        raise SystemExit(
            f"docker network {network} has unsafe/unexpected configuration; "
            f"expected internal subnet={SUBNET} gateway={GATEWAY}")


def ensure_proxy(host: str, port: int) -> None:
    def reachable():
        try:
            with urllib.request.urlopen(
                    f"http://{host}:{port}/__arena_health", timeout=1) as response:
                return response.read() == b"model-arena-inference-proxy\n"
        except Exception:  # noqa: BLE001
            return False

    if reachable():
        return
    # Replace a legacy unrestricted TCP proxy that may still own the port.
    for proc_dir in Path("/proc").glob("[0-9]*"):
        try:
            cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\0", b" ")
            if PROXY_MARKER.encode() in cmdline:
                os.kill(int(proc_dir.name), 15)
        except (OSError, ValueError):
            continue
    time.sleep(0.2)
    print(f"[arena] starting ollama proxy on {host}:{port}")
    log_path = Path(os.environ.get("ARENA_LOG", "/tmp")) / "proxy.log"
    log = open(log_path, "a")
    try:
        subprocess.Popen(
            [sys.executable, str(ROOT / "runner" / "ollama_proxy.py"),
             "--listen", host, "--listen-port", str(port)],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        log.close()
    for _ in range(50):
        time.sleep(0.2)
        if reachable():
            return
    raise SystemExit("ollama proxy failed to start")


def is_local_model(model: str) -> bool:
    return model.startswith("ollama/")


def validate_model_name(model: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9._:/+@-]+", model):
        raise SystemExit(f"invalid model identifier: {model!r}")


def warmup_model(model: str, timeout: int = 300) -> float:
    """Preload a local model into VRAM before the run starts.

    Loading is not part of the task: a 17 GB model takes minutes to page in on
    partial offload, and counting that against the run deadline produced
    "timeouts" where the model never got a fair turn. Returns load seconds
    (0.0 for hosted models, which need no local load).
    """
    if not is_local_model(model):
        return 0.0
    if os.environ.get("ARENA_NO_WARMUP") == "1":
        return 0.0
    model_id = model[len("ollama/"):]
    timeout = int(os.environ.get("ARENA_WARMUP_TIMEOUT", "900"))
    payload = json.dumps({
        "model": model_id, "prompt": "hi", "stream": False,
        "keep_alive": "15m",
        "options": {"num_predict": 1},
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate", data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        print(f"[arena] {model}: warmup failed ({exc}) — continuing anyway")
        return 0.0
    load_s = data.get("load_duration", 0) / 1e9
    print(f"[arena] {model}: warmup loaded in {load_s:.0f}s")
    return load_s


# Agent container mounts. /tmp must be `exec`: entry.sh writes the opencode
# wrapper there and runs it, and docker tmpfs defaults to noexec. The grader
# container keeps its own noexec /tmp on purpose.
AGENT_TMPFS = (
    "/home/opencode:rw,nosuid,nodev,size=512m,uid=1000,gid=1000",
    "/tmp:rw,exec,nosuid,nodev,size=256m,mode=1777",
)

# Host-side opencode session store. The OpenAI subscription is an OAuth
# session here, not an API key, so openai/* runs get a private copy of just
# that entry (mounted read-only; the container copies it into $HOME).
OPENAI_AUTH_PATH = Path.home() / ".local/share/opencode/auth.json"


def make_openai_auth_file(model: str):
    """Temp auth.json holding only the openai entry, or None.

    Scoped to a single provider so a run never sees other stored credentials.
    The caller must delete the returned path after the container exits.
    """
    if not model.startswith("openai/"):
        return None
    try:
        data = json.loads(OPENAI_AUTH_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    entry = data.get("openai")
    if not entry:
        return None
    fd, name = tempfile.mkstemp(prefix="arena-openai-auth-", suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump({"openai": entry}, fh)
    os.chmod(name, 0o600)
    return Path(name)


def run_agent(model: str, scratch: Path, prompt: str, timeout: int, log_dir: Path):
    (scratch / "PROMPT.txt").write_text(prompt)
    events_path = log_dir / "events.jsonl"
    err_path = log_dir / "stderr.log"
    mounts = [
        "-v", f"{scratch.resolve()}:/workspace",
        "-v", f"{(ROOT / 'docker' / 'agent_entry.sh').resolve()}:/entry.sh:ro",
    ]
    extra_agents = os.environ.get("ARENA_EXTRA_AGENTS")
    if extra_agents and Path(extra_agents).exists():
        mounts += ["-v", f"{Path(extra_agents).resolve()}:/extra_agents.md:ro"]
    openai_auth = make_openai_auth_file(model)
    if openai_auth:
        mounts += ["-v", f"{openai_auth}:/extra_auth.json:ro"]
    # Local models run on the isolated network and reach ollama through the host
    # proxy. Hosted models (opencode Zen and friends) need real internet, so they
    # go on the default bridge; they need no credentials.
    if is_local_model(model):
        network = NETWORK
    else:
        network = os.environ.get("ARENA_HOSTED_NETWORK", "bridge")
    env_args = []
    # Hosted providers identify the caller: the Zen free tier only works from
    # inside opencode, and OPENCODE_API_KEY lifts the free limit. OpenRouter
    # free models authenticate with OPENROUTER_API_KEY. Pass them through when
    # present; never log or persist them.
    if not is_local_model(model):
        api_key = os.environ.get("OPENCODE_API_KEY")
        if api_key:
            env_args += ["-e", "OPENCODE_API_KEY"]
        if model.startswith("openrouter/"):
            or_key = os.environ.get("OPENROUTER_API_KEY")
            if or_key:
                env_args += ["-e", "OPENROUTER_API_KEY"]
        if model.startswith("openai/"):
            oai_key = os.environ.get("OPENAI_API_KEY")
            if oai_key:
                env_args += ["-e", "OPENAI_API_KEY"]
    if os.environ.get("ARENA_NO_THINK") == "1":
        env_args += ["-e", "ARENA_NO_THINK=1"]
    env_args += ["-e", f"ARENA_POST_DEADLINE={int(os.environ.get('ARENA_POST_DEADLINE', '1800'))}"]
    model_opts = os.environ.get("ARENA_MODEL_OPTS")
    if model_opts:
        env_args += ["-e", f"ARENA_MODEL_OPTS={model_opts}"]
    cmd = [
        "docker", "run", "--rm",
        "--name", f"arena-{log_dir.parent.name}-{log_dir.name}",
        "--network", network,
        "--user", "1000:1000",
        "--read-only",
        *[arg for spec in AGENT_TMPFS for arg in ("--tmpfs", spec)],
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "--pids-limit", os.environ.get("ARENA_PIDS", "256"),
        *mounts,
        *env_args,
        "--memory", os.environ.get("ARENA_MEMORY", "6g"),
        "--cpus", os.environ.get("ARENA_CPUS", "8"),
        IMAGE,
        "sh", "/entry.sh", model, "/workspace/PROMPT.txt", str(timeout),
        f"http://{GATEWAY}:{OLLAMA_PORT}/v1",
    ]
    cname = f"arena-{log_dir.parent.name}-{log_dir.name}"
    idle_grace = float(os.environ.get("ARENA_IDLE_GRACE", "900"))
    # Hard ceiling beyond the deadline; must match the safety net inside the
    # entry script (which uses the same variable).
    post_deadline = int(os.environ.get("ARENA_POST_DEADLINE", "1800"))
    start = time.time()
    proc = None
    try:
        with open(events_path, "wb") as out, open(err_path, "wb") as err:
            proc = subprocess.Popen(cmd, stdout=out, stderr=err)
            try:
                rc, termination = supervise_agent(
                    proc, events_path, start, timeout, idle_grace, post_deadline,
                    kill=lambda: subprocess.run(
                        ["docker", "kill", cname], capture_output=True,
                        timeout=30),
                    stop=lambda: subprocess.run(
                        ["docker", "stop", "-t", "25", cname],
                        capture_output=True, timeout=45),
                )
            finally:
                if proc.poll() is None:
                    subprocess.run(["docker", "rm", "-f", cname],
                                   capture_output=True, timeout=30)
                    proc.kill()
                    rc = proc.wait(timeout=30)
                    termination = "runner_interrupted"
    finally:
        if openai_auth:
            openai_auth.unlink(missing_ok=True)
    return rc, time.time() - start, termination


def supervise_agent(proc, events_path: Path, start: float, timeout: int,
                    idle_grace: float, post_deadline: int,
                    kill=lambda: None, stop=lambda: None,
                    poll_interval: float = 10.0, clock=time.time):
    """Watch an agent process; return (rc, termination_reason).

    Pure supervision logic, injectable for tests: `kill`/`stop` perform the
    backend action and `clock` supplies monotonic time.
    """
    wall = start + timeout + post_deadline
    deadline = start + timeout
    termination = "completed"
    last_size = 0
    last_change = start
    ever_emitted = False
    rc = None
    while rc is None:
        try:
            rc = proc.wait(timeout=poll_interval)
            break
        except subprocess.TimeoutExpired:
            pass
        now = clock()
        try:
            size = events_path.stat().st_size if events_path.exists() else 0
        except OSError:
            size = 0
        if size > last_size:
            last_size = size
            last_change = now
            ever_emitted = True
        if now > wall:
            termination = "hard_wall"
            kill()
            rc = proc.wait(timeout=30)
        elif now > deadline and not ever_emitted \
                and now - start > timeout + 120:
            termination = "no_events_timeout"
            kill()
            rc = proc.wait(timeout=30)
        elif now > deadline and now - last_change > idle_grace:
            termination = "idle_timeout"
            stop()
            rc = proc.wait(timeout=30)
    return rc, termination


def parse_events(events_path: Path) -> dict:
    stats = {
        "tokens_input": 0, "tokens_output": 0, "tokens_reasoning": 0,
        "steps": 0, "tool_calls": 0, "tool_errors": 0, "tool_names": {},
        "text_chars": 0, "session_ids": set(), "api_errors": 0,
    }
    if not events_path.exists():
        return {**stats, "session_ids": []}
    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = ev.get("type")
            part = ev.get("part", {}) or {}
            if ev.get("sessionID"):
                stats["session_ids"].add(ev["sessionID"])
            if etype == "step_finish":
                tok = part.get("tokens", {}) or {}
                stats["tokens_input"] += tok.get("input", 0)
                stats["tokens_output"] += tok.get("output", 0)
                stats["tokens_reasoning"] += tok.get("reasoning", 0)
                stats["steps"] += 1
            elif etype == "tool_use":
                stats["tool_calls"] += 1
                tool = part.get("tool", "?")
                stats["tool_names"][tool] = stats["tool_names"].get(tool, 0) + 1
                state = part.get("state", {}) or {}
                if state.get("status") == "error" or state.get("error"):
                    stats["tool_errors"] += 1
            elif etype == "text":
                stats["text_chars"] += len(part.get("text", "") or "")
            elif etype == "error":
                stats["api_errors"] += 1
    stats["session_ids"] = sorted(stats["session_ids"])
    return stats


def grade(task: dict, workspace: Path, grader_dir: Path, log_dir: Path) -> dict:
    """Run the hidden grader with candidate subprocesses under a separate UID."""
    timeout = int(task.get("timeout", 120))
    out_dir = log_dir / "grade"
    out_dir.mkdir(parents=True, exist_ok=True)
    cname = f"arena-grader-{log_dir.name}"
    cmd = [
        "docker", "run", "--rm",
        "--name", cname,
        "--network", "none",
        "--user", "0:0",
        "--read-only",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
        "--memory", os.environ.get("ARENA_GRADER_MEMORY", "1g"),
        "--cpus", os.environ.get("ARENA_GRADER_CPUS", "2"),
        "--pids-limit", os.environ.get("ARENA_GRADER_PIDS", "128"),
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL", "--cap-add", "CHOWN",
        "--cap-add", "SETUID", "--cap-add", "SETGID",
        "--cap-add", "DAC_OVERRIDE",
        "-v", f"{workspace.resolve()}:/submission:ro",
        "-v", f"{grader_dir.resolve()}:/root/grader-src:ro",
        "-v", f"{(ROOT / 'docker' / 'grader_entry.py').resolve()}:/grader_entry.py:ro",
        "-v", f"{(ROOT / 'docker' / 'grader_sitecustomize.py').resolve()}:/grader_sitecustomize.py:ro",
        IMAGE,
        "python3", "/grader_entry.py", str(timeout),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout + 60)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", cname], capture_output=True,
                       timeout=30)
        return {"passed": False, "score": 0.0,
                "detail": "grader failed: timeout", "grader_error": True}
    result_path = out_dir / "result.json"
    marker = "ARENA_RESULT_B64="
    encoded = next((line[len(marker):] for line in proc.stdout.splitlines()
                    if line.startswith(marker)), None)
    if proc.returncode == 0 and encoded:
        try:
            result = json.loads(base64.b64decode(encoded, validate=True))
            if type(result.get("passed")) is not bool:
                raise ValueError("passed must be a boolean")
            score = result.get("score")
            if type(score) not in (int, float) or not math.isfinite(score) \
                    or not 0.0 <= score <= 1.0:
                raise ValueError("score must be finite and within 0..1")
            result_path.write_text(json.dumps(result, indent=2))
            return result
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            detail = f"invalid grader result: {exc}"
        except base64.binascii.Error as exc:
            detail = f"invalid grader channel: {exc}"
    else:
        detail = f"grader failed rc={proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}"
    return {
        "passed": False, "score": 0.0,
        "detail": detail, "grader_error": True,
    }


def run_pair(model: str, task: dict, tasks_dir: Path, results_root: Path,
              base_timeout: int, keep_workspace: bool,
              force_timeout: bool = False, repeat_index: int = 0,
              batch_id: str = "") -> dict:
    name = task["name"]
    if force_timeout:
        # Use base_timeout even if the task caps it lower: needed for slow
        # models (Zen free tier, CPU-offloaded) where the cap is the reason
        # they fail, not the task itself.
        timeout = base_timeout
    else:
        timeout = min(int(task.get("timeout", 600)), base_timeout)
    slug = model.replace("/", "_").replace(":", "_")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
    run_dir = results_root / f"{stamp}__{name}__{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)

    scratch = SCRATCH_ROOT / f"{name}__{slug}__{stamp}"
    if scratch.exists():
        shutil.rmtree(scratch)
    copy_workspace(tasks_dir / name / "starter", scratch)
    before = snapshot_hashes(scratch)

    prompt = (tasks_dir / name / "prompt.md").read_text()
    print(f"[arena] {model} x {name}: running (timeout {timeout}s)")
    warmup_model(model)
    rc, duration, termination = run_agent(model, scratch, prompt, timeout, run_dir)

    stats = parse_events(run_dir / "events.jsonl")

    after = snapshot_hashes(scratch)
    changed = sorted(k for k in after if before.get(k) != after[k])
    removed = sorted(k for k in before if k not in after)

    protected = task.get("protected", [])

    def is_protected(rel: str) -> bool:
        return any(
            rel == p or rel.startswith(p.rstrip("/") + "/") for p in protected
        )

    tamper = {
        "touched_protected": [f for f in changed + removed if is_protected(f)],
        "untracked_files": sorted(k for k in after if k not in before),
        "tracked_files_changed": [f for f in changed if f in before],
        "removed_files": removed,
    }

    provider_failure = (stats["api_errors"] > 0 and stats["tool_calls"] == 0
                        and stats["tokens_output"] == 0)
    if provider_failure:
        grade_result = {
            "passed": False, "score": 0.0,
            "detail": "provider/API failure before the model acted",
        }
        run_outcome = "provider_error" if not is_local_model(model) else "api_error"
    elif tamper["touched_protected"]:
        grade_result = {
            "passed": False, "score": 0.0,
            "detail": f"tamper: protected files modified: {tamper['touched_protected'][:5]}",
        }
        run_outcome = "tamper"
    else:
        grade_result = grade(task, scratch, tasks_dir / name / "grader", run_dir)
        if grade_result.get("grader_error"):
            run_outcome = "grader_error"
        elif termination != "completed":
            run_outcome = "agent_timeout"
        elif rc not in (0, None):
            run_outcome = "agent_error"
        else:
            run_outcome = "completed"

    submission = run_dir / "submission"
    shutil.copytree(scratch, submission, symlinks=True)
    valid_for_quality = run_outcome not in {"provider_error", "api_error", "grader_error"}
    task_dir = tasks_dir / name
    provenance = {
        "suite_id": os.environ.get("ARENA_SUITE_ID", "model-arena-v2"),
        "image": IMAGE,
        "image_digest": image_digest(),
        "git_revision": git_revision(),
        "runner_digest": tree_digest(ROOT / "runner"),
        "docker_digest": tree_digest(ROOT / "docker"),
        "task_digest": tree_digest(task_dir),
        "starter_digest": tree_digest(task_dir / "starter"),
        "grader_digest": tree_digest(task_dir / "grader"),
        "prompt_digest": file_digest(task_dir / "prompt.md"),
        "submission_digest": tree_digest(submission),
        "timeout_s": timeout,
        "idle_grace_s": float(os.environ.get("ARENA_IDLE_GRACE", "900")),
        "post_deadline_s": int(os.environ.get("ARENA_POST_DEADLINE", "1800")),
        "no_think": os.environ.get("ARENA_NO_THINK") == "1",
        "model_options": os.environ.get("ARENA_MODEL_OPTS", ""),
    }

    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": stamp,
        "batch_id": batch_id or stamp,
        "repeat_index": repeat_index,
        "model": model,
        "task": name,
        "task_title": task.get("title", name),
        "passed": bool(grade_result.get("passed")),
        "score": float(grade_result.get("score", 0.0)),
        "detail": grade_result.get("detail", ""),
        "duration_s": round(duration, 1),
        "exit_code": rc,
        # True only when the runner had to kill the container (stuck/idle
        # past the deadline, hard wall, or never emitted any event). A model
        # that finishes its work past the deadline is slow, not timed out:
        # its duration says everything.
        "timed_out": termination in {"hard_wall", "idle_timeout", "no_events_timeout"},
        "tokens": {
            "input": stats["tokens_input"], "output": stats["tokens_output"],
            "reasoning": stats["tokens_reasoning"],
        },
        "steps": stats["steps"],
        "tool_calls": stats["tool_calls"],
        "tool_errors": stats["tool_errors"],
        "tool_names": stats["tool_names"],
        "api_errors": stats["api_errors"],
        "run_outcome": run_outcome,
        "termination_reason": termination,
        "valid_for_quality": valid_for_quality,
        "provenance": provenance,
        "tamper": tamper,
        "run_dir": str(run_dir),
        "workspace": str(submission),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "record.json").write_text(json.dumps(record, indent=2))
    if not keep_workspace:
        shutil.rmtree(scratch, ignore_errors=True)
    status = "PASS" if record["passed"] else "FAIL"
    print(f"[arena] {model} x {name}: {status} ({record['score']:.2f}) "
          f"in {record['duration_s']}s, {record['tokens']['output']} out-tok, "
          f"{record['tool_calls']} tool calls")
    if not record["passed"]:
        print(f"        detail: {record['detail'][:200]}")
    return record


def load_all_records(results_root: Path) -> list:
    """Canonical latest-valid records from this results directory."""
    return reporting.load_records([results_root], include_smoke=True)


def merge_previous(previous: list, records: list) -> list:
    """Refresh valid cells while retaining earlier work after invalid retries."""
    previous_by_cell = {(r["model"], r["task"]): r for r in previous}
    refreshed = {(r["model"], r["task"]) for r in records
                 if reporting.is_valid(r)
                 or not reporting.is_valid(previous_by_cell.get(
                     (r["model"], r["task"]), {"valid_for_quality": False}))}
    return [r for r in previous if (r["model"], r["task"]) not in refreshed] \
        + [r for r in records if (r["model"], r["task"]) in refreshed]


def write_report(records, results_root: Path) -> Path:
    # `smoke` is the prescreen task, not a scored competition task; keep it out
    # of the main report (the prescreen has its own report).
    records = [r for r in records if r.get("task") != "smoke"]
    csv_path = results_root / "report.csv"
    fields = ["model", "task", "passed", "score", "duration_s", "exit_code",
              "timed_out", "tokens_input", "tokens_output", "tokens_reasoning",
              "steps", "tool_calls", "tool_errors", "detail"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            row = {
                "model": r["model"], "task": r["task"],
                "passed": "1" if r["passed"] else "0",
                "score": f"{r['score']:.2f}", "duration_s": r["duration_s"],
                "exit_code": r["exit_code"], "timed_out": "1" if r["timed_out"] else "0",
                "tokens_input": r["tokens"]["input"],
                "tokens_output": r["tokens"]["output"],
                "tokens_reasoning": r["tokens"]["reasoning"],
                "steps": r["steps"], "tool_calls": r["tool_calls"],
                "tool_errors": r["tool_errors"],
                "detail": str(r["detail"])[:200],
            }
            writer.writerow(row)

    models = sorted({r["model"] for r in records})
    tasks = sorted({r["task"] for r in records})
    md = ["# model-arena report", "",
          f"Generated: {datetime.now(timezone.utc).isoformat()}",
          f"Models: {len(models)}  Tasks: {len(tasks)}  Runs: {len(records)}", ""]
    header = "| model | " + " | ".join(tasks) + " | pass-rate |"
    md.append(header)
    md.append("|" + "---|" * (len(tasks) + 2))
    for m in models:
        cells = []
        for t in tasks:
            runs = [r for r in records if r["model"] == m and r["task"] == t]
            if not runs:
                cells.append("-")
            else:
                valid = [r for r in runs if r.get("valid_for_quality", True)]
                if not valid:
                    cells.append("invalid")
                    continue
                score = sum(r["score"] for r in valid) / len(valid)
                passes = sum(1 for r in valid if r["passed"])
                cells.append(f"{passes}/{len(valid)} · {score:.2f}")
        quality = [r for r in records if r["model"] == m
                   and r.get("valid_for_quality", True)]
        passed = sum(1 for r in quality if r["passed"])
        total = len(quality)
        cells.append(f"{passed}/{total}")
        md.append(f"| {m} | " + " | ".join(cells) + " |")
    md.append("")
    md.append("## per run")
    md.append("")
    md.append("| model | task | result | score | time | out-tok | tools | detail |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(records, key=lambda r: (r["model"], r["task"])):
        md.append(
            f"| {r['model']} | {r['task']} | {'PASS' if r['passed'] else 'fail'} | "
            f"{r['score']:.2f} | {r['duration_s']}s | {r['tokens']['output']} | "
            f"{r['tool_calls']} | {str(r['detail'])[:120]} |")
    md_path = results_root / "report.md"
    md_path.write_text("\n".join(md) + "\n")
    return md_path


def main():
    ap = argparse.ArgumentParser(description="model-arena runner")
    ap.add_argument("--tasks", default=str(ROOT / "tasks"))
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--models-file", type=str, default=None)
    ap.add_argument("--task", nargs="*", default=None, help="limit to task names")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=1800,
                    help="per-run deadline in seconds. This is a soft "
                         "deadline, not a hard kill: the runner watches the "
                         "event stream and only stops the model when it is "
                         "idle past the deadline (see README 'Timeout "
                         "model'). Local models are slow; the run time is "
                         "recorded anyway.")
    ap.add_argument("--force-timeout", action="store_true",
                    help="use --timeout even for tasks whose meta.json caps it "
                         "lower (for slow models where the cap is the cause)")
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--merge", action="store_true",
                    help="keep earlier runs from --results and refresh only the "
                         "models/tasks in this invocation")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    tasks_dir = Path(args.tasks)
    results_root = Path(args.results).resolve()
    results_root.mkdir(parents=True, exist_ok=True)

    tasks = list_tasks(tasks_dir)
    if args.list:
        print("tasks:")
        for t in tasks:
            print(f"  {t['name']:16s} timeout={t.get('timeout', 600):4d}s  {t.get('title', '')}")
        print("\nmodels (from ollama):")
        try:
            out = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
            for line in out.splitlines()[1:]:
                if line.strip():
                    print("  ollama/" + line.split()[0])
        except FileNotFoundError:
            print("  (ollama not found)")
        return

    models = list(args.models)
    if args.models_file:
        models += [l.strip() for l in Path(args.models_file).read_text().splitlines()
                   if l.strip() and not l.startswith("#")]
    if not models:
        raise SystemExit("no models given (use --models or --models-file)")
    for model in models:
        validate_model_name(model)

    if args.task:
        tasks = [t for t in tasks if t["name"] in args.task]

    # Local models run on the isolated arena-net and need the host ollama
    # proxy; hosted models (opencode/* etc.) go on the default bridge with
    # internet and need neither. Skipping this for hosted-only runs avoids
    # touching docker networks and binding the proxy for nothing.
    if any(is_local_model(m) for m in models):
        ensure_network(NETWORK)
        ensure_proxy(GATEWAY, OLLAMA_PORT)

    previous = load_all_records(results_root) if args.merge else []
    batch_id = (datetime.now().strftime("%Y%m%d-%H%M%S") + "-"
                + uuid4().hex[:8])
    records = []
    for model in models:
        for task in tasks:
            for rep in range(args.repeats):
                if args.repeats > 1:
                    print(f"[arena] repeat {rep + 1}/{args.repeats}")
                try:
                    records.append(run_pair(model, task, tasks_dir, results_root,
                                            args.timeout, keep_workspace=True,
                                            force_timeout=args.force_timeout,
                                            repeat_index=rep, batch_id=batch_id))
                except Exception as exc:
                    print(f"[arena] {model} x {task['name']}: ERROR {exc}")
                    stamp = (datetime.now().strftime("%Y%m%d-%H%M%S") + "-"
                             + uuid4().hex[:6])
                    slug = model.replace("/", "_").replace(":", "_")
                    run_dir = results_root / f"{stamp}__{task['name']}__{slug}"
                    run_dir.mkdir(parents=True, exist_ok=True)
                    failed_record = {
                        "schema_version": SCHEMA_VERSION, "run_id": stamp,
                        "batch_id": batch_id,
                        "repeat_index": rep,
                        "model": model, "task": task["name"],
                        "task_title": task.get("title", ""), "passed": False,
                        "score": 0.0, "detail": f"runner error: {exc}",
                        "duration_s": 0, "exit_code": -1, "timed_out": False,
                        "tokens": {"input": 0, "output": 0, "reasoning": 0},
                        "steps": 0, "tool_calls": 0, "tool_errors": 0,
                        "tool_names": {}, "api_errors": 0,
                        "run_outcome": "runner_error",
                        "termination_reason": "runner_exception",
                        "valid_for_quality": False,
                        "tamper": {}, "run_dir": str(run_dir), "workspace": "",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                    }
                    (run_dir / "record.json").write_text(
                        json.dumps(failed_record, indent=2))
                    records.append(failed_record)

    if args.merge:
        merged = merge_previous(previous, records)
        print(f"[arena] merging: {len(merged) - len(records)} previous runs "
              f"kept, {len(records)} new runs")
        records = merged

    md_path = write_report(records, results_root)
    passed = sum(1 for r in records if r["passed"])
    print(f"\n[arena] {passed}/{len(records)} passed")
    print(f"[arena] report: {md_path}")


if __name__ == "__main__":
    main()
