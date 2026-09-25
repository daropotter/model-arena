#!/usr/bin/env python3
"""Generate a detailed per-model markdown report.

Pulls everything: competition runs (results/), prescreen runs
(results-prescreen*, results-prescreen2), and the tool-instruction A/B
(results-ab/). Each model gets its own section: metadata, verdict, per-task
results, what it actually did in the tool stream, and where the raw evidence
lives.

Usage:
  python3 runner/report_models.py
  python3 runner/report_models.py --out results/models-report.md
"""

import argparse
import json
import statistics
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runner"))
import analyze  # noqa: E402
import roster  # noqa: E402
import prescreen as prescreen_mod  # noqa: E402

TASK_ORDER = ["cronlog", "datajanitor", "generator", "ledger", "tasklog"]
NEW_TASK_ORDER = ["filedock", "sumtool", "pipeline", "codec", "scheduler"]
TASK_TITLES = {
    "cronlog": "concurrency: flock, lock timeout, atomic writes",
    "datajanitor": "messy CSV normalization (BOM, formats, duplicates)",
    "generator": "reverse-engineer PRNG from samples",
    "ledger": "repair CLI against spec (rounding, ordering, zero rows)",
    "tasklog": "cross-file feature + store migration v1->v2",
    "smoke": "prescreen: read a file, sum it, write the answer",
    "filedock": "organize inbox files, deduplicate, write manifest",
    "sumtool": "fix two bugs in one small function",
    "pipeline": "pack/unpack round-trip of JSON",
    "codec": "binary frame codec (varint, CRC32)",
    "scheduler": "minimize late jobs with dependencies",
}
STATUS_LABEL = {
    "finished": "worked",
    "TEXT-ONLY": "prose-only",
    "TOOL-TEXT": "fake tool call (as text)",
    "NO-ACTION": "no action",
    "TIMEOUT": "timeout",
    "UNSUPPORTED": "no tool support",
}


# ---------------------------------------------------------------- ollama meta

def fetch_zen_registry() -> dict:
    """opencode's own model registry (Zen etc.) from its cache file."""
    path = Path.home() / ".cache" / "opencode" / "models.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    registry = {}
    for prov_name, prov in data.items():
        if not isinstance(prov, dict):
            continue
        for model_id, entry in (prov.get("models") or {}).items():
            registry[f"{prov_name}/{model_id}"] = entry
    return registry


def fetch_ollama_meta(models):
    """Size, capabilities and family from ollama; empty dict on failure."""
    meta = {}
    registry = fetch_zen_registry()
    try:
        tags = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:11434/api/tags", timeout=10).read())
    except Exception:  # noqa: BLE001
        tags = {"models": []}
    sizes = {m["name"]: m["size"] / 1e9 for m in tags.get("models", [])}
    for model in models:
        if not model.startswith("ollama/"):
            entry = registry.get(model, {})
            limit = entry.get("limit") or {}
            cost = entry.get("cost") or {}
            meta[model] = {
                "size_gb": None,
                "capabilities": (["completion", "tools"]
                                 + (["reasoning"] if entry.get("reasoning") else [])
                                 + (["vision"] if entry.get("attachment") else [])),
                "family": model.split("/")[0],
                "params": None,
                "quant": None,
                "context": limit.get("context"),
                "hosted": True,
                "free": (cost.get("input", 1) or 0) == 0
                        and (cost.get("output", 1) or 0) == 0,
            }
            continue
        name = model.replace("ollama/", "")
        entry = {"size_gb": sizes.get(name), "capabilities": [],
                 "family": None, "params": None, "quant": None}
        payload = json.dumps({"model": name}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/show", data=payload,
            headers={"Content-Type": "application/json"})
        try:
            show = json.loads(urllib.request.urlopen(req, timeout=15).read())
            entry["capabilities"] = show.get("capabilities", []) or []
            details = show.get("details", {}) or {}
            entry["family"] = details.get("family")
            entry["params"] = details.get("parameter_size")
            entry["quant"] = details.get("quantization_level")
        except Exception:  # noqa: BLE001
            pass
        meta[model] = entry
    return meta


# ------------------------------------------------------------------- helpers

