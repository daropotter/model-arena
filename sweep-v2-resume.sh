#!/bin/bash
# Resumable full v2 sweep of prescreen-qualified free models.
# Like sweep-v2.sh, but per model it runs only the tasks that do not yet have
# a valid model-arena-v2 run, and skips a model entirely once it is complete.
# Safe to re-run after the OpenRouter free daily budget resets.
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
  rem=""
  missing=$(python3 - "$m" "$TASKS" <<'PY'
import glob, json, sys
model, tasks = sys.argv[1], sys.argv[2].split()
done = set()
for p in glob.glob("results/*/record.json"):
    try:
        r = json.load(open(p))
    except Exception:
        continue
    if (r.get("model") == model and r.get("valid_for_quality")
            and (r.get("provenance") or {}).get("suite_id") == "model-arena-v2"):
        done.add(r["task"])
print(" ".join(t for t in tasks if t not in done))
PY
)
  if [ -z "$missing" ]; then
    echo "[sweep] $(date -Is) skip $m (all tasks have valid v2 runs)" >> "$LOG"
    continue
  fi
  case "$m" in
    openrouter/*)
      rem=$(quota_remaining)
      if [ -z "$rem" ] || [ "$rem" -lt "$QUOTA_MIN" ]; then
        echo "[sweep] $(date -Is) stopping before $m: free requests left=${rem:-unknown}" >> "$LOG"
        break
      fi
      ;;
  esac
  echo "[sweep] $(date -Is) start $m (missing: $missing; free requests left: ${rem:-n/a})" >> "$LOG"
  python3 runner/arena.py --models "$m" --task $missing --results results --merge >> "$LOG" 2>&1
  echo "[sweep] $(date -Is) done $m" >> "$LOG"
done < sweep-v2-models.txt
echo "[sweep] $(date -Is) finished" >> "$LOG"
