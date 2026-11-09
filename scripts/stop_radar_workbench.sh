#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/outputs/radar_workbench/logs"

for name in radar_ui radar_api; do
  pid_file="$LOG_DIR/$name.pid"
  if [[ -f "$pid_file" ]]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      kill -- "-$pid" 2>/dev/null || kill "$pid"
      for _ in $(seq 1 20); do
        if ! kill -0 -- "-$pid" 2>/dev/null; then
          break
        fi
        sleep 0.1
      done
      if kill -0 -- "-$pid" 2>/dev/null; then
        kill -KILL -- "-$pid" 2>/dev/null || true
      fi
      echo "Stopped $name PID $pid"
    fi
    rm -f "$pid_file"
  fi
done
