"""Unit: Claude Code stream-json -> opencode event translation.

claude/* runs are scored by the same parse_events as opencode runs, so the
translation must preserve steps, tokens, tool calls/errors, text and provider
failures, and the subscription token must be the only credential forwarded.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runner import arena, claude_events  # noqa: E402


def assistant(msg_id, blocks, usage=None, **extra):
    return {"type": "assistant", "session_id": "s1",
            "message": {"id": msg_id, "content": blocks,
                        "usage": usage or {"input_tokens": 10,
                                           "cache_read_input_tokens": 500,
                                           "cache_creation_input_tokens": 40,
                                           "output_tokens": 7}},
            **extra}


def tool_result(call_id, text, is_error=False):
    return {"type": "user", "session_id": "s1", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id, "is_error": is_error,
         "content": [{"type": "text", "text": text}]}]}}


STREAM = [
    {"type": "system", "subtype": "init", "session_id": "s1", "model": "opus"},
    # One API turn split over two events (text block, then tool_use block).
    assistant("m1", [{"type": "text", "text": "Reading the spec."}]),
    assistant("m1", [{"type": "tool_use", "id": "t1", "name": "Read",
                      "input": {"file_path": "SPEC.md"}}]),
    tool_result("t1", "spec body"),
    assistant("m2", [{"type": "tool_use", "id": "t2", "name": "Bash",
                      "input": {"command": "false"}}],
              usage={"input_tokens": 3, "output_tokens": 5}),
    tool_result("t2", "exit 1", is_error=True),
    assistant("m3", [{"type": "text", "text": "Done."}],
              usage={"input_tokens": 1, "output_tokens": 2}),
    {"type": "result", "subtype": "success", "is_error": False,
     "session_id": "s1", "result": "Done."},
]


def write_raw(path, events):
    path.write_text("".join(json.dumps(e) + "\r\n" for e in events))


class ClaudeEventsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def stats_for(self, events):
        raw, out = self.tmp / "claude-events.jsonl", self.tmp / "events.jsonl"
        write_raw(raw, events)
        claude_events.normalize_file(raw, out)
        return arena.parse_events(out)

    def test_counts_steps_tokens_and_tools_like_opencode(self):
        stats = self.stats_for(STREAM)
        self.assertEqual(stats["steps"], 3)
        # Usage repeated across blocks of one turn is counted once.
        self.assertEqual(stats["tokens_input"], 10 + 3 + 1)
        self.assertEqual(stats["tokens_output"], 7 + 5 + 2)
        self.assertEqual(stats["tool_calls"], 2)
        self.assertEqual(stats["tool_errors"], 1)
        self.assertEqual(stats["tool_names"], {"read": 1, "bash": 1})
        self.assertEqual(stats["text_chars"], len("Reading the spec.Done."))
        self.assertEqual(stats["session_ids"], ["s1"])
        self.assertEqual(stats["api_errors"], 0)
        self.assertFalse(stats["usage_limited"])

    def test_auth_failure_is_a_provider_failure_before_acting(self):
        stats = self.stats_for([
            assistant("m1", [{"type": "text", "text": "Invalid API key"}],
                      usage={"input_tokens": 0, "output_tokens": 0},
                      error="authentication_failed"),
            {"type": "result", "subtype": "success", "is_error": True,
             "result": "Invalid API key"},
        ])
        self.assertGreater(stats["api_errors"], 0)
        self.assertEqual((stats["tool_calls"], stats["tokens_output"]), (0, 0))
        self.assertFalse(stats["usage_limited"])

    def test_usage_limit_mid_run_is_flagged(self):
        stats = self.stats_for(STREAM[:4] + [
            {"type": "result", "subtype": "success", "is_error": True,
             "result": "Claude AI usage limit reached|1791100000"},
        ])
        self.assertTrue(stats["usage_limited"])
        self.assertEqual(stats["tool_calls"], 1)

    def test_killed_run_keeps_unfinished_tool_call(self):
        stats = self.stats_for(STREAM[:3])
        self.assertEqual(stats["tool_calls"], 1)
        self.assertEqual(stats["steps"], 1)

    def test_garbage_lines_are_ignored(self):
        raw, out = self.tmp / "raw.jsonl", self.tmp / "events.jsonl"
        raw.write_text("not json\n[1, 2]\n\n" + json.dumps(STREAM[1]) + "\n")
        claude_events.normalize_file(raw, out)
        self.assertEqual(arena.parse_events(out)["steps"], 1)


class ClaudeBackendTests(unittest.TestCase):
    def test_backend_selection(self):
        self.assertEqual(arena.agent_backend("claude/opus"), "claude")
        self.assertEqual(arena.agent_backend("claude/claude-opus-5-5@high"), "claude")
        self.assertEqual(arena.agent_backend("opencode/big-pickle"), "opencode")
        self.assertEqual(arena.agent_backend("ollama/gemma4:12b"), "opencode")
        self.assertFalse(arena.is_local_model("claude/sonnet"))
        arena.validate_model_name("claude/claude-sonnet-5-5@xhigh")

    def test_claude_runs_require_subscription_token(self):
        env = {k: v for k, v in os.environ.items()
               if k != "CLAUDE_CODE_OAUTH_TOKEN"}
        env["ANTHROPIC_API_KEY"] = "sk-ant-api-not-a-subscription"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(SystemExit):
                arena.require_claude_auth(["claude/opus"])
            arena.require_claude_auth(["ollama/gemma4:12b"])
        with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "tok"}):
            arena.require_claude_auth(["claude/opus"])


if __name__ == "__main__":
    unittest.main()
