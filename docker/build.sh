#!/usr/bin/env bash
# Build the model-arena-agent image.
#   ./build.sh            -> uses the pinned OPENCODE_VERSION in Dockerfile
#   ./build.sh 1.18.32    -> build a specific opencode-ai release
#   CLAUDE_CODE_VERSION=2.1.289 ./build.sh -> pick the Claude Code release
set -euo pipefail
cd "$(dirname "$0")"
IMAGE="${ARENA_IMAGE:-model-arena-agent}"
args=()
if [ "$#" -ge 1 ]; then
  args+=(--build-arg OPENCODE_VERSION="$1")
fi
if [ -n "${CLAUDE_CODE_VERSION:-}" ]; then
  args+=(--build-arg CLAUDE_CODE_VERSION="$CLAUDE_CODE_VERSION")
fi
docker build "${args[@]}" -t "$IMAGE" .
echo "built: $IMAGE"
