"""Translate Claude Code's stream-json output into opencode-style events.

Every consumer of `events.jsonl` (parse_events, analyze, prescreen,
report_models) reads opencode's `--format json` schema. Rather than teaching
each of them a second dialect, claude/* runs keep Claude Code's raw stream as
`claude-events.jsonl` and get a normalized `events.jsonl` written next to it:

  assistant message (one API turn)  -> step_start ... step_finish (tokens)
  assistant text block              -> text
  tool_use block + its tool_result  -> tool_use (state completed/error)
  API / usage-limit / result error  -> error

Tool names are lower-cased (Bash -> bash) so tool tables line up with
opencode runs. Token semantics follow opencode: `input` excludes cache reads
and writes, which are reported under `cache`.
"""
import json
import re
from pathlib import Path

# Errors that mean the subscription refused service, not that the model failed.
USAGE_LIMIT_PATTERN = re.compile(
    r"(usage|session|weekly) limit|rate[ _-]?limit|limit reached|overloaded|\b429\b|\b529\b",
    re.IGNORECASE)


def _error_event(session_id, name, message, ts):
    return {"type": "error", "timestamp": ts, "sessionID": session_id,
            "error": {"name": name, "data": {"message": message}}}


def _error_name(message: str, default: str) -> str:
    return "UsageLimitError" if USAGE_LIMIT_PATTERN.search(message) else default


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(c.get("text", "")) for c in content
            if isinstance(c, dict) and c.get("type") == "text")
    return ""


def convert(raw_lines):
    """Yield opencode-style events for an iterable of raw stream-json lines."""
    session_id = ""
    ts = 0
    pending = {}           # tool_use id -> event awaiting its result
    open_msg = None        # message id of the step in progress
    open_usage = {}

    def finish_step():
        nonlocal open_msg, open_usage
        if open_msg is None:
            return None
        usage = open_usage or {}
        event = {
            "type": "step_finish", "timestamp": ts, "sessionID": session_id,
            "part": {"type": "step-finish", "messageID": open_msg, "tokens": {
                "input": int(usage.get("input_tokens") or 0),
                "output": int(usage.get("output_tokens") or 0),
                "reasoning": 0,
                "cache": {
                    "read": int(usage.get("cache_read_input_tokens") or 0),
                    "write": int(usage.get("cache_creation_input_tokens") or 0),
                },
            }},
        }
        open_msg, open_usage = None, {}
        return event

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        ts += 1
        session_id = ev.get("session_id") or session_id
        etype = ev.get("type")

        if etype == "assistant":
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            msg_id = msg.get("id") or f"msg_{ts}"
            # Claude Code emits one event per content block; blocks of the
            # same API turn share message.id and repeat its usage.
            if msg_id != open_msg:
                done = finish_step()
                if done:
                    yield done
                open_msg = msg_id
                yield {"type": "step_start", "timestamp": ts,
                       "sessionID": session_id,
                       "part": {"type": "step-start", "messageID": msg_id}}
            if isinstance(msg.get("usage"), dict):
                open_usage = msg["usage"]
            if ev.get("error"):
                text = _result_text(msg.get("content")) or str(ev["error"])
                yield _error_event(session_id, _error_name(text, "APIError"),
                                   text, ts)
                continue
            for block in msg.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    yield {"type": "text", "timestamp": ts,
                           "sessionID": session_id,
                           "part": {"type": "text", "text": block["text"]}}
                elif block.get("type") == "tool_use":
                    pending[block.get("id")] = {
                        "type": "tool_use", "timestamp": ts,
                        "sessionID": session_id,
                        "part": {"type": "tool",
                                 "tool": str(block.get("name") or "?").lower(),
                                 "callID": block.get("id"),
                                 "state": {"status": "running",
                                           "input": block.get("input") or {}}},
                    }

        elif etype == "user":
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            content = msg.get("content")
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                event = pending.pop(block.get("tool_use_id"), None)
                if event is None:
                    continue
                output = _result_text(block.get("content"))
                state = event["part"]["state"]
                if block.get("is_error"):
                    state.update(status="error", error=output)
                else:
                    state.update(status="completed", output=output)
                event["timestamp"] = ts
                yield event

        elif etype == "result":
            done = finish_step()
            if done:
                yield done
            if ev.get("is_error") or ev.get("subtype") not in (None, "success"):
                text = str(ev.get("result") or ev.get("subtype") or "error")
                yield _error_event(session_id,
                                   _error_name(text, "ResultError"), text, ts)

    done = finish_step()
    if done:
        yield done
    # Calls cut off by a kill still count as attempted tool calls.
    for event in pending.values():
        yield event


def normalize_file(raw_path: Path, out_path: Path) -> None:
    with open(raw_path, errors="replace") as src:
        events = list(convert(src))
    with open(out_path, "w") as out:
        for event in events:
            out.write(json.dumps(event) + "\n")
