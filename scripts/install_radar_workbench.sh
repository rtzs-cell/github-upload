#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_COMMAND="${PYTHON_COMMAND:-python3}"
INSTALL_RUNTIME=1

if [[ "${1:-}" == "--without-sionna" ]]; then
  INSTALL_RUNTIME=0
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--without-sionna]" >&2
  exit 2
fi

if ! command -v "$PYTHON_COMMAND" >/dev/null 2>&1; then
  echo "Python 3.10 or newer is required." >&2
  exit 1
fi

"$PYTHON_COMMAND" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required")
print(f"Using Python {sys.version.split()[0]}")
PY

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  "$PYTHON_COMMAND" -m venv "$ROOT_DIR/.venv"
fi
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
"$VENV_PYTHON" -m pip install --upgrade pip wheel
"$VENV_PYTHON" -m pip install --no-cache-dir -r "$ROOT_DIR/services/radar_api/requirements-api.txt"
if [[ "$INSTALL_RUNTIME" -eq 1 ]]; then
  "$VENV_PYTHON" -m pip install --no-cache-dir -r "$ROOT_DIR/experiments/sionna_radar/requirements-runtime.txt"
fi

if [[ ! -f "$ROOT_DIR/apps/radar-workbench/dist/index.html" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "The package has no built frontend. Install Node.js 20+ and run npm ci && npm run build." >&2
    exit 1
  fi
  (
    cd "$ROOT_DIR/apps/radar-workbench"
    npm ci
    npm run build
  )
fi

mkdir -p \
  "$ROOT_DIR/outputs/radar_workbench/experiments" \
  "$ROOT_DIR/outputs/radar_workbench/campaigns" \
  "$ROOT_DIR/outputs/radar_workbench/logs" \
  "$ROOT_DIR/outputs/radar_workbench/web_cache"

GPU_IDS="0"
if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_IDS="$(nvidia-smi --query-gpu=index --format=csv,noheader | paste -sd, -)"
fi

{
  echo "RADAR_API_PYTHON=$VENV_PYTHON"
  if [[ "$INSTALL_RUNTIME" -eq 1 ]]; then
    echo "RADAR_SIONNA_PYTHON=$VENV_PYTHON"
  fi
  echo "RADAR_UI_MODE=embedded"
  echo "RADAR_API_HOST=127.0.0.1"
  echo "RADAR_API_PORT=8000"
  echo "RADAR_GPU_IDS=$GPU_IDS"
} > "$ROOT_DIR/.env.radar"

"$VENV_PYTHON" "$ROOT_DIR/scripts/rebase_radar_paths.py" --repo "$ROOT_DIR"
echo "Installation complete. Start with: ./scripts/start_radar_workbench.sh"
