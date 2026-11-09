#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
[[ -f .env.docker ]] || { echo ".env.docker is missing." >&2; exit 1; }

set -a
# shellcheck disable=SC1091
source .env.docker
set +a
IMAGE="${RADAR_IMAGE:-localhost/radar-workbench:2.0.1}"

command -v docker >/dev/null 2>&1 || { echo "Docker is not installed." >&2; exit 1; }
command -v nvidia-smi >/dev/null 2>&1 || { echo "NVIDIA driver tools are not installed." >&2; exit 1; }
docker compose version
nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader
docker image inspect "$IMAGE" --format 'Image: {{index .RepoTags 0}} ({{.Size}} bytes)'

docker run --rm -i --gpus all --entrypoint python "$IMAGE" - <<'PY'
import drjit as dr
import mitsuba as mi
from sionna.rt import PathSolver, load_scene

mi.set_variant("cuda_ad_mono")
values = dr.arange(mi.Float, 1024)
total = dr.sum(values)
dr.eval(total)
assert total[0] == 523776.0
assert dr.has_backend(dr.JitBackend.CUDA)
print("Sionna RT imports: OK")
print("Mitsuba variant: cuda_ad_mono")
print("CUDA computation: OK")
PY

export RADAR_UID="$(id -u)"
export RADAR_GID="$(id -g)"
docker compose --env-file .env.docker config >/dev/null
echo "Compose configuration: OK"

if HEALTH_RESPONSE="$(docker compose --env-file .env.docker exec -T radar-workbench \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read().decode())" \
  2>/dev/null)"; then
  echo "$HEALTH_RESPONSE"
  echo "Running service: OK"
else
  echo "Service is not running; run ./start_radar_workbench.sh after verification."
fi
