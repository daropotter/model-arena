#!/bin/bash
# Full v2 sweep of prescreen-qualified free models.
# Runs the 14 scored tasks per model (smoke is already covered by the
# prescreen). OpenRouter free models share a daily request budget, so it is
# checked before each model and the sweep stops cleanly when it runs low.
set -u
cd "$(dirname "$0")"
LOG=sweep-v2.log
TASKS="codec cronlog datajanitor filedock generator interpreter kvstore ledger merge pipeline regex scheduler sumtool tasklog"
QUOTA_MIN=30

quota_remaining() {
  curl -s -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    https://openrouter.ai/api/v1/auth/key \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["free_model_daily_requests"]["remaining"])' 2>/dev/null
}

while read -r m; do
  [ -z "$m" ] && continue
  case "$m" in
    openrouter/*)
      rem=$(quota_remaining)
      if [ -z "$rem" ] || [ "$rem" -lt "$QUOTA_MIN" ]; then
        echo "[sweep] $(date -Is) stopping before $m: free requests left=${rem:-unknown}" >> "$LOG"
        break
      fi
      ;;
  esac
  echo "[sweep] $(date -Is) start $m (free requests left: ${rem:-n/a})" >> "$LOG"
  python3 runner/arena.py --models "$m" --task $TASKS --results results --merge >> "$LOG" 2>&1
  echo "[sweep] $(date -Is) done $m" >> "$LOG"
done < sweep-v2-models.txt
echo "[sweep] $(date -Is) finished" >> "$LOG"
