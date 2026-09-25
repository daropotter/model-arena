#!/usr/bin/env bash
# Build the model-arena-agent image.
#   ./build.sh            -> uses the pinned OPENCODE_VERSION in Dockerfile
#   ./build.sh 1.18.32    -> build a specific opencode-ai release
set -euo pipefail
cd "$(dirname "$0")"
IMAGE="${ARENA_IMAGE:-model-arena-agent}"
if [ "$#" -ge 1 ]; then
  docker build --build-arg OPENCODE_VERSION="$1" -t "$IMAGE" .
else
  docker build -t "$IMAGE" .
fi
echo "built: $IMAGE"
