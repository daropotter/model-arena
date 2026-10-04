"""Schema-safe record loading and methodology shared by arena reports."""

import json
import math
import os
import statistics
from pathlib import Path


ERROR_STATUSES = {"PROVIDER_ERROR", "API_ERROR", "RUNNER_ERROR", "GRADER_ERROR"}
CURRENT_SUITE_ID = os.environ.get("ARENA_SUITE_ID", "model-arena-v2")


def _number(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def normalize_record(record, record_path=None):
    """Return a safe copy of a historical record, or None if unidentifiable."""
    if not isinstance(record, dict):
        return None
    model, task = record.get("model"), record.get("task")
    if not isinstance(model, str) or not model or not isinstance(task, str) or not task:
        return None
    out = dict(record)
    out["model"], out["task"] = model, task
    out["passed"] = record.get("passed") is True
    out["score"] = max(0.0, min(1.0, _number(record.get("score"))))
    out["duration_s"] = max(0.0, _number(record.get("duration_s")))
    out["exit_code"] = record.get("exit_code")
    out["timed_out"] = record.get("timed_out") is True
    out["tool_calls"] = max(0, _integer(record.get("tool_calls")))
    out["tool_errors"] = max(0, _integer(record.get("tool_errors")))
    out["api_errors"] = max(0, _integer(record.get("api_errors")))
    out["detail"] = str(record.get("detail") or "")
    out["finished_at"] = str(record.get("finished_at") or "")
    out["tool_names"] = record.get("tool_names") if isinstance(record.get("tool_names"), dict) else {}
    tokens = record.get("tokens") if isinstance(record.get("tokens"), dict) else {}
    out["tokens"] = {name: max(0, _integer(tokens.get(name)))
                     for name in ("input", "output", "reasoning")}
    if record_path is not None:
        out["_record_path"] = str(record_path)
        out["_record_mtime"] = record_path.stat().st_mtime
    return out


def _artifact_file(record, name):
    record_path = record.get("_record_path")
    if record_path:
        return Path(record_path).parent / name
    run_dir = record.get("run_dir")
    return Path(run_dir) / name if run_dir else None


def event_errors(record):
    """Read structured API/provider errors without trusting event schemas."""
    path = _artifact_file(record, "events.jsonl")
    if path is None:
        return []
    errors = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return errors
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(event, dict) or event.get("type") != "error":
            continue
        error = event.get("error") if isinstance(event.get("error"), dict) else {}
        data = error.get("data") if isinstance(error.get("data"), dict) else {}
        errors.append((str(error.get("name") or ""), str(data.get("message") or error)))
    return errors


def error_category(record):
    """Classify infrastructure failures; None means quality is scoreable."""
    outcome = record.get("run_outcome")
    explicit = {
        "provider_error": "PROVIDER_ERROR",
        "api_error": "API_ERROR",
        "runner_error": "RUNNER_ERROR",
        "grader_error": "GRADER_ERROR",
    }
    if outcome in explicit:
        return explicit[outcome]
    if record.get("valid_for_quality") is False:
        return "RUNNER_ERROR"
    detail = record.get("detail", "").lower()
    if detail.startswith("runner error:"):
        return "RUNNER_ERROR"
    if detail.startswith("grader failed") or "grader error" in detail:
        return "GRADER_ERROR"
    # Legacy records did not carry run_outcome. Treat an event error as fatal
    # only when the agent produced no work; providers may emit recoverable
    # errors during an otherwise valid session.
    errors = event_errors(record)
    no_work = (record.get("tool_calls", 0) == 0
               and record.get("tokens", {}).get("output", 0) == 0)
    if errors and no_work:
        joined = " ".join(f"{name} {message}" for name, message in errors).lower()
        provider_markers = (
            "does not support tools", "freeusagelimit", "rate limit", "ratelimit",
            "quota", "authentication", "unauthorized", "forbidden", "provider",
            "unexpected server error", "model not found",
        )
        if any(marker in joined for marker in provider_markers):
            return "PROVIDER_ERROR"
        return "API_ERROR"
    # Old records may retain only the aggregate count.
    if record.get("api_errors", 0) and no_work:
        return "API_ERROR"
    return None


def status_of(record):
    """One precedence order used by every report."""
    category = error_category(record)
    if category:
        return category
    if record.get("passed"):
        return "PASS"
    if record.get("timed_out"):
        return "TIMEOUT"
    if record.get("exit_code") not in (0, None):
        return "AGENT_ERROR"
    if record.get("tool_calls", 0) == 0:
        return "NO_ACTION"
    return "FAIL"


def is_valid(record):
    return error_category(record) is None


def _sort_key(record):
    return (record.get("finished_at") or "", record.get("_record_mtime", 0),
            record.get("_record_path", ""))


def load_records(results_dirs, include_smoke=False):
    """Select latest valid (model, task) attempt, falling back to latest invalid.

    Later invalid attempts are retained as metadata on the selected copy; files
    on disk are never changed.
    """
    grouped = {}
    for directory in results_dirs:
        directory = Path(directory)
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*/record.json")):
            try:
                raw = json.loads(path.read_text())
                record = normalize_record(raw, path)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if record is None or (record["task"] == "smoke" and not include_smoke):
                continue
            grouped.setdefault((record["model"], record["task"]), []).append(record)

    selected = []
    for attempts in grouped.values():
        attempts.sort(key=_sort_key)
        valid = [record for record in attempts if is_valid(record)]
        candidate = valid[-1] if valid else attempts[-1]
        batch_id = candidate.get("batch_id")
        batch = ([record for record in valid if record.get("batch_id") == batch_id]
                 if batch_id and valid else [candidate])
        choice = dict(batch[-1])
        if len(batch) > 1:
            choice["score"] = statistics.mean(record["score"] for record in batch)
            choice["passed"] = all(record["passed"] for record in batch)
            choice["duration_s"] = statistics.median(
                record["duration_s"] for record in batch)
            choice["_repeat_scores"] = [record["score"] for record in batch]
            choice["_repeat_pass_rate"] = (
                sum(record["passed"] for record in batch) / len(batch))
        later = [record for record in attempts if _sort_key(record) > _sort_key(choice)
                 and not is_valid(record)]
        choice["_later_invalid"] = [error_category(record) for record in later]
        choice["_attempt_count"] = len(attempts)
        selected.append(choice)
    return selected


def split_smoke(records):
    return ([record for record in records if record["task"] != "smoke"],
            [record for record in records if record["task"] == "smoke"])


def quality_records(records):
    return [record for record in records if is_valid(record)]


def is_comparable(record, suite_id=CURRENT_SUITE_ID):
    provenance = record.get("provenance")
    required = {"task_digest", "starter_digest", "grader_digest",
                "prompt_digest", "runner_digest", "docker_digest"}
    return (is_valid(record) and record.get("schema_version") == 2
            and isinstance(provenance, dict)
            and provenance.get("suite_id") == suite_id
            and required.issubset(provenance))


def comparable_records(records, suite_id=CURRENT_SUITE_ID):
    return [record for record in records if is_comparable(record, suite_id)]


def provenance_matches(record, task_dir, suite_id=CURRENT_SUITE_ID):
    """True only when the stored hashes equal the current task files."""
    try:
        from . import arena as _arena
    except ImportError:
        import arena as _arena  # type: ignore
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        return False
    if provenance.get("suite_id") != suite_id:
        return False
    task_dir = Path(task_dir)
    expected = {
        "task_digest": _arena.tree_digest(task_dir),
        "starter_digest": _arena.tree_digest(task_dir / "starter"),
        "grader_digest": _arena.tree_digest(task_dir / "grader"),
        "prompt_digest": _arena.file_digest(task_dir / "prompt.md"),
    }
    return all(provenance.get(key) == value for key, value in expected.items())


def explicit_baselines(tasks_dir, results_dir=None):
    """Load canonical starter floors only; never infer them from model failures."""
    floors = {}
    candidates = []
    if results_dir is not None:
        candidates.append(Path(results_dir) / "baselines.json")
    candidates.append(Path(tasks_dir) / "baselines.json")
    for path in candidates:
        try:
            data = json.loads(path.read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            for task, value in data.items():
                if isinstance(task, str) and isinstance(value, (int, float)):
                    floors[task] = float(value)
    try:
        task_dirs = list(Path(tasks_dir).iterdir())
    except OSError:
        task_dirs = []
    for task_dir in task_dirs:
        try:
            meta = json.loads((task_dir / "meta.json").read_text())
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        value = meta.get("starter_score", meta.get("baseline_score")) if isinstance(meta, dict) else None
        if isinstance(value, (int, float)):
            floors[task_dir.name] = float(value)
    return floors


def relative_artifact(value, root, fallback=None):
    """Prefer a repository-relative artifact path in generated Markdown."""
    fallback_path = Path(fallback) if fallback else None
    if fallback_path is not None and fallback_path.exists():
        path = fallback_path
    else:
        path = Path(value) if value else fallback_path
    if path is None:
        return "-"
    try:
        return str(path.resolve().relative_to(Path(root).resolve()))
    except (OSError, ValueError):
        return str(path)
