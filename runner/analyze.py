#!/usr/bin/env python3
"""Aggregate arena records into a human report.

Reads every results/*/record.json (a run), groups by model and task, and
answers: how long each model took, whether it actually did the work
(tool calls / files changed / finished vs timeout), and how well it scored.

Usage: python3 runner/analyze.py [--results DIR] [--out FILE]
"""

import argparse
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TOOL_TEXT_PATTERN = re.compile(
    r"\[Tool Call"                                                  # [Tool Call: ...]
    r'|\\?"type\\?"\s*:\s*\\?"(todowrite|write|read|edit|bash|glob|grep|task|webfetch|function)\\?"'
    r'|\\?"filePath\\?"\s*:|\\?"todos\\?"\s*:\s*\[',
    re.IGNORECASE)


def hallucinated_tool_text(rec) -> bool:
    """Model printed a tool call as text instead of calling the tool."""
    if rec.get("tool_calls", 0) > 0 or rec.get("timed_out"):
        return False
    run_dir = rec.get("run_dir")
    if not run_dir:
        return False
    events = Path(run_dir) / "events.jsonl"
    try:
        text = events.read_text(errors="replace")
    except OSError:
        return False
    if "does not support tools" in text:
        return False
    return bool(TOOL_TEXT_PATTERN.search(text))


def weird_filenames(rec):
    """Files created with control characters in the name (model's own bug)."""
    run_dir = rec.get("workspace")
    if not run_dir:
        return []
    found = []
    for path in Path(run_dir).rglob("*"):
        if any(c in path.name for c in ("\n", "\r", "\t")):
            found.append(path.name)
    return found


def load_records(results: Path):
    """Latest run per (model, task); `smoke` is a prescreen artifact."""
    latest = {}
    for record_path in sorted(results.glob("*/record.json")):
        try:
            record = json.loads(record_path.read_text())
        except json.JSONDecodeError:
            continue
        if record.get("task") == "smoke":
            continue  # prescreen artifact, not a scored competition task
        key = (record["model"], record["task"])
        finished = record.get("finished_at") or ""
        if key not in latest or finished > (latest[key].get("finished_at") or ""):
            latest[key] = record
    return list(latest.values())


def is_unsupported(rec) -> bool:
    """Ollama rejected the model: it cannot do tool calls at all."""
    if rec.get("tool_calls", 0) > 0 or rec.get("timed_out"):
        return False
    run_dir = rec.get("run_dir")
    if not run_dir:
        return False
    events = Path(run_dir) / "events.jsonl"
    try:
        text = events.read_text(errors="replace")
    except OSError:
        return False
    return "does not support tools" in text


def produced_text(rec) -> bool:
    run_dir = rec.get("run_dir")
    if not run_dir:
        return False
    events = Path(run_dir) / "events.jsonl"
    try:
        text = events.read_text(errors="replace")
    except OSError:
        return False
    return '"type":"text"' in text or '"type": "text"' in text


def status_of(rec) -> str:
    if rec.get("timed_out"):
        return "TIMEOUT"
    if is_unsupported(rec):
        return "UNSUPPORTED"
    if rec.get("exit_code") not in (0, None):
        return f"ERROR({rec.get('exit_code')})"
    if rec.get("tool_calls", 0) == 0:
        if hallucinated_tool_text(rec):
            return "TOOL-TEXT"
        if produced_text(rec):
            return "TEXT-ONLY"
        return "NO-ACTION"
    return "finished"


def did_work(rec) -> bool:
    return rec.get("tool_calls", 0) > 0


def fmt_secs(seconds) -> str:
    if seconds is None:
        return "-"
    seconds = float(seconds)
    if seconds >= 60:
        return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
    return f"{seconds:.0f}s"


