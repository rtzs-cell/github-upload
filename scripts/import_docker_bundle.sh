#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_CLI="${CONTAINER_CLI:-docker}"

command -v "$CONTAINER_CLI" >/dev/null 2>&1 || { echo "$CONTAINER_CLI is not installed." >&2; exit 1; }
command -v zstd >/dev/null 2>&1 || { echo "zstd is required." >&2; exit 1; }
cd "$ROOT_DIR"
sha256sum -c SHA256SUMS
zstd -dc radar-workbench-image.tar.zst | "$CONTAINER_CLI" load
mkdir -p radar-data

echo "Image imported. Start with:"
echo "RADAR_UID=$(id -u) RADAR_GID=$(id -g) $CONTAINER_CLI compose --env-file .env.docker up -d --no-build"
echo "Then open: http://127.0.0.1:8000/"
