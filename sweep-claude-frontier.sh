#!/bin/bash
# Claude subscription sweep over the opt-in tasks-frontier suite.
#
# Token handling as in sweep-claude.sh: the host Claude Code session is
# refreshed before every run and its access token exported; ANTHROPIC_API_KEY
# is unset so nothing falls back to API billing. Pairs that already have a
# valid record in results-frontier are skipped, so the script is safe to
# re-run after subscription usage limits reset.
set -u
cd "$(dirname "$0")"
LOG=sweep-claude-frontier.log
TASKS="dispatch-migration dispatch-minefield returns-release export-forensics dossier returns-distributed"

get_token() {
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN python3 -c \
    "import json,sys;print(json.load(open(sys.argv[1]))['claudeAiOauth']['accessToken'])" \
    "$HOME/.claude/.credentials.json"
}

refresh_session() {
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN timeout 120 \
    claude -p --model haiku "ok" >/dev/null 2>&1 || true
}

done_pair() {
  python3 - "$1" "$2" <<'PY'
import glob, json, sys
model, task = sys.argv[1:]
for p in glob.glob("results-frontier/*/record.json"):
    try:
        r = json.load(open(p))
    except Exception:
        continue
    if r.get("model") == model and r.get("task") == task and r.get("valid_for_quality"):
        sys.exit(0)
sys.exit(1)
PY
}

while read -r m; do
  [ -z "$m" ] && continue
  for t in $TASKS; do
    if done_pair "$m" "$t"; then
      echo "[frontier] $(date -Is) skip $m x $t (valid record)" >> "$LOG"
      continue
    fi
    refresh_session
    if ! CLAUDE_CODE_OAUTH_TOKEN=$(get_token); then
      echo "[frontier] $(date -Is) token unavailable, stopping" >> "$LOG"
      exit 1
    fi
    export CLAUDE_CODE_OAUTH_TOKEN
    timeout_s=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['timeout'])" "tasks-frontier/$t/meta.json")
    echo "[frontier] $(date -Is) start $m x $t (timeout ${timeout_s}s)" >> "$LOG"
    env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
      python3 runner/frontier.py --model "$m" --task "$t" --timeout "$timeout_s" >> "$LOG" 2>&1
    echo "[frontier] $(date -Is) done $m x $t rc=$?" >> "$LOG"
  done
done < sweep-claude-models.txt
echo "[frontier] $(date -Is) finished" >> "$LOG"
