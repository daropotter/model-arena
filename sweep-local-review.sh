#!/bin/bash
# Local model sweep over the three code-review tasks (cartreview, notesreview,
# billingreview). ARENA_NO_THINK=1 matches the project's setting for local
# thinking models (see sweep-local.sh). Each pair runs with the task's own
# meta.json timeout via --force-timeout, because the runner's 1800s default
# would otherwise cap billingreview's 2700s budget. Pairs that already have a
# valid record in results/ are skipped, so the script is safe to re-run.
set -u
cd "$(dirname "$0")"
LOG=sweep-local-review.log
MODELS="ollama/qwen3.8-35b-a3b-moe-Q3_K_M ollama/gemma4-128k:latest ollama/qwen3-coder:30b ollama/devstral-small-2:24b ollama/qwen3.8-32k"
TASKS="cartreview notesreview billingreview"

done_pair() {
  python3 - "$1" "$2" <<'PY'
import glob, json, sys
model, task = sys.argv[1:]
for p in glob.glob("results/*/record.json"):
    try:
        r = json.load(open(p))
    except Exception:
        continue
    if r.get("model") == model and r.get("task") == task and r.get("valid_for_quality"):
        sys.exit(0)
sys.exit(1)
PY
}

echo "[review] $(date -Is) start: $MODELS" >> "$LOG"
for m in $MODELS; do
  for t in $TASKS; do
    if done_pair "$m" "$t"; then
      echo "[review] $(date -Is) skip $m x $t (valid record)" >> "$LOG"
      continue
    fi
    timeout_s=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['timeout'])" "tasks/$t/meta.json")
    echo "[review] $(date -Is) start $m x $t (timeout ${timeout_s}s)" >> "$LOG"
    ARENA_NO_THINK=1 python3 runner/arena.py --models "$m" --task "$t" \
      --timeout "$timeout_s" --force-timeout --results results --merge >> "$LOG" 2>&1
    echo "[review] $(date -Is) done $m x $t rc=$?" >> "$LOG"
  done
done
echo "[review] $(date -Is) finished" >> "$LOG"
