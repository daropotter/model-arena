#!/bin/bash
# Sweep of the new Zen free models (cat-jam-free, step-5-preview-free, both
# routes) over the full 17-task suite. Zen free models share rate limits, so
# they run strictly one at a time; this queue is safe to run in parallel with
# local ollama sweeps (different resource pools).
# Per-task timeout from meta.json via --force-timeout, matching the review
# sweeps, so billingreview gets its full 2700s budget.
set -u
cd "$(dirname "$0")"
LOG=sweep-newfree.log
MODELS="opencode/cat-jam-free opencode-go/cat-jam-free opencode/step-5-preview-free opencode-go/step-5-preview-free"
TASKS="billingreview cartreview codec cronlog datajanitor filedock generator interpreter kvstore ledger merge notesreview pipeline regex scheduler sumtool tasklog"

echo "[newfree] $(date -Is) start: $MODELS" >> "$LOG"
for m in $MODELS; do
  echo "[newfree] $(date -Is) start $m" >> "$LOG"
  for t in $TASKS; do
    timeout_s=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['timeout'])" "tasks/$t/meta.json")
    python3 runner/arena.py --models "$m" --task "$t" \
      --timeout "$timeout_s" --force-timeout --results results --merge >> "$LOG" 2>&1
  done
  echo "[newfree] $(date -Is) done $m" >> "$LOG"
done
echo "[newfree] $(date -Is) finished" >> "$LOG"
