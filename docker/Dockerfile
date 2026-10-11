FROM node:22-bookworm-slim

# opencode is pinned to a known-good release; bump with
#   ./docker/build.sh <version>   (e.g. ./docker/build.sh 1.18.32)
ARG OPENCODE_VERSION=1.18.32
# Claude Code drives claude/* models (subscription auth); bump with
#   CLAUDE_CODE_VERSION=<version> ./docker/build.sh
ARG CLAUDE_CODE_VERSION=2.1.289
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
        git openssh-client ca-certificates ripgrep fd-find less curl bash \
        tini python3 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf "$(command -v fdfind)" /usr/local/bin/fd

RUN npm install -g "opencode-ai@${OPENCODE_VERSION}" \
        "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

RUN mkdir -p /home/opencode/.config/opencode \
             /home/opencode/.local/share/opencode \
             /home/opencode/.cache \
             /workspace /out \
    && chown -R 1000:1000 /home/opencode /workspace /out

ENV HOME=/home/opencode \
    XDG_CONFIG_HOME=/home/opencode/.config \
    XDG_DATA_HOME=/home/opencode/.local/share \
    XDG_CACHE_HOME=/home/opencode/.cache

USER 1000:1000
WORKDIR /workspace
