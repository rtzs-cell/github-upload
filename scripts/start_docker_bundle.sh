#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
[[ -f .env.docker ]] || { echo ".env.docker is missing." >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker is not installed." >&2; exit 1; }
docker compose version >/dev/null

set -a
# shellcheck disable=SC1091
source .env.docker
set +a
DATA_DIR="${RADAR_DATA_DIR:-./radar-data}"
mkdir -p "$DATA_DIR"
[[ -w "$DATA_DIR" ]] || { echo "Data directory is not writable: $DATA_DIR" >&2; exit 1; }

export RADAR_UID="$(id -u)"
export RADAR_GID="$(id -g)"
docker compose --env-file .env.docker up -d --no-build

PORT="${RADAR_PORT:-8000}"
for _ in $(seq 1 60); do
  if docker compose --env-file .env.docker exec -T radar-workbench \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" \
    >/dev/null 2>&1; then
    echo "Radar Workbench is ready: http://127.0.0.1:$PORT/"
    exit 0
  fi
  sleep 1
done

docker compose --env-file .env.docker logs --tail=100 >&2
echo "Radar Workbench did not become ready." >&2
exit 1