def load_runs(results_dirs):
    """Latest record.json per (model, task), split into scored and smoke."""
    latest_scored, latest_smoke = {}, {}
    for directory in results_dirs:
        for path in sorted(Path(directory).glob("*/record.json")):
            try:
                record = json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
            finished = record.get("finished_at") or ""
            if record.get("task") == "smoke":
                key = record["model"]
                if key not in latest_smoke or finished > (
                        latest_smoke[key].get("finished_at") or ""):
                    latest_smoke[key] = record
            else:
                key = (record["model"], record["task"])
                if key not in latest_scored or finished > (
                        latest_scored[key].get("finished_at") or ""):
                    latest_scored[key] = record
    return list(latest_scored.values()), list(latest_smoke.values())


def run_behavior(run_dir):
    """Tool usage, tool errors, text snippets and API errors from events."""
    info = {"tools": {}, "tool_errors": {}, "texts": [], "api_errors": 0,
            "events_bytes": 0}
    if not run_dir:
        return info
    events = Path(run_dir) / "events.jsonl"
    if not events.exists():
        return info
    raw = events.read_text(errors="replace")
    info["events_bytes"] = len(raw)
    for line in raw.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = ev.get("type")
        part = ev.get("part", {}) or {}
        if etype == "tool_use":
            tool = part.get("tool", "?")
            info["tools"][tool] = info["tools"].get(tool, 0) + 1
            state = part.get("state", {}) or {}
            if state.get("status") == "error" or state.get("error"):
                info["tool_errors"][tool] = info["tool_errors"].get(tool, 0) + 1
        elif etype == "text":
            text = (part.get("text") or "").strip()
            if text:
                info["texts"].append(text)
        elif etype == "error":
            info["api_errors"] += 1
    return info


def tool_summary(tool_names, tool_errors):
    if not tool_names:
        return "-"
    parts = []
    for name, count in sorted(tool_names.items(), key=lambda kv: -kv[1]):
        errs = tool_errors.get(name, 0) if tool_errors else 0
        parts.append(f"{name}×{count}" + (f" ({errs} err)" if errs else ""))
    return ", ".join(parts)


def snippet(text, limit=260):
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


def detail_bullets(detail, limit=14):
    if not detail:
        return []
    parts = [p.strip() for p in str(detail).split("; ") if p.strip()]
    out = parts[:limit]
    if len(parts) > limit:
        out.append(f"… (+{len(parts) - limit} more)")
    return out


def fmt(seconds):
    if seconds is None:
        return "-"
    seconds = float(seconds)
    if seconds >= 60:
        return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
    return f"{seconds:.0f}s"


def status_cell(record):
    status = analyze.status_of(record)
    if record["passed"]:
        return "**PASS**"
    label = STATUS_LABEL.get(status, status)
    return f"fail ({label})"


def run_date(record):
    finished = record.get("finished_at") or ""
    return finished[:10] if finished else "?"


def meta_line(model, meta):
    m = meta.get(model, {})
    bits = []
    if m.get("hosted"):
        tag = "hosted (opencode Zen"
        if m.get("free"):
            tag += ", free"
        bits.append(tag + ")")
    if m.get("size_gb"):
        bits.append(f"{m['size_gb']:.1f} GB")
    if m.get("params"):
        bits.append(str(m["params"]))
    if m.get("quant"):
        bits.append(str(m["quant"]))
    if m.get("context"):
        bits.append(f"ctx {m['context']:,}")
    if m.get("family") and not m.get("hosted"):
        bits.append(f"family `{m['family']}`")
    caps = m.get("capabilities") or []
    if caps:
        bits.append("capabilities: " + ", ".join(f"`{c}`" for c in caps))
    return " · ".join(bits) if bits else "(brak metadanych)"


def baseline_floors(scored):
    floors = {}
    for task in sorted({r["task"] for r in scored}):
        scores = [r["score"] for r in scored
                  if r["task"] == task and r["tool_calls"] == 0
                  and not r["timed_out"]]
        if scores:
            floors[task] = min(scores)
    return floors


# ------------------------------------------------------------ model section

