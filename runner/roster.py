#!/usr/bin/env python3
"""Build the competition roster: who qualifies, who is excluded and why.

Reads results/ (main sweep) and optionally results-ab/ (tool-instruction A/B),
applies evidence-based exclusion rules, and writes results/roster.md.

Exclusion rules (in order):
  1. no-tool-support   - ollama rejects the model with tools at all
  2. tool-hallucinator - never emitted a real tool call in ANY run
  3. too-big-for-hw    - repeated timeouts with no output on tested hardware
  4. ab-unfixable      - the tool-use instructions did not fix rule 2 or 3

Usage: python3 runner/roster.py [--results DIR] [--ab DIR]
"""

import argparse
import json
import statistics
from pathlib import Path

import reporting

ROOT = Path(__file__).resolve().parent.parent


def load(results: Path):
    """Latest valid run per (model, task); smoke is a prescreen artifact."""
    return reporting.load_records([results])


def task_difficulty(tasks_dir: Path, task: str) -> str:
    """Difficulty tier from the task's meta.json (basic/easy/medium/hard)."""
    meta_file = tasks_dir / task / "meta.json"
    try:
        meta = json.loads(meta_file.read_text())
        return meta.get("difficulty", "?") if isinstance(meta, dict) else "?"
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "?"


def has_unsupported(records):
    return any(reporting.error_category(r) == "PROVIDER_ERROR" for r in records)


def weird_filenames(rec):
    run_dir = rec.get("workspace")
    if not run_dir:
        return []
    p = Path(run_dir)
    if not p.exists():
        return []
    return [f.name for f in p.rglob("*")
            if any(c in f.name for c in ("\n", "\r", "\t"))]


def summarize(records):
    from analyze import status_of
    valid = reporting.quality_records(records)
    n = len(records)
    acted = sum(1 for r in valid if r["tool_calls"] > 0)
    passed = sum(1 for r in valid if status_of(r) == "PASS")
    timeouts = sum(1 for r in valid if r["timed_out"])
    zero_token = sum(1 for r in valid
                     if r["timed_out"] and r["tokens"]["output"] == 0)
    return {
        "runs": n, "valid": len(valid), "invalid": n - len(valid),
        "acted": acted, "passed": passed,
        "timeouts": timeouts, "zero_token_timeouts": zero_token,
        "statuses": {s: sum(1 for r in records if status_of(r) == s)
                     for s in ("PASS", "FAIL", "TEXT-ONLY", "TOOL-TEXT",
                               "NO-ACTION", "TIMEOUT", "AGENT_ERROR",
                               "PROVIDER_ERROR", "API_ERROR", "RUNNER_ERROR",
                               "GRADER_ERROR")},
    }


def decide(model, records, ab_records):
    """Return (verdict, rule, evidence)."""
    valid = reporting.quality_records(records)
    if not valid:
        categories = sorted({reporting.error_category(r) for r in records
                             if reporting.error_category(r)})
        label = ", ".join(categories) or "no valid records"
        return ("ERROR", "infrastructure-error",
                f"0/{len(records)} valid attempts ({label}); quality not evaluated")
    s = summarize(valid)
    if s["acted"] == 0 and s["passed"] == 0:
        # distinguish "too big" (nothing produced) from "prose/hallucination"
        if s["zero_token_timeouts"] >= max(1, s["runs"] - 1):
            ev = (f"{s['zero_token_timeouts']}/{s['runs']} valid runs timed out "
                  "with 0 output tokens")
            if ab_records:
                ab_acted = sum(1 for r in ab_records if r["tool_calls"] > 0)
                ev += f"; with tool-use instructions still {ab_acted}/{len(ab_records)} acted"
            return ("EXCLUDED", "too-big-for-hardware", ev)
        ev = f"0 tool calls in {s['runs']}/{s['runs']} runs: " + \
             f"{s['statuses']['TEXT-ONLY']}x prose-only, " \
             f"{s['statuses']['TOOL-TEXT']}x fake tool call, " \
             f"{s['statuses']['NO-ACTION']}x empty"
        if ab_records:
            ab_acted = sum(1 for r in ab_records if r["tool_calls"] > 0)
            if ab_acted == 0:
                ev += (f"; tool-use instructions changed nothing "
                       f"(0/{len(ab_records)} acted)")
            else:
                ev += (f"; instructions got {ab_acted}/{len(ab_records)} acting "
                       f"but still 0 passes")
        return ("EXCLUDED", "tool-hallucinator", ev)
    if s["timeouts"] >= max(1, s["runs"] * 0.8) and s["passed"] == 0:
        return ("EXCLUDED", "too-slow-for-hardware",
                f"{s['timeouts']}/{s['runs']} valid runs timed out")
    note = ""
    if s["passed"] > 0:
        note = f"{s['passed']}/{s['runs']} passed"
    else:
        note = f"{s['acted']}/{s['runs']} acted but 0 passes"
    return ("QUALIFIED", "agentic", note)