def build_report(records):
    models = sorted({r["model"] for r in records})
    tasks = sorted({r["task"] for r in records})

    md = ["# model-arena — full local run", ""]
    md.append(f"Models: **{len(models)}**, tasks: **{len(tasks)}**, runs: **{len(records)}**")
    md.append("")

    # Baseline: score a model gets by doing nothing. The hidden suites include
    # cases the untouched starter already satisfies (visible behavior), so
    # "did nothing" is not score 0.
    baselines = {}
    for task in tasks:
        scores = [r["score"] for r in records
                  if r["task"] == task and r["tool_calls"] == 0 and not r["timed_out"]]
        if scores:
            baselines[task] = min(scores)
    if baselines:
        md.append("## 0. TL;DR")
        md.append("")
        md.append(f"- **Passes: {sum(1 for r in records if r['passed'])}/{len(records)} runs, "
                  f"{len({r['model'] for r in records if r['passed']})}/{len(models)} models.** "
                  f"Only `gemma4-200k:latest` completed a task (`ledger`).")
        acted = [r for r in records if did_work(r)]
        md.append(f"- **{len(acted)}/{len(records)} runs actually used tools.** "
                  f"The rest answered with prose, printed fake tool calls, or timed out.")
        md.append("- **Baseline warning**: the starter already passes part of every hidden suite, "
                  "so a model that does *nothing* scores about "
                  + ", ".join(f"`{t}` {s:.2f}" for t, s in sorted(baselines.items()))
                  + ". Compare scores against those floors, not against 0.")
        md.append("- Models bigger than VRAM (26b/31b/35b on 12 GB) never finished a single "
                  "turn in 7 minutes: all their runs hit the timeout with 0 tokens.")
        md.append("- Ollama's `tools` capability flag is necessary but not sufficient: "
                  "llama3.1/mistral/ornith advertise it and still never emit a real tool call.")
        md.append("")

    md.append(
        "Legend: cell shows `score · duration`. Statuses when not PASS:\n"
        "`fail` = worked (used tools) but wrong result; "
        "`TO` = hit the time limit; "
        "`UNSUP` = ollama rejects the model: no tool-call support; "
        "`TEXT-ONLY` = model answered with prose, never called a tool; "
        "`TOOL-TEXT` = model wrote the tool call as text instead of calling it; "
        "`NO-ACTION` = no tool call and no text; `-` = not run.")
    md.append("")

    md.append("## 1. Model x task matrix")
    md.append("")
    md.append("| model | " + " | ".join(tasks) + " | avg score |")
    md.append("|" + "---|" * (len(tasks) + 2))
    for model in models:
        cells = []
        for task in tasks:
            runs = [r for r in records if r["model"] == model and r["task"] == task]
            if not runs:
                cells.append("-")
                continue
            best = max(runs, key=lambda r: (r["passed"], r["score"]))
            status = status_of(best)
            label = "PASS" if best["passed"] else {
                "TIMEOUT": "TO", "UNSUPPORTED": "UNSUP",
                "NO-ACTION": "NO-ACTION", "TOOL-TEXT": "TOOL-TEXT",
            }.get(status, "fail")
            cells.append(f"{label} {best['score']:.2f} · {fmt_secs(best['duration_s'])}")
        scores = [r["score"] for r in records if r["model"] == model]
        avg = statistics.mean(scores) if scores else 0.0
        md.append(f"| {model} | " + " | ".join(cells) + f" | **{avg:.2f}** |")
    md.append("")

    md.append("## 2. Per-model summary")
    md.append("")
    md.append("`acted` = used at least one tool. `prose-only` = never called a tool "
              "(TEXT-ONLY + TOOL-TEXT + NO-ACTION). `TO` = timeout.")
    md.append("")
    md.append("| model | avg score | passed | acted | prose-only | TO | unsupported | "
              "total time | median/task | out-tokens | tool calls | tool errors |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    rows = []
    for model in models:
        runs = [r for r in records if r["model"] == model]
        scores = [r["score"] for r in runs]
        avg = statistics.mean(scores) if scores else 0.0
        passed = sum(1 for r in runs if r["passed"])
        acted = sum(1 for r in runs if did_work(r))
        prose_only = sum(1 for r in runs
                         if status_of(r) in ("TEXT-ONLY", "TOOL-TEXT", "NO-ACTION"))
        timeouts = sum(1 for r in runs if r["timed_out"])
        unsupported = sum(1 for r in runs if is_unsupported(r))
        total_time = sum(r["duration_s"] for r in runs)
        median_time = statistics.median([r["duration_s"] for r in runs]) if runs else 0
        out_tok = sum(r["tokens"]["output"] for r in runs)
        tools = sum(r["tool_calls"] for r in runs)
        tool_err = sum(r["tool_errors"] for r in runs)
        rows.append((avg, model, passed, acted, timeouts, median_time))
        md.append(
            f"| {model} | **{avg:.2f}** | {passed}/{len(runs)} | {acted}/{len(runs)} | "
            f"{prose_only}/{len(runs)} | {timeouts} | {unsupported} | "
            f"{fmt_secs(total_time)} | {fmt_secs(median_time)} | {out_tok} | "
            f"{tools} | {tool_err} |")
    md.append("")

    md.append("### Failure-mode breakdown")
    md.append("")
    md.append("| model | worked (tools) | TEXT-ONLY | TOOL-TEXT | NO-ACTION | TIMEOUT | UNSUPPORTED |")
    md.append("|---|---|---|---|---|---|---|")
    for model in models:
        runs = [r for r in records if r["model"] == model]
        counts = {}
        for status in ("finished", "TEXT-ONLY", "TOOL-TEXT", "NO-ACTION",
                       "TIMEOUT", "UNSUPPORTED"):
            counts[status] = sum(1 for r in runs if status_of(r) == status)
        md.append(
            f"| {model} | {counts['finished']} | {counts['TEXT-ONLY']} | "
            f"{counts['TOOL-TEXT']} | {counts['NO-ACTION']} | "
            f"{counts['TIMEOUT']} | {counts['UNSUPPORTED']} |")
    md.append("")

    md.append("## 3. Ranking by average score")
    md.append("")
    md.append("| # | model | avg score | pass rate | acted | median task time |")
    md.append("|---|---|---|---|---|---|")
    for i, (avg, model, passed, acted, timeouts, median_time) in enumerate(
                sorted(rows, key=lambda x: (-x[0], x[5])), start=1):
        n = len([r for r in records if r["model"] == model])
        md.append(f"| {i} | {model} | {avg:.2f} | {passed}/{n} | {acted}/{n} | "
                  f"{fmt_secs(median_time)} |")
    md.append("")

    md.append("## 4. Difficulty per task")
    md.append("")
    md.append("| task | avg score | passed | timeouts | no-action | median time |")
    md.append("|---|---|---|---|---|---|")
    for task in tasks:
        runs = [r for r in records if r["task"] == task]
        avg = statistics.mean([r["score"] for r in runs]) if runs else 0.0
        passed = sum(1 for r in runs if r["passed"])
        timeouts = sum(1 for r in runs if r["timed_out"])
        no_action = sum(1 for r in runs if not did_work(r))
        median_time = statistics.median([r["duration_s"] for r in runs]) if runs else 0
        md.append(f"| {task} | {avg:.2f} | {passed}/{len(runs)} | {timeouts} | "
                  f"{no_action} | {fmt_secs(median_time)} |")
    md.append("")

    md.append("## 4b. Passes by difficulty tier")
    md.append("")
    tiers = ["basic", "easy", "medium", "hard"]
    tier_tasks = {}
    for task in tasks:
        meta_file = ROOT / "tasks" / task / "meta.json"
        try:
            tier = json.loads(meta_file.read_text()).get("difficulty", "?")
        except (OSError, json.JSONDecodeError):
            tier = "?"
        tier_tasks.setdefault(tier, []).append(task)
    md.append("| tier | tasks | pass rate (models) | pass rate (runs) |")
    md.append("|---|---|---|---|")
    for tier in tiers:
        tier_runs = [r for r in records if r["task"] in tier_tasks.get(tier, [])]
        if not tier_runs:
            md.append(f"| {tier} | {', '.join(tier_tasks.get(tier, [])) or '-'} "
                      f"| - | - |")
            continue
        models_passed = {r["model"] for r in tier_runs if r["passed"]}
        models_total = {r["model"] for r in tier_runs}
        passed_runs = sum(1 for r in tier_runs if r["passed"])
        md.append(f"| {tier} | {', '.join(tier_tasks.get(tier, []))} "
                  f"| {len(models_passed)}/{len(models_total)} "
                  f"| {passed_runs}/{len(tier_runs)} |")
    md.append("")

    md.append("## 5. All runs (chronological)")
    md.append("")
    md.append("| model | task | status | score | duration | out-tok | tools | detail |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(records, key=lambda r: (r["model"], r["task"])):
        md.append(
            f"| {r['model']} | {r['task']} | {status_of(r)} | "
            f"{'PASS' if r['passed'] else 'fail'} {r['score']:.2f} | "
            f"{fmt_secs(r['duration_s'])} | {r['tokens']['output']} | "
            f"{r['tool_calls']} | {str(r['detail'])[:150].replace('|', '/')} |")
    md.append("")

    md.append("## 6. Diagnostics")
    md.append("")
    weird = [(r["model"], r["task"], weird_filenames(r)) for r in records
             if weird_filenames(r)]
    if weird:
        md.append("Files created with control characters in the name "
                  "(the model's own bug; graders run the correctly-named file):")
        md.append("")
        for model, task, names in weird:
            md.append(f"- `{model}` / `{task}`: {[repr(n) for n in names]}")
        md.append("")
    unsupported = sorted({r["model"] for r in records if is_unsupported(r)})
    if unsupported:
        md.append(f"Models ollama refuses to run with tools: {', '.join('`' + m + '`' for m in unsupported)}")
        md.append("")
    text_only = [m for m in sorted({r["model"] for r in records})
                 if all(status_of(r) in ("TEXT-ONLY", "UNSUPPORTED", "NO-ACTION")
                        for r in records if r["model"] == m)]
    if text_only:
        md.append("Models that never produced a tool call in any run "
                  "(prose-only or unsupported): "
                  + ", ".join("`" + m + "`" for m in text_only))
        md.append("")
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    results = Path(args.results)
    records = load_records(results)
    if not records:
        raise SystemExit(f"no records found under {results}")

    report = build_report(records)
    out_path = Path(args.out) if args.out else results / "analysis.md"
    out_path.write_text(report)

    models = {r["model"] for r in records}
    print(f"records: {len(records)}  models: {len(models)}")
    print(f"analysis: {out_path}")
    print()
    lines = report.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## 3."))
    print("\n".join(lines[start:start + 25]))


if __name__ == "__main__":
    main()
