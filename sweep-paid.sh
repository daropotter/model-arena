#!/bin/bash
# Comparison sweep of paid opencode-go models (deepseek-v4.1-flash, deepseek-v4-pro,
# gpt-6-luna). Same 14 scored tasks as the free sweep, so results are comparable.
# OpenAIs gpt-6.1-sol is not runnable: the API key has no credits, Zen has no
# funds, and Go does not carry it.
set -u
cd "$(dirname "$0")"
LOG=sweep-paid.log
TASKS="codec cronlog datajanitor filedock generator interpreter kvstore ledger merge pipeline regex scheduler sumtool tasklog"
echo "[paid] $(date -Is) start" >> "$LOG"
python3 runner/arena.py --models-file sweep-paid-models.txt --task $TASKS --results results --merge >> "$LOG" 2>&1
echo "[paid] $(date -Is) done" >> "$LOG"
