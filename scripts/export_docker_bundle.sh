#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${RADAR_IMAGE:-radar-workbench:2.0.1}"
CONTAINER_CLI="${CONTAINER_CLI:-docker}"
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) shift; IMAGE="${1:-}" ;;
    --output) shift; OUTPUT="${1:-}" ;;
    *) echo "Usage: $0 [--image NAME:TAG] [--output FILE.tar]" >&2; exit 2 ;;
  esac
  shift
done

command -v "$CONTAINER_CLI" >/dev/null 2>&1 || { echo "$CONTAINER_CLI is not installed." >&2; exit 1; }
command -v zstd >/dev/null 2>&1 || { echo "zstd is required." >&2; exit 1; }
"$CONTAINER_CLI" image inspect "$IMAGE" >/dev/null
ARCHIVE_IMAGE="$("$CONTAINER_CLI" image inspect "$IMAGE" --format '{{index .RepoTags 0}}')"
[[ -n "$ARCHIVE_IMAGE" ]] || { echo "Image $IMAGE has no repository tag." >&2; exit 1; }

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT="${OUTPUT:-$ROOT_DIR/radar-workbench-docker-$TIMESTAMP.tar}"
OUTPUT="$(realpath -m "$OUTPUT")"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
BUNDLE_DIR="$TEMP_DIR/radar-workbench-offline"
mkdir -p "$BUNDLE_DIR"

echo "Exporting $ARCHIVE_IMAGE ..."
"$CONTAINER_CLI" save "$ARCHIVE_IMAGE" | zstd -T0 -10 -o "$BUNDLE_DIR/radar-workbench-image.tar.zst"
cp "$ROOT_DIR/compose.yaml" "$BUNDLE_DIR/compose.yaml"
cp "$ROOT_DIR/.env.docker.example" "$BUNDLE_DIR/.env.docker"
sed -i "s|^RADAR_IMAGE=.*|RADAR_IMAGE=$ARCHIVE_IMAGE|" "$BUNDLE_DIR/.env.docker"
cp "$ROOT_DIR/scripts/import_docker_bundle.sh" "$BUNDLE_DIR/import_docker_bundle.sh"
cp "$ROOT_DIR/scripts/start_docker_bundle.sh" "$BUNDLE_DIR/start_radar_workbench.sh"
cp "$ROOT_DIR/scripts/stop_docker_bundle.sh" "$BUNDLE_DIR/stop_radar_workbench.sh"
cp "$ROOT_DIR/scripts/verify_docker_bundle.sh" "$BUNDLE_DIR/verify_radar_workbench.sh"
cp "$ROOT_DIR/docs/DOCKER_OFFLINE_INSTALL.md" "$BUNDLE_DIR/INSTALL.md"
"$ROOT_DIR/scripts/package_radar_workbench.sh" \
  --output "$BUNDLE_DIR/radar-workbench-source.tar.zst"
chmod +x \
  "$BUNDLE_DIR/import_docker_bundle.sh" \
  "$BUNDLE_DIR/start_radar_workbench.sh" \
  "$BUNDLE_DIR/stop_radar_workbench.sh" \
  "$BUNDLE_DIR/verify_radar_workbench.sh"
(cd "$BUNDLE_DIR" && sha256sum \
  radar-workbench-image.tar.zst \
  radar-workbench-source.tar.zst \
  > SHA256SUMS)

tar -cf "$OUTPUT" -C "$TEMP_DIR" radar-workbench-offline
echo "Created: $OUTPUT"
du -h "$OUTPUT"
