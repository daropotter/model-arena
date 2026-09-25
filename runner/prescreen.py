#!/usr/bin/env python3
"""Prescreen new models before a full sweep.

Runs the tiny `smoke` task (read a file, sum it, write the answer) with a short
timeout. Answers, cheaply:
  - does the model act at all (real tool calls)?
  - does it solve the trivial task?
  - is it too big / too slow for this hardware (timeout, zero tokens)?
  - did ollama reject it (no tool support)?

Usage:
  python3 runner/prescreen.py --models-file prescreen-candidates.txt
  python3 runner/prescreen.py --models ollama/qwen3:8b
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runner"))
import arena  # noqa: E402


VRAM_GB = float(os.environ.get("ARENA_VRAM_GB", "12"))
# ollama splits models between GPU and CPU, so weights above VRAM can still
# load. This is only a cheap safety net against obviously-hopeless sizes;
# everything under it gets a real warmup + smoke run.
SIZE_LIMIT_GB = float(os.environ.get("ARENA_SIZE_LIMIT_GB", str(VRAM_GB + 8)))


def model_size_gb(model: str) -> float:
    """Model weight size from ollama, or 0.0 if unknown (hosted models: 0)."""
    if not model.startswith("ollama/"):
        return 0.0
    try:
        tags = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:11434/api/tags", timeout=10).read())
        for m in tags.get("models", []):
            if m["name"] == model.replace("ollama/", ""):
                return m["size"] / 1e9
    except Exception:  # noqa: BLE001
        pass
    return 0.0


def model_capabilities(model: str) -> list:
    """Capabilities reported by ollama (e.g. ['completion', 'tools']).

    Hosted models (opencode/* etc.) are not in ollama: opencode's registry
    already only exposes tool-capable chat models, so report tools.
    """
    if not model.startswith("ollama/"):
        return ["completion", "tools"]
    model_id = model.replace("ollama/", "")
    payload = json.dumps({"model": model_id}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/show", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("capabilities", [])
    except Exception:  # noqa: BLE001
        return []


def warmup(model: str, timeout: int = 300):
    """Load the model with a 1-token prompt, directly against ollama.

    Returns (ok, detail, load_seconds). Separates "cannot load at all / too big
    for this hardware" from "loaded fine but failed the task". Hosted models
    are not loaded locally, so warmup is a no-op.
    """
    if not model.startswith("ollama/"):
        return True, "hosted model — no local load", 0.0
    model_id = model.replace("ollama/", "")
    payload = json.dumps({
        "model": model_id, "prompt": "hi", "stream": False,
        "keep_alive": "15m",  # stay in VRAM through the smoke run
        "options": {"num_predict": 1},
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate", data=payload,
        headers={"Content-Type": "application/json"})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        load_s = data.get("load_duration", 0) / 1e9
        return True, f"loaded in {load_s:.0f}s", load_s
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, f"warmup failed after {time.time() - start:.0f}s: {exc}", 0.0


def classify(record, run_dir: Path, warmup_ok: bool = True) -> tuple[str, str]:
    """Return (verdict, reason) for a smoke run."""
    if record["passed"]:
        return ("QUALIFIED", "solved the smoke task")
    events = run_dir / "events.jsonl"
    text = events.read_text(errors="replace") if events.exists() else ""
    if "does not support tools" in text:
        return ("EXCLUDED", "no-tool-support: ollama rejects tool calls")
    if record["timed_out"] and record["tokens"]["output"] == 0:
        if not warmup_ok:
            return ("EXCLUDED",
                    "too-big-for-hardware: model cannot even be loaded "
                    "(warmup failed) and the run timed out")
        return ("EXCLUDED",
                f"too-slow: timed out with 0 output tokens ({record['duration_s']:.0f}s) "
                f"even though the model loads")
    if record["tool_calls"] == 0:
        if '"type": "text"' in text or '"type":"text"' in text:
            if "tool" in text.lower() or "{" in text:
                return ("EXCLUDED",
                        "tool-hallucinator: answered with prose/fake tool calls, "
                        "never called a tool")
            return ("EXCLUDED", "prose-only: no tool call")
        return ("EXCLUDED", "no-action: no tool call and no text")
    return ("BORDERLINE",
            f"acted ({record['tool_calls']} tool calls) but failed the smoke task: "
            f"{record['detail'][:150]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=[])
    ap.add_argument("--models-file", default=None)
    ap.add_argument("--timeout", type=int, default=180,
                    help="legacy; the smoke run limit is fixed by "
                         "ARENA_SMOKE_TIMEOUT (default 900) so the "
                         "too-slow verdict does not drift")
    ap.add_argument("--warmup-timeout", type=int, default=600,
                    help="seconds to allow for the initial model load")
    ap.add_argument("--results", default=str(ROOT / "results-prescreen"))
    ap.add_argument("--report-only", action="store_true",
                    help="regenerate the report from existing results, run nothing")
    args = ap.parse_args()

    models = list(args.models)
    if args.models_file:
        models += [l.strip() for l in Path(args.models_file).read_text().splitlines()
                   if l.strip() and not l.startswith("#")]
    if not models and not args.report_only:
        raise SystemExit("no models given")

    results_root = Path(args.results).resolve()
    results_root.mkdir(parents=True, exist_ok=True)
    tasks_dir = ROOT / "tasks"
    task = arena.load_task(tasks_dir, "smoke")
    # Prescreen decides "too slow" from a run that must fit the smoke limit,
    # so the limit is fixed regardless of --timeout. Local models are slow by
    # nature (partial offload); 900s gives even 17GB+ models a fair chance.
    # Override with ARENA_SMOKE_TIMEOUT.
    smoke_timeout = int(os.environ.get("ARENA_SMOKE_TIMEOUT", "900"))

    only_local = all(m.startswith("ollama/") for m in models)
    if not args.report_only and only_local:
        arena.ensure_network(arena.NETWORK)
        arena.ensure_proxy(arena.GATEWAY, arena.OLLAMA_PORT)

    entries = []
    for model in ([] if args.report_only else models):
        print(f"\n[prescreen] {model}")
        caps = model_capabilities(model)
        if caps and "completion" not in caps:
            reason = (f"not-a-chat-model: capabilities {caps} — cannot run as an agent")
            print(f"[prescreen] {model}: EXCLUDED — {reason}")
            entries.append({"model": model, "verdict": "EXCLUDED",
                            "reason": reason, "record": None})
            continue
        if caps and "tools" not in caps:
            reason = (f"no-tool-support: capabilities {caps} — ollama will reject "
                      f"tool calls")
            print(f"[prescreen] {model}: EXCLUDED — {reason}")
            entries.append({"model": model, "verdict": "EXCLUDED",
                            "reason": reason, "record": None})
            continue
        size = model_size_gb(model)
        if size and size > SIZE_LIMIT_GB:
            reason = (f"too-big-for-hardware: {size:.1f} GB weights vs "
                      f"{VRAM_GB:.0f} GB VRAM (limit {SIZE_LIMIT_GB:.0f} GB); "
                      f"skipped without warmup")
            print(f"[prescreen] {model}: EXCLUDED — {reason}")
            entries.append({"model": model, "verdict": "EXCLUDED",
                            "reason": reason, "record": None})
            continue
        warmup_ok, warmup_detail, _ = warmup(model, timeout=args.warmup_timeout)
        print(f"[prescreen] {model}: warmup: {warmup_detail}")
        if not warmup_ok:
            entries.append({"model": model, "verdict": "EXCLUDED",
                            "reason": f"too-big-for-hardware: {warmup_detail}",
                            "record": None})
            continue
        try:
            record = arena.run_pair(model, task, tasks_dir, results_root,
                                    smoke_timeout, keep_workspace=True,
                                    force_timeout=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[prescreen] {model}: runner error {exc}")
            entries.append({"model": model, "verdict": "ERROR",
                            "reason": str(exc), "record": None})
            continue
        verdict, reason = classify(record, Path(record["run_dir"]), warmup_ok)
        entries.append({"model": model, "verdict": verdict, "reason": reason,
                        "record": record})
        print(f"[prescreen] {model}: {verdict} — {reason}")

    # Append this run's entries to a durable log, then merge with everything
    # recorded before (rescanning records picks up older runs too, so a re-test
    # of one model never wipes the rest of the report).
    log_path = results_root / "prescreen-results.jsonl"
    with open(log_path, "a") as f:
        for e in entries:
            slim = {"model": e["model"], "verdict": e["verdict"],
                    "reason": e["reason"],
                    "duration_s": e["record"]["duration_s"] if e["record"] else None,
                    "tool_calls": e["record"]["tool_calls"] if e["record"] else None,
                    "score": e["record"]["score"] if e["record"] else None}
            f.write(json.dumps(slim) + "\n")

    merged: dict[str, dict] = {}
    for rec_path in sorted(results_root.glob("*/record.json")):
        try:
            rec = json.loads(rec_path.read_text())
        except json.JSONDecodeError:
            continue
        verdict, reason = classify(rec, rec_path.parent)
        finished = rec.get("finished_at") or ""
        current = merged.get(rec["model"])
        if current and (current["record"].get("finished_at") or "") > finished:
            continue
        merged[rec["model"]] = {"model": rec["model"], "verdict": verdict,
                                "reason": reason, "record": rec}
    for line in log_path.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e["model"] in merged:
            # a record.json is an executed test and always beats a logged
            # verdict (e.g. an old size-based skip with no execution)
            continue
        merged[e["model"]] = {"model": e["model"], "verdict": e["verdict"],
                              "reason": e["reason"], "record": None,
                              "duration_s": e.get("duration_s"),
                              "tool_calls": e.get("tool_calls")}

    md = ["# prescreen of new models", ""]
    md.append(f"Time: {datetime.now().isoformat(timespec='seconds')}")
    md.append("Task: `smoke` (sum numbers from a file), run limit from meta.json.")
    md.append("")
    for verdict in ("QUALIFIED", "BORDERLINE", "EXCLUDED", "ERROR"):
        group = [e for e in merged.values() if e["verdict"] == verdict]
        if not group:
            continue
        md.append(f"## {verdict} ({len(group)})")
        md.append("")
        md.append("| model | time | tool calls | score | reason |")
        md.append("|---|---|---|---|---|")
        for e in sorted(group, key=lambda e: e["model"]):
            r = e["record"]
            if r:
                md.append(f"| {e['model']} | {r['duration_s']:.0f}s | "
                          f"{r['tool_calls']} | {r['score']:.2f} | {e['reason'][:160]} |")
            else:
                md.append(f"| {e['model']} | {e.get('duration_s') or '-'} | "
                          f"{e.get('tool_calls') if e.get('tool_calls') is not None else '-'} | "
                          f"- | {e['reason'][:160]} |")
        md.append("")
    out = results_root / "prescreen.md"
    out.write_text("\n".join(md) + "\n")
    print(f"\n[prescreen] report: {out}")

    qualified = [e["model"] for e in merged.values()
                 if e["verdict"] in ("QUALIFIED", "BORDERLINE")]
    with open(ROOT / "prescreen-passed.txt", "w") as f:
        for model in sorted(qualified):
            f.write(model + "\n")
    print(f"[prescreen] ready for further testing: {len(qualified)}/{len(merged)} "
          f"(saved in prescreen-passed.txt)")


if __name__ == "__main__":
    main()