def model_section(model, runs, meta, verdict, evidence, ab_runs, smoke_runs):
    lines = []
    passed = sum(1 for r in runs if r["passed"])
    acted = sum(1 for r in runs if r["tool_calls"] > 0)
    scores = [r["score"] for r in runs]
    avg = statistics.mean(scores) if scores else 0.0
    times = [r["duration_s"] for r in runs]
    median_time = statistics.median(times) if times else 0
    out_tok = sum(r["tokens"]["output"] for r in runs)
    tools = sum(r["tool_calls"] for r in runs)
    tool_err = sum(r["tool_errors"] for r in runs)

    badge = "✅" if passed else ("⚠️" if acted else "❌")
    lines.append(f"### {badge} `{model}`")
    lines.append("")
    lines.append(f"**Verdict:** {verdict} — {evidence}")
    lines.append("")
    lines.append(f"**Metrics:** {meta_line(model, meta)}")
    lines.append("")
    lines.append(
        f"**Summary:** avg score **{avg:.2f}** · passes **{passed}/{len(runs)}** · "
        f"used tools {acted}/{len(runs)} · median time {fmt(median_time)} · "
        f"out-tokens {out_tok:,} · tool calls {tools} ({tool_err} errors)")
    lines.append("")

    # per-task table (best run per task)
    lines.append("| task | status | score | time | run date | out-tok | tool calls |")
    lines.append("|---|---|---|---|---|---|---|")
    by_task = {}
    for task in sorted({r["task"] for r in runs},
                       key=lambda t: (TASK_ORDER + NEW_TASK_ORDER).index(t)
                       if t in TASK_ORDER + NEW_TASK_ORDER else 99):
        task_runs = [r for r in runs if r["task"] == task]
        if not task_runs:
            continue
        best = max(task_runs, key=lambda r: (r["passed"], r["score"]))
        by_task[task] = best
        lines.append(
            f"| `{task}` | {status_cell(best)} | {best['score']:.2f} | "
            f"{fmt(best['duration_s'])} | {run_date(best)} | "
            f"{best['tokens']['output']:,} | "
            f"{tool_summary(best.get('tool_names'), None)} |")
    lines.append("")

    # per-task detail + behavior
    lines.append("<details>")
    lines.append("<summary>Run details (click)</summary>")
    lines.append("")
    for task in sorted({r["task"] for r in runs},
                       key=lambda t: (TASK_ORDER + NEW_TASK_ORDER).index(t)
                       if t in TASK_ORDER + NEW_TASK_ORDER else 99):
        best = by_task.get(task)
        if not best:
            continue
        behavior = run_behavior(best.get("run_dir"))
        lines.append(f"**`{task}`** — {TASK_TITLES.get(task, task)}")
        lines.append("")
        detail = detail_bullets(best["detail"])
        if detail:
            lines.append("Powody niepowodzenia / uwagi:")
            for item in detail:
                lines.append(f"- {item}")
            lines.append("")
        if behavior["texts"]:
            lines.append(f"Last message: _{snippet(behavior['texts'][-1])}_")
        elif behavior["events_bytes"] == 0:
            lines.append("_No events at all — the model never started within the "
                         "limit (0 bytes in the stream)._")
        if behavior["api_errors"]:
            lines.append(f"API errors: {behavior['api_errors']}.")
        if behavior["tool_errors"]:
            lines.append("Tool errors: " + tool_summary(behavior["tool_errors"], None))
        lines.append("")
        lines.append(f"Artefakty: `{best.get('run_dir')}/` · workspace: "
                     f"`{best.get('workspace')}`")
        lines.append("")

    if ab_runs:
        lines.append("**A/B z instrukcjami tool-use:**")
        for r in sorted(ab_runs, key=lambda r: r["task"]):
            lines.append(
                f"- `{r['task']}`: {status_cell(r)}, score {r['score']:.2f}, "
                f"{r['tool_calls']} tool calls, {fmt(r['duration_s'])}")
        lines.append("")

    if smoke_runs:
        smoke = max(smoke_runs, key=lambda r: (r["passed"], r["score"]))
        status = analyze.status_of(smoke)
        lines.append(
            f"**Prescreen (smoke):** {STATUS_LABEL.get(status, status)}, "
            f"score {smoke['score']:.2f}, {smoke['tool_calls']} tool calls, "
            f"{fmt(smoke['duration_s'])}")
        lines.append("")

    lines.append("</details>")
    lines.append("")
    return lines


def prescreen_only_section(model, entry, smoke_record, meta):
    lines = []
    lines.append(f"### `{model}`")
    lines.append("")
    lines.append(f"**Prescreen verdict:** {entry['verdict']} — {entry['reason']}")
    lines.append("")
    lines.append(f"**Metrics:** {meta_line(model, meta)}")
    lines.append("")
    if smoke_record:
        behavior = run_behavior(smoke_record.get("run_dir"))
        status = analyze.status_of(smoke_record)
        lines.append(
            f"**Smoke:** {STATUS_LABEL.get(status, status)} · score "
            f"{smoke_record['score']:.2f} · {smoke_record['tool_calls']} tool calls · "
            f"{fmt(smoke_record['duration_s'])} · out-tokens "
            f"{smoke_record['tokens']['output']:,}")
        lines.append("")
        if behavior["texts"]:
            lines.append(f"Last message: _{snippet(behavior['texts'][-1])}_")
            lines.append("")
        elif behavior["events_bytes"] == 0:
            lines.append("_No events: the model could not start._")
            lines.append("")
        if behavior["api_errors"]:
            lines.append(f"API errors: {behavior['api_errors']}.")
            lines.append("")
    lines.append("")
    return lines


