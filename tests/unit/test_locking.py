"""Host-lock policy: only local-model sweeps serialize on the host lock.

Hosted runs (opencode Zen, OpenRouter, OpenAI, claude/*) do not touch the
shared GPU, so they must be able to run in parallel with the local completion
queue instead of queueing behind it.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from runner import arena  # noqa: E402


class HostLockPolicyTests(unittest.TestCase):
    def test_hosted_only_sweeps_skip_the_lock(self):
        for model in ("openrouter/qwen/qwen3.8-27b:free", "opencode/big-pickle",
                      "opencode-go/deepseek-v4-pro", "openai/gpt-6.1-sol",
                      "claude/sonnet"):
            self.assertFalse(arena.needs_host_lock([model]), model)

    def test_local_models_keep_the_lock(self):
        self.assertTrue(arena.needs_host_lock(["ollama/qwen3.8-32k"]))
        self.assertTrue(arena.needs_host_lock(
            ["openrouter/qwen/qwen3.8-27b:free", "ollama/qwen3.8-32k"]))
        self.assertFalse(arena.needs_host_lock([]))


if __name__ == "__main__":
    unittest.main()
