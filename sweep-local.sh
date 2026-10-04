#!/bin/bash
# Local comparison run: ollama/qwen3.8-32k, the only prescreen-qualified local
# model without full v2 coverage. ARENA_NO_THINK matches the project's setting
# for thinking models (qwen3.8 etc.), which otherwise spend minutes per step.
set -u
cd "$(dirname "$0")"
LOG=sweep-local.log
TASKS="codec cronlog datajanitor filedock generator interpreter kvstore ledger merge pipeline regex scheduler sumtool tasklog"
echo "[local] $(date -Is) start" >> "$LOG"
ARENA_NO_THINK=1 python3 runner/arena.py --models ollama/qwen3.8-32k --task $TASKS --results results --merge >> "$LOG" 2>&1
echo "[local] $(date -Is) done" >> "$LOG"
