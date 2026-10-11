#!/bin/bash
# Claude subscription sweep: claude/* models through the Claude Code harness.
#
# The runner needs CLAUDE_CODE_OAUTH_TOKEN. Instead of a long-lived token from
# `claude setup-token`, this refreshes the host Claude Code session before each
# model (the CLI rotates ~/.claude/.credentials.json) and extracts the access
# token into the environment; the token is never printed. ANTHROPIC_API_KEY is
# explicitly unset so nothing can fall back to creditless API billing.
#
# Runs only tasks without a valid model-arena-v2 result, so the script is safe
# to re-run after subscription usage limits reset. Like every entry point it
# serializes on the shared host lock.
set -u
cd "$(dirname "$0")"
LOG=sweep-claude.log
TASKS="codec cronlog datajanitor filedock generator interpreter kvstore ledger merge pipeline regex scheduler sumtool tasklog"

get_token() {
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN python3 -c \
    "import json,sys;print(json.load(open(sys.argv[1]))['claudeAiOauth']['accessToken'])" \
    "$HOME/.claude/.credentials.json"
}

refresh_session() {
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN timeout 120 \
    claude -p --model haiku "ok" >/dev/null 2>&1 || true
}

while read -r m; do
  [ -z "$m" ] && continue
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
    echo "[claude] $(date -Is) skip $m (complete)" >> "$LOG"
    continue
  fi
  refresh_session
  if ! CLAUDE_CODE_OAUTH_TOKEN=$(get_token); then
    echo "[claude] $(date -Is) token unavailable, stopping" >> "$LOG"
    break
  fi
  export CLAUDE_CODE_OAUTH_TOKEN
  echo "[claude] $(date -Is) start $m (missing: $missing)" >> "$LOG"
  python3 runner/arena.py --models "$m" --task $missing --results results --merge >> "$LOG" 2>&1
  echo "[claude] $(date -Is) done $m" >> "$LOG"
done < sweep-claude-models.txt
echo "[claude] $(date -Is) finished" >> "$LOG"
