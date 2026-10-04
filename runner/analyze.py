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

import reporting

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
    """Latest valid run per (model, task); smoke is a prescreen artifact."""
    return reporting.load_records([results])


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
    category = reporting.error_category(rec)
    if category:
        return category
    if rec.get("passed"):
        return "PASS"
    if rec.get("timed_out"):
        return "TIMEOUT"
    if rec.get("exit_code") not in (0, None):
        return "AGENT_ERROR"
    if rec.get("tool_calls", 0) == 0:
        if hallucinated_tool_text(rec):
            return "TOOL-TEXT"
        if produced_text(rec):
            return "TEXT-ONLY"
        return "NO-ACTION"
    return "FAIL"


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
    quality = reporting.quality_records(records)
    comparable = reporting.comparable_records(records)
    superseded_invalid = sum(len(r.get("_later_invalid", [])) for r in records)

    md = ["# model-arena - analysis", ""]
    md.append(f"Models: **{len(models)}**, required tasks: **{len(tasks)}**, "
              f"selected attempts: **{len(records)}**, valid quality runs: **{len(quality)}**, "
              f"current-suite comparable runs: **{len(comparable)}**, "
              f"later invalid retries: **{superseded_invalid}**")
    md.append("")
    md.append("Infrastructure failures (`PROVIDER_ERROR`, `API_ERROR`, `RUNNER_ERROR`, "
              "`GRADER_ERROR`) are invalid attempts: they are shown but excluded from "
              "quality averages and coverage. Selection uses the latest valid attempt; a "
              "later invalid retry does not replace it.")
    md.append("")
    baselines = reporting.explicit_baselines(ROOT / "tasks")
    if baselines:
        md.append("Canonical starter floors: " + ", ".join(
            f"`{task}` {score:.2f}" for task, score in sorted(baselines.items())))
    else:
        md.append("Canonical starter floors are not available. No floor is inferred from "
                  "provider failures or no-action model runs.")
    md.append("")

    md.append("## 1. Model x task matrix")
    md.append("")
    md.append("| model | " + " | ".join(tasks) + " | valid avg | coverage | status |")
    md.append("|" + "---|" * (len(tasks) + 4))
    for model in models:
        cells = []
        for task in tasks:
            runs = [r for r in records if r["model"] == model and r["task"] == task]
            if not runs:
                cells.append("-")
                continue
            run = runs[0]
            status = status_of(run)
            score = f" {run['score']:.2f}" if reporting.is_valid(run) else ""
            later = " (later invalid: " + ", ".join(run["_later_invalid"]) + ")" \
                if run.get("_later_invalid") else ""
            cells.append(f"{status}{score} · {fmt_secs(run['duration_s'])}{later}")
        model_quality = [r for r in quality if r["model"] == model]
        avg = statistics.mean(r["score"] for r in model_quality) if model_quality else None
        coverage = len({r["task"] for r in model_quality})
        model_comparable = [r for r in comparable if r["model"] == model]
        if model_comparable:
            comp_coverage = len({r["task"] for r in model_comparable})
            provisional = "complete" if comp_coverage == len(tasks) else "PROVISIONAL"
        else:
            provisional = "LEGACY"
        avg_text = f"**{avg:.2f}**" if avg is not None else "-"
        md.append(f"| {model} | " + " | ".join(cells)
                  + f" | {avg_text} | {coverage}/{len(tasks)} | {provisional} |")
    md.append("")

    md.append("## 2. Per-model summary")
    md.append("")
    md.append("`acted` = used at least one tool. `prose-only` = never called a tool "
              "(TEXT-ONLY + TOOL-TEXT + NO-ACTION). `TO` = timeout.")
    md.append("")
    md.append("| model | valid avg | coverage | passed | acted | invalid | TO | "
              "total time | median/task | out-tokens | tool calls | tool errors |")
    md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    rows = []
    for model in models:
        runs = [r for r in records if r["model"] == model]
        valid = [r for r in runs if reporting.is_valid(r)]
        avg = statistics.mean(r["score"] for r in valid) if valid else None
        passed = sum(1 for r in valid if status_of(r) == "PASS")
        acted = sum(1 for r in runs if did_work(r))
        timeouts = sum(1 for r in runs if r["timed_out"])
        total_time = sum(r["duration_s"] for r in runs)
        median_time = statistics.median([r["duration_s"] for r in runs]) if runs else 0
        out_tok = sum(r["tokens"]["output"] for r in runs)
        tools = sum(r["tool_calls"] for r in runs)
        tool_err = sum(r["tool_errors"] for r in runs)
        coverage = len({r["task"] for r in valid})
        rows.append((avg, model, passed, acted, median_time, coverage))
        md.append(
            f"| {model} | {f'{avg:.2f}' if avg is not None else '-'} | "
            f"{coverage}/{len(tasks)} | {passed}/{len(valid)} | {acted}/{len(runs)} | "
            f"{len(runs) - len(valid) + sum(len(r.get('_later_invalid', [])) for r in runs)} | "
            f"{timeouts} | "
            f"{fmt_secs(total_time)} | {fmt_secs(median_time)} | {out_tok} | "
            f"{tools} | {tool_err} |")
    md.append("")

    md.append("### Failure-mode breakdown")
    md.append("")
    statuses = ("PASS", "FAIL", "TEXT-ONLY", "TOOL-TEXT", "NO-ACTION", "TIMEOUT",
                "AGENT_ERROR", "PROVIDER_ERROR", "API_ERROR", "RUNNER_ERROR", "GRADER_ERROR")
    md.append("| model | " + " | ".join(statuses) + " |")
    md.append("|" + "---|" * (len(statuses) + 1))
    for model in models:
        runs = [r for r in records if r["model"] == model]
        counts = {status: sum(1 for r in runs if status_of(r) == status)
                  + sum(r.get("_later_invalid", []).count(status) for r in runs)
                  for status in statuses}
        md.append(f"| {model} | " + " | ".join(str(counts[s]) for s in statuses) + " |")
    md.append("")

    md.append("## 3. Primary ranking (complete required suite)")
    md.append("")
    comparable_rows = []
    for model in models:
        runs = [r for r in comparable if r["model"] == model]
        coverage = len({r["task"] for r in runs})
        if runs:
            comparable_rows.append((statistics.mean(r["score"] for r in runs), model,
                                    sum(status_of(r) == "PASS" for r in runs),
                                    statistics.median(r["duration_s"] for r in runs),
                                    coverage))
    complete = [row for row in comparable_rows if row[4] == len(tasks)]
    md.append(f"Only schema-v2 records from `{reporting.CURRENT_SUITE_ID}` with full "
              "provenance and complete task coverage are comparable here.")
    md.append("")
    md.append("| # | model | avg score | pass rate | median task time |")
    md.append("|---|---|---|---|---|")
    for i, (avg, model, passed, median_time, coverage) in enumerate(
            sorted(complete, key=lambda x: (-x[0], x[3])), start=1):
        md.append(f"| {i} | {model} | {avg:.2f} | {passed}/{len(tasks)} | "
                  f"{fmt_secs(median_time)} |")
    if not complete:
        md.append(f"| - | No model has {len(tasks)}/{len(tasks)} valid coverage | - | - | - |")
    md.append("")
    md.append("### Historical/provisional quality results")
    md.append("")
    md.append("| model | valid avg | coverage | passes |")
    md.append("|---|---|---|---|")
    for avg, model, passed, acted, median_time, coverage in sorted(
            rows,
            key=lambda x: (-x[5], -(x[0] if x[0] is not None else -1), x[1])):
        md.append(f"| {model} | {f'{avg:.2f}' if avg is not None else '-'} | "
                  f"{coverage}/{len(tasks)} | {passed}/{coverage} |")
    md.append("")

    md.append("## 4. Difficulty per task")
    md.append("")
    md.append("| task | avg score | passed | timeouts | no-action | median time |")
    md.append("|---|---|---|---|---|---|")
    for task in tasks:
        runs = [r for r in records if r["task"] == task]
        valid = [r for r in runs if reporting.is_valid(r)]
        avg = statistics.mean([r["score"] for r in valid]) if valid else None
        passed = sum(1 for r in valid if status_of(r) == "PASS")
        timeouts = sum(1 for r in runs if r["timed_out"])
        no_action = sum(1 for r in runs if not did_work(r))
        median_time = statistics.median([r["duration_s"] for r in runs]) if runs else 0
        md.append(f"| {task} | {f'{avg:.2f}' if avg is not None else '-'} | "
                  f"{passed}/{len(valid)} valid | {timeouts} | "
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
        tier_runs = [r for r in quality if r["task"] in tier_tasks.get(tier, [])]
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

    md.append("## 5. Selected attempts")
    md.append("")
    md.append("| model | task | status | score | duration | out-tok | tools | detail |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(records, key=lambda r: (r["model"], r["task"])):
        score_text = f"{r['score']:.2f}" if reporting.is_valid(r) else "-"
        md.append(
            f"| {r['model']} | {r['task']} | {status_of(r)} | "
            f"{'PASS' if status_of(r) == 'PASS' else 'fail'} "
            f"{score_text} | "
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
                 if all(status_of(r) in ("TEXT-ONLY", "TOOL-TEXT", "NO-ACTION",
                                         "PROVIDER_ERROR", "API_ERROR")
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
