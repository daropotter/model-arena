#!/bin/bash
# Keep the v2 sweep moving across OpenRouter free-budget resets.
# Every 5 minutes: if no run is active and models are still incomplete,
# wait for the free budget to refresh (>=300 requests) and resume.
# Exits once every model has all 14 tasks with a valid v2 run.
# Stop with: pkill -f sweep-v2-watch
set -u
cd "$(dirname "$0")"
LOG=sweep-v2-watch.log

quota_remaining() {
  curl -s -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    https://openrouter.ai/api/v1/auth/key \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["free_model_daily_requests"]["remaining"])' 2>/dev/null
}

pending_models() {
  python3 - <<'PY'
import glob, json
TASKS = ("codec cronlog datajanitor filedock generator interpreter kvstore ledger merge "
         "pipeline regex scheduler sumtool tasklog").split()
models = [l.strip() for l in open("sweep-v2-models.txt") if l.strip()]
done, seen = set(), set()
for p in glob.glob("results/*/record.json"):
    try:
        r = json.load(open(p))
    except Exception:
        continue
    if (r.get("valid_for_quality")
            and (r.get("provenance") or {}).get("suite_id") == "model-arena-v2"):
        done.add((r["model"], r["task"]))
pending = [m for m in models
           if any((m, t) not in done for t in TASKS) and m not in seen]
print(len(pending))
PY
}

while :; do
  if ! pgrep -f "runner/arena.py" >/dev/null; then
    left=$(pending_models)
    if [ "$left" = "0" ]; then
      echo "[watch] $(date -Is) all models complete, exiting" >> "$LOG"
      break
    fi
    rem=$(quota_remaining)
    if [ -n "$rem" ] && [ "$rem" -ge 300 ]; then
      echo "[watch] $(date -Is) $left model(s) pending, quota $rem — resuming" >> "$LOG"
      bash sweep-v2-resume.sh
      echo "[watch] $(date -Is) resume pass returned" >> "$LOG"
    else
      echo "[watch] $(date -Is) $left model(s) pending, quota ${rem:-unknown} — waiting" >> "$LOG"
    fi
  fi
  sleep 300
done
