#!/bin/sh
# Args: MODEL PROMPT_FILE TIMEOUT_SEC [OLLAMA_BASE_URL]
#
# Two kinds of models:
#   ollama/<name>    local; the provider block below points at the host proxy
#   <provider>/<id>  hosted (e.g. opencode/* Zen free models); no config
#                    needed, opencode ships the provider. Needs internet.
set -eu

MODEL="$1"
PROMPT_FILE="$2"
TIMEOUT_SEC="$3"
OLLAMA_BASE_URL="${4:-http://172.22.0.1:11435/v1}"

CONFIG_DIR="$HOME/.config/opencode"
mkdir -p "$CONFIG_DIR"

case "$MODEL" in
  ollama/*)
    MODEL_ID="${MODEL#ollama/}"
    # ARENA_NO_THINK=1 turns off reasoning for thinking models (qwen3.8 etc.).
    # Without it such a model can spend minutes per step in "thinking" and
    # never finish an agent loop on CPU-offloaded hardware.
    if [ "${ARENA_NO_THINK:-0}" = "1" ]; then
      MODEL_OPTS=', "options": { "think": false }, "reasoning": false'
    else
      MODEL_OPTS=""
    fi
    # ARENA_MODEL_OPTS lets a run pass raw ollama options for one model,
    # e.g. ARENA_MODEL_OPTS=', "options": { "num_ctx": 16384 }'. It is not
    # meant to be combined with ARENA_NO_THINK (the last one wins).
    if [ -n "${ARENA_MODEL_OPTS:-}" ]; then
      MODEL_OPTS="$ARENA_MODEL_OPTS"
    fi
    cat > "$CONFIG_DIR/opencode.json" <<EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": { "baseURL": "$OLLAMA_BASE_URL" },
      "models": { "$MODEL_ID": { ${MODEL_OPTS#, } } }
    }
  },
  "permission": {
    "bash": "allow",
    "read": { "*": "allow", "*.env": "deny", "*.env.*": "deny" },
    "external_directory": "allow"
  }
}
EOF
    ;;
  *)
    # hosted provider: let opencode use its built-in provider/model registry
    cat > "$CONFIG_DIR/opencode.json" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "bash": "allow",
    "read": { "*": "allow", "*.env": "deny", "*.env.*": "deny" },
    "external_directory": "allow"
  }
}
EOF
    ;;
esac

cat > "$CONFIG_DIR/AGENTS.md" <<'EOF'
You are working in /workspace. Use relative paths for all file operations.
All commands run from /workspace. Never use absolute paths outside /workspace.
EOF
if [ -f /extra_agents.md ]; then
  cat /extra_agents.md >> "$CONFIG_DIR/AGENTS.md"
fi
cat >> "$CONFIG_DIR/AGENTS.md" <<'EOF'

## Ground rules

- Finish the task, not just a draft. Read SPEC.md completely before writing
  code; every rule in it is graded, hidden tests cover what you have not seen.
- Verify your work yourself before stopping: run the visible tests
  (`python3 -m pytest tests/ -q` when a tests/ directory exists) and fix every
  failure. A task is done when your code matches the spec AND the tests pass.
- Edit files by calling the `edit` tool with the exact current text of the
  region you are changing. If an edit fails because the text is not found,
  read the file again and retry with the exact text — do not give up.
- Call one tool at a time and look at its result before the next step.
- Never print a tool call as text — only real tool calls do anything.
EOF

# Wrapper so the prompt can be read from a file at runtime (no nested quoting).
cat > /tmp/run_opencode.sh <<EOF
#!/bin/sh
exec opencode run -m "$MODEL" --pure --auto --format json --dir /workspace "\$(cat $PROMPT_FILE)"
EOF
chmod +x /tmp/run_opencode.sh

cd /workspace
# `script` gives opencode a pty so the JSON event stream is line-buffered and
# survives a SIGKILL partway through a slow run. -e propagates the exit code.
# The wall below is a pure safety net, deliberately far beyond TIMEOUT_SEC:
# the host enforces the real limits by watching the event stream (it stops
# the container when the model is idle past the deadline). Slow local models
# (partial GPU offload) can spend >10 minutes on a single generation with no
# events, so the container must not die before the host decides.
timeout -s KILL "$((TIMEOUT_SEC + ${ARENA_POST_DEADLINE:-1800}))" script -q -e -c /tmp/run_opencode.sh /dev/null
exit $?