# ------------------------------------------------------------------- report

def build_report(scored, smoke, ab, prescreen_entries, meta, floors):
    models = sorted({r["model"] for r in scored})
    smoke_by_model = {}
    for r in smoke:
        smoke_by_model.setdefault(r["model"], []).append(r)
    ab_by_model = {}
    for r in ab:
        ab_by_model.setdefault(r["model"], []).append(r)
    prescreen_by_model = {e["model"]: e for e in prescreen_entries}

    lines = []
    hosted = [m for m in models if m in meta and meta[m].get("hosted")]
    local = [m for m in models if m not in hosted]
    lines.append("# model-arena — detailed per-model report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"Models in the full sweep: **{len(models)}** "
                 f"({len(local)} local ollama + {len(hosted)} hosted "
                 f"opencode Zen) · scored runs: **{len(scored)}** · "
                 f"prescreened models: **{len(prescreen_entries)}** · "
                 f"A/B runs: **{len(ab)}**")
    lines.append("")

    # how to read
    lines.append("## How to read this report")
    lines.append("")
    lines.append("- **Verdict** is the decision from `roster.py`: qualified (uses "
                 "tools) or excluded (with reason and evidence).")
    lines.append("- **Run status**: `PASS` = task passed; the other labels "
                 "describe the failure mode:")
    lines.append("  - `worked` — the model really used tools, but the result was wrong;")
    lines.append("  - `prose-only` — answered in prose, never called a tool;")
    lines.append("  - `fake tool call (as text)` — printed the tool call as text "
                 "(e.g. `{\"type\":\"write\",...}`), nothing happened;")
    lines.append("  - `no action` — neither tools nor text;")
    lines.append("  - `timeout` — exceeded the time limit (0 tokens = never started);")
    lines.append("  - `no tool support` — ollama rejects the model for tool calls.")
    lines.append("- **Score** compares against the baseline floor (below): the "
                 "starter passes part of the hidden tests, so \"doing nothing\" "
                 "does not score 0.")
    lines.append("- `<details>` sections expand the run: grading reasons, the "
                 "model's last message, and paths to raw data.")
    lines.append("")

    lines.append("### Baseline floors (score for doing nothing)")
    lines.append("")
    lines.append("| task | floor |")
    lines.append("|---|---|")
    for task in sorted(floors.keys(),
                       key=lambda t: (TASK_ORDER + NEW_TASK_ORDER).index(t)
                       if t in TASK_ORDER + NEW_TASK_ORDER else 99):
        lines.append(f"| `{task}` | {floors[task]:.2f} |")
    lines.append("")

    # summary table
    lines.append("## Summary table")
    lines.append("")
    lines.append("| # | model | avg score | passes | used tools | median | verdict |")
    lines.append("|---|---|---|---|---|---|---|")
    rows = []
    for model in models:
        runs = [r for r in scored if r["model"] == model]
        avg = statistics.mean([r["score"] for r in runs])
        passed = sum(1 for r in runs if r["passed"])
        acted = sum(1 for r in runs if r["tool_calls"] > 0)
        median = statistics.median([r["duration_s"] for r in runs])
        verdict, _rule, _ev = roster.decide(model, runs,
                                            ab_by_model.get(model, []))
        rows.append((verdict == "QUALIFIED", passed, avg, model, acted,
                     len(runs), median, verdict))
    rows.sort(key=lambda r: (-r[0], -r[1], -r[2]))
    for i, (qualified, passed, avg, model, acted, total, median, verdict) in \
            enumerate(rows, start=1):
        lines.append(f"| {i} | `{model}` | {avg:.2f} | {passed}/{total} | "
                     f"{acted}/{total} | {fmt(median)} | {verdict} |")
    lines.append("")

    # qualified sections
    lines.append("---")
    lines.append("")
    lines.append("## Qualified models — full picture")
    lines.append("")
    qualified_models = [model for model in models
                        if roster.decide(model, [r for r in scored if r["model"] == model],
                                         ab_by_model.get(model, []))[0] == "QUALIFIED"]
    qualified_models.sort(key=lambda m: (
        -sum(1 for r in scored if r["model"] == m and r["passed"]),
        -statistics.mean([r["score"] for r in scored if r["model"] == m])))
    for model in qualified_models:
        runs = [r for r in scored if r["model"] == model]
        verdict, _rule, evidence = roster.decide(model, runs, ab_by_model.get(model, []))
        lines += model_section(model, runs, meta, verdict, evidence,
                               ab_by_model.get(model, []),
                               smoke_by_model.get(model, []))
        lines.append("---")
        lines.append("")

    # excluded sections
    lines.append("## Excluded models — full picture")
    lines.append("")
    excluded_models = [model for model in models if model not in qualified_models]
    rules = {}
    for model in excluded_models:
        runs = [r for r in scored if r["model"] == model]
        verdict, rule, evidence = roster.decide(model, runs,
                                                ab_by_model.get(model, []))
        rules[model] = (rule, evidence)
    excluded_models.sort(key=lambda m: (rules[m][0], m))
    for model in excluded_models:
        runs = [r for r in scored if r["model"] == model]
        rule, evidence = rules[model]
        lines += model_section(model, runs, meta, "EXCLUDED", f"{rule}: {evidence}",
                               ab_by_model.get(model, []),
                               smoke_by_model.get(model, []))
        lines.append("---")
        lines.append("")

    # prescreen-only
    swept = set(models)
    prescreen_only = [e for e in prescreen_entries
                      if e["model"] not in swept]
    if prescreen_only:
        lines.append("## Prescreen-only models (no full sweep)")
        lines.append("")
        lines.append("They passed the `smoke` task (read a file, sum it, write the "
                     "answer) or were rejected cheaply.")
        lines.append("")
        for entry in sorted(prescreen_only, key=lambda e: (e["verdict"], e["model"])):
            smoke_record = None
            for r in smoke:
                if r["model"] == entry["model"]:
                    if smoke_record is None or r["score"] > smoke_record["score"]:
                        smoke_record = r
            lines += prescreen_only_section(entry["model"], entry, smoke_record, meta)
        lines.append("---")
        lines.append("")

    # raw data pointers
    lines.append("## Where to find raw data")
    lines.append("")
    lines.append("- `results/<timestamp>__<task>__<model>/events.jsonl` — the full "
                 "opencode event stream (turns, tools, texts);")
    lines.append("- `.../record.json` — run metrics (tokens, times, tamper-check);")
    lines.append("- `.../grade/result.json` — the grader verdict, broken down per case;")
    lines.append("- `.../stderr.log` — container stderr (e.g. `Killed` = SIGKILL "
                 "past the limit);")
    lines.append("- run workspace: the path in the details section (default "
                 "`/tmp/model-arena/...` — gone after a host reboot).")
    lines.append("")
    lines.append("Summary reports: `results/report.md`, `results/analysis.md`, "
                 "`results/roster.md`, `results-prescreen/prescreen.md`, "
                 "`results-prescreen2/prescreen.md`.")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--prescreen", default=str(ROOT / "results-prescreen")
                    + "," + str(ROOT / "results-prescreen2"))
    ap.add_argument("--ab", default=str(ROOT / "results-ab"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    scored, smoke = load_runs([Path(args.results)])
    ab, _ = load_runs([Path(args.ab)])
    # smoke records live inside the prescreen result dirs
    prescreen_smoke = []
    prescreen_entries = []
    seen = set()
    for dir_arg in args.prescreen.split(","):
        directory = Path(dir_arg.strip())
        _s, smoke_records = load_runs([directory])
        prescreen_smoke += smoke_records
        for entry in roster.load_prescreen(directory / "prescreen.md"):
            if entry["model"] not in seen:
                seen.add(entry["model"])
                prescreen_entries.append(entry)
    smoke += prescreen_smoke

    models = sorted({r["model"] for r in scored} |
                    {e["model"] for e in prescreen_entries})
    meta = fetch_ollama_meta(models)
    floors = baseline_floors(scored)

    report = build_report(scored, smoke, ab, prescreen_entries, meta, floors)
    out_path = Path(args.out) if args.out else Path(args.results) / "models-report.md"
    out_path.write_text(report)
    print(f"models: {len(models)}  scored runs: {len(scored)}  "
          f"smoke runs: {len(smoke)}  ab runs: {len(ab)}")
    print(f"report: {out_path}")


if __name__ == "__main__":
    main()
