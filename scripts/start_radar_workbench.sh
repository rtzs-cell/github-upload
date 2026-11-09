#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/outputs/radar_workbench/logs"
mkdir -p "$LOG_DIR"

if [[ -f "$ROOT_DIR/.env.radar" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env.radar"
  set +a
fi

PYTHON_BIN="${RADAR_API_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || command -v python)"
  fi
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "No executable Python found. Run ./scripts/install_radar_workbench.sh first." >&2
  exit 1
fi

if [[ -z "${RADAR_SIONNA_PYTHON:-}" ]]; then
  if "$PYTHON_BIN" -c 'from sionna.rt import PathSolver' >/dev/null 2>&1; then
    export RADAR_SIONNA_PYTHON="$PYTHON_BIN"
  elif command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base 2>/dev/null || true)"
    SIONNA_CONDA_PYTHON="$CONDA_BASE/envs/sionna-rt2/bin/python"
    if [[ -x "$SIONNA_CONDA_PYTHON" ]]; then
      export RADAR_SIONNA_PYTHON="$SIONNA_CONDA_PYTHON"
    fi
  fi
fi
export RADAR_SIONNA_PYTHONNOUSERSITE="${RADAR_SIONNA_PYTHONNOUSERSITE:-1}"

API_HOST="${RADAR_API_HOST:-127.0.0.1}"
API_PORT="${RADAR_API_PORT:-8000}"
UI_HOST="${RADAR_UI_HOST:-127.0.0.1}"
UI_PORT="${RADAR_UI_PORT:-5173}"
UI_MODE="${RADAR_UI_MODE:-dev}"

api_pid_file="$LOG_DIR/radar_api.pid"
ui_pid_file="$LOG_DIR/radar_ui.pid"

wait_for_url() {
  local name="$1"
  local url="$2"
  local log_file="$3"
  for _ in $(seq 1 30); do
    if "$PYTHON_BIN" - "$url" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

url = sys.argv[1]
with urllib.request.urlopen(url, timeout=1) as response:
    if response.status < 400:
        sys.exit(0)
sys.exit(1)
PY
    then
      echo "$name ready: $url"
      return 0
    fi
    sleep 1
  done
  echo "$name failed to become ready: $url" >&2
  tail -80 "$log_file" >&2 || true
  return 1
}

clear_stale_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]] && ! kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    rm -f "$pid_file"
  fi
}

port_available() {
  local host="$1"
  local port="$2"
  "$PYTHON_BIN" - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
PY
}

require_unmanaged_port_free() {
  local name="$1"
  local host="$2"
  local port="$3"
  local pid_file="$4"
  if [[ -f "$pid_file" ]]; then
    return 0
  fi
  if ! port_available "$host" "$port"; then
    echo "$name port $host:$port is already in use, but no managed PID file exists." >&2
    echo "Stop the stale process or set a different port with RADAR_API_PORT/RADAR_UI_PORT." >&2
    if command -v ss >/dev/null 2>&1; then
      ss -ltnp | grep ":$port " >&2 || true
    fi
    return 1
  fi
}

clear_stale_pid "$api_pid_file"
clear_stale_pid "$ui_pid_file"
require_unmanaged_port_free "Radar API" "$API_HOST" "$API_PORT" "$api_pid_file"
if [[ "$UI_MODE" != "embedded" ]]; then
  require_unmanaged_port_free "Radar UI" "$UI_HOST" "$UI_PORT" "$ui_pid_file"
fi

if [[ -f "$api_pid_file" ]] && kill -0 "$(cat "$api_pid_file")" 2>/dev/null; then
  echo "Radar API already running with PID $(cat "$api_pid_file")"
else
  (
    cd "$ROOT_DIR/services/radar_api"
    nohup setsid "$PYTHON_BIN" -m uvicorn app.main:app --host "$API_HOST" --port "$API_PORT" \
      > "$LOG_DIR/radar_api.log" 2>&1 < /dev/null &
    echo $! > "$api_pid_file"
  )
  echo "Started Radar API: http://$API_HOST:$API_PORT"
fi
wait_for_url "Radar API" "http://$API_HOST:$API_PORT/api/health" "$LOG_DIR/radar_api.log"

if [[ "$UI_MODE" == "embedded" ]]; then
  if [[ ! -f "$ROOT_DIR/apps/radar-workbench/dist/index.html" ]]; then
    echo "Built frontend not found. Run ./scripts/install_radar_workbench.sh first." >&2
    exit 1
  fi
  echo "Radar UI served by API: http://$API_HOST:$API_PORT/"
elif [[ -f "$ui_pid_file" ]] && kill -0 "$(cat "$ui_pid_file")" 2>/dev/null; then
  echo "Radar UI already running with PID $(cat "$ui_pid_file")"
else
  (
    cd "$ROOT_DIR/apps/radar-workbench"
    if [[ ! -d node_modules ]]; then
      npm install
    fi
    nohup setsid npm run dev -- --host "$UI_HOST" --port "$UI_PORT" --strictPort \
      > "$LOG_DIR/radar_ui.log" 2>&1 < /dev/null &
    echo $! > "$ui_pid_file"
  )
  echo "Started Radar UI: http://$UI_HOST:$UI_PORT"
fi
if [[ "$UI_MODE" == "embedded" ]]; then
  wait_for_url "Radar UI" "http://$API_HOST:$API_PORT/" "$LOG_DIR/radar_api.log"
else
  wait_for_url "Radar UI" "http://$UI_HOST:$UI_PORT/" "$LOG_DIR/radar_ui.log"
fi

echo "Logs: $LOG_DIR"
