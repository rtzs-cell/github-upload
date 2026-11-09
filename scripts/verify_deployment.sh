#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT_DIR/.env.radar" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env.radar"
  set +a
fi
PYTHON_BIN="${RADAR_API_PYTHON:-$ROOT_DIR/.venv/bin/python}"

[[ -x "$PYTHON_BIN" ]] || { echo "Python environment is missing." >&2; exit 1; }
[[ -f "$ROOT_DIR/apps/radar-workbench/dist/index.html" ]] || { echo "Frontend build is missing." >&2; exit 1; }

"$PYTHON_BIN" - <<'PY'
import fastapi, matplotlib, numpy, pandas, pyarrow, scipy, uvicorn, yaml
print("API dependencies: OK")
PY

if [[ -n "${RADAR_SIONNA_PYTHON:-}" ]]; then
  "$RADAR_SIONNA_PYTHON" - <<'PY'
from sionna.rt import PathSolver, load_scene
print("Sionna RT runtime: OK")
PY
else
  echo "Sionna RT runtime: not installed (result browsing only)"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader
else
  echo "NVIDIA driver not detected. GPU simulation will be unavailable."
fi

echo "Deployment prerequisites verified."
