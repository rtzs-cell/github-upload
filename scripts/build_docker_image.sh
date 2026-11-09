#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${RADAR_IMAGE:-radar-workbench:2.0.1}"
CONTAINER_CLI="${CONTAINER_CLI:-docker}"
PYTHON_IMAGE="${RADAR_PYTHON_IMAGE:-public.ecr.aws/docker/library/python:3.10-slim-bookworm}"
APP_VERSION="${RADAR_VERSION:-2.0.1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) shift; IMAGE="${1:-}" ;;
    *) echo "Usage: $0 [--image NAME:TAG]" >&2; exit 2 ;;
  esac
  shift
done

[[ -n "$IMAGE" ]] || { echo "Image name cannot be empty." >&2; exit 2; }
command -v "$CONTAINER_CLI" >/dev/null 2>&1 || { echo "$CONTAINER_CLI is not installed." >&2; exit 1; }
[[ -f "$ROOT_DIR/apps/radar-workbench/dist/index.html" ]] || {
  echo "Built frontend is missing. Run npm -C apps/radar-workbench run build first." >&2
  exit 1
}

"$CONTAINER_CLI" build \
  --file "$ROOT_DIR/Containerfile" \
  --tag "$IMAGE" \
  --build-arg "PYTHON_IMAGE=$PYTHON_IMAGE" \
  --build-arg "APP_VERSION=$APP_VERSION" \
  "$ROOT_DIR"

"$CONTAINER_CLI" image inspect "$IMAGE" --format 'Image size: {{.Size}} bytes'