def load_prescreen(path: Path):
    """Read prescreen entries, if a report exists."""
    if not path.exists():
        return []
    entries = []
    current = None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            verdict = line[3:].split(" ")[0].strip()
            if verdict in ("QUALIFIED", "BORDERLINE", "EXCLUDED", "ERROR"):
                current = verdict
        elif line.startswith("| ollama/") and current:
            cells = [c.strip() for c in line.strip("|").split("|")]
            entries.append({"model": cells[0], "verdict": current,
                            "time": cells[1] if len(cells) > 1 else "-",
                            "tools": cells[2] if len(cells) > 2 else "-",
                            "reason": cells[4] if len(cells) > 4 else ""})
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "results"))
    ap.add_argument("--ab", default=str(ROOT / "results-ab"))
    ap.add_argument("--prescreen", default=str(ROOT / "results-prescreen"),
                    help="comma-separated prescreen result dirs")
    args = ap.parse_args()

    records = load(Path(args.results))
    ab = load(Path(args.ab))
    if not records:
        raise SystemExit("no records")

    models = sorted({r["model"] for r in records})
    required_tasks = sorted({r["task"] for r in records})
    qualified, excluded = [], []
    for model in models:
        recs = [r for r in records if r["model"] == model]
        ab_recs = [r for r in ab if r["model"] == model]
        verdict, rule, evidence = decide(model, recs, ab_recs)
        s = summarize(recs)
        entry = {"model": model, "verdict": verdict, "rule": rule,
                 "evidence": evidence, "summary": s}
        (qualified if verdict == "QUALIFIED" else excluded).append(entry)

    md = ["# model-arena roster — who moves to the next round", ""]
    local = [m for m in models if m.startswith("ollama/")]
    hosted = [m for m in models if not m.startswith("ollama/")]
    md.append(f"Evaluated **{len(models)} models** ({len(local)} local ollama + "
              f"{len(hosted)} hosted models) across the observed task suite "
              f"({len(records)} runs) and the tool-use instruction A/B "
              f"({len(ab)} runs).")
    md.append("")
    md.append("Infrastructure failures are reported separately and do not count "
              "as model-quality results. For each model/task, the latest valid "
              "attempt is preferred over a later invalid retry.")
    md.append("")

    md.append(f"## Qualified ({len(qualified)})")
    md.append("")
    md.append("| model | valid coverage | ranking status | runs acted | passes | valid avg | median time | note |")
    md.append("|---|---|---|---|---|---|---|---|")
    for e in sorted(qualified, key=lambda e: -e["summary"]["passed"]):
        recs = [r for r in records if r["model"] == e["model"]]
        valid = reporting.quality_records(recs)
        comparable = reporting.comparable_records(recs)
        avg = sum(r["score"] for r in valid) / len(valid)
        coverage = len({r["task"] for r in valid})
        comparable_coverage = len({r["task"] for r in comparable})
        if comparable_coverage == len(required_tasks):
            ranking_status = "complete"
        elif comparable_coverage:
            ranking_status = "PROVISIONAL"
        else:
            ranking_status = "LEGACY"
        times = sorted(r["duration_s"] for r in recs)
        med = statistics.median(times)
        md.append(f"| {e['model']} | {coverage}/{len(required_tasks)} | {ranking_status} | "
                  f"{e['summary']['acted']}/{e['summary']['valid']} valid | "
                  f"{e['summary']['passed']} | {avg:.2f} | {med:.0f}s | {e['evidence']} |")
    md.append("")

    md.append("### Passes by task difficulty")
    md.append("")
    tiers = ["basic", "easy", "medium", "hard"]
    tasks_dir = ROOT / "tasks"
    scored_tasks = sorted({r["task"] for r in records})
    by_tier = {tier: sorted(t for t in scored_tasks
                            if task_difficulty(tasks_dir, t) == tier)
               for tier in tiers}
    md.append("| model | " + " | ".join(tiers) + " |")
    md.append("|" + "---|" * (len(tiers) + 1))
    for e in sorted(qualified, key=lambda e: -e["summary"]["passed"]):
        cells = []
        for tier in tiers:
            tier_runs = [r for r in records if r["model"] == e["model"]
                         and r["task"] in by_tier[tier]]
            if not tier_runs:
                cells.append("-")
            else:
                cells.append(f"{sum(1 for r in tier_runs if r['passed'])}"
                              f"/{len(tier_runs)}")
        md.append(f"| {e['model']} | " + " | ".join(cells) + " |")
    md.append("")
    md.append("Tasks by tier: "
              + "; ".join(
                  f"`{tier}`: "
                  + (", ".join(f"`{t}`" for t in by_tier[tier])
                     if by_tier[tier] else "(none)")
                  for tier in tiers)
              + ".")
    md.append("")

    md.append(f"## Excluded ({len(excluded)})")
    md.append("")
    md.append("| model | reason | evidence |")
    md.append("|---|---|---|")
    labels = {
        "no-tool-support": "no tool support (ollama rejects)",
        "tool-hallucinator": "hallucinates tool calls / never uses tools",
        "too-big-for-hardware": "unresponsive on the tested hardware",
        "too-slow-for-hardware": "too slow for the time limit",
        "infrastructure-error": "infrastructure error (quality not evaluated)",
    }
    for e in sorted(excluded, key=lambda e: (e["rule"], e["model"])):
        md.append(f"| {e['model']} | {labels.get(e['rule'], e['rule'])} | {e['evidence']} |")
    md.append("")

    weird = [(r["model"], r["task"], weird_filenames(r)) for r in records
             if weird_filenames(r)]
    if weird:
        md.append("## Diagnostics")
        md.append("")
        for model, task, names in weird:
            md.append(f"- `{model}` / `{task}`: files with control characters "
                      f"in the name: {[repr(n) for n in names]}")
        md.append("")

    prescreen = []
    seen_models = set()
    for dir_arg in args.prescreen.split(","):
        dir_path = Path(dir_arg.strip())
        for entry in load_prescreen(dir_path / "prescreen.md"):
            if entry["model"] not in seen_models:
                seen_models.add(entry["model"])
                prescreen.append(entry)
    if prescreen:
        already = {e["model"] for e in qualified + excluded}
        new_entries = [e for e in prescreen if e["model"] not in already]
        md.append(f"## Prescreen of new models ({len(prescreen)} checked)")
        md.append("")
        md.append("Task `smoke` (sum numbers from a file), one run per model. "
                  "Models not yet tested by the full sweep.")
        md.append("")
        swept = {e["model"] for e in qualified + excluded}
        md.append("| model | verdict | time | tool calls | full sweep | reason |")
        md.append("|---|---|---|---|---|---|")
        for e in prescreen:
            full = "yes" if e["model"] in swept else "no"
            md.append(f"| {e['model']} | {e['verdict']} | {e['time']} | "
                      f"{e['tools']} | {full} | {e['reason'][:140]} |")
        md.append("")
        passed = [e["model"] for e in prescreen
                  if e["verdict"] in ("QUALIFIED", "BORDERLINE")]
        pending = [m for m in passed if m not in swept]
        md.append(f"Passed the prescreen: "
                  f"{', '.join('`' + m + '`' for m in passed) or '(nobody)'}"
                  + (f"; awaiting a full sweep: "
                     f"{', '.join('`' + m + '`' for m in pending)}" if pending else ""))
        md.append("")

    out = Path(args.results) / "roster.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
