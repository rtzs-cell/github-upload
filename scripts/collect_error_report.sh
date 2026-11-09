#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOB_ID=""
OUTPUT=""

usage() {
  echo "Usage: $0 --job-id JOB_ID [--output REPORT.tar.gz]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job-id) shift; JOB_ID="${1:-}" ;;
    --output) shift; OUTPUT="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
  shift
done

if [[ -z "$JOB_ID" || ! "$JOB_ID" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "A valid --job-id is required." >&2
  usage
  exit 2
fi

if [[ -f "$ROOT_DIR/.env.radar" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env.radar"
  set +a
fi

OUTPUT_ROOT="${RADAR_OUTPUT_ROOT:-$ROOT_DIR/outputs/radar_workbench}"
JOB_DIR="$OUTPUT_ROOT/jobs/$JOB_ID"
CAMPAIGN_DIR="$OUTPUT_ROOT/campaigns/$JOB_ID"
if [[ ! -d "$JOB_DIR" ]]; then
  echo "Job directory not found: $JOB_DIR" >&2
  exit 1
fi

PYTHON_BIN="${RADAR_API_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || command -v python)"
  fi
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -z "$OUTPUT" ]]; then
  mkdir -p "$ROOT_DIR/deliverables"
  OUTPUT="$ROOT_DIR/deliverables/radar-error-report-${JOB_ID}-${TIMESTAMP}.tar.gz"
fi
OUTPUT="$(realpath -m "$OUTPUT")"

TEMP_DIR="$(mktemp -d)"
REPORT_DIR="$TEMP_DIR/radar-error-report-$JOB_ID"
mkdir -p "$REPORT_DIR/job" "$REPORT_DIR/logs" "$REPORT_DIR/run_metadata"
trap 'rm -rf "$TEMP_DIR"' EXIT

for name in job.json status.json task_manifest.json worker_events.jsonl logs.txt; do
  if [[ -f "$JOB_DIR/$name" ]]; then
    cp "$JOB_DIR/$name" "$REPORT_DIR/job/$name"
  fi
done

for name in radar_api.log radar_ui.log; do
  if [[ -f "$OUTPUT_ROOT/logs/$name" ]]; then
    tail -n 4000 "$OUTPUT_ROOT/logs/$name" > "$REPORT_DIR/logs/$name"
  fi
done

if [[ -d "$CAMPAIGN_DIR" ]]; then
  while IFS= read -r path; do
    relative="${path#"$CAMPAIGN_DIR"/}"
    target="$REPORT_DIR/run_metadata/$relative"
    mkdir -p "$(dirname "$target")"
    cp "$path" "$target"
  done < <(
    find "$CAMPAIGN_DIR" -type f \(
      -name config.yaml -o
      -name metadata.json -o
      -name metrics.json -o
      -name campaign_manifest.json -o
      -name pose_manifest.json -o
      -name beamforming_summary.json -o
      -name fmcw_summary.json
    \) -print
  )
fi

{
  echo "created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "job_id=$JOB_ID"
  echo "repo_root=$ROOT_DIR"
  echo "output_root=$OUTPUT_ROOT"
  echo "campaign_exists=$([[ -d "$CAMPAIGN_DIR" ]] && echo true || echo false)"
  echo
  echo "== operating system =="
  uname -a || true
  echo
  echo "== disk =="
  df -h "$ROOT_DIR" "$OUTPUT_ROOT" 2>&1 || true
  echo
  echo "== memory =="
  free -h 2>&1 || true
  echo
  echo "== GPU =="
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=index,name,driver_version,memory.total,memory.used --format=csv,noheader 2>&1 || true
  else
    echo "nvidia-smi not found"
  fi
  echo
  echo "== source revision =="
  git -C "$ROOT_DIR" rev-parse HEAD 2>&1 || true
  git -C "$ROOT_DIR" status --short 2>&1 || true
  echo
  echo "== fix markers =="
  grep -n "ensure_canonical_path_archive" "$ROOT_DIR/services/radar_api/app/core/path_layout.py" 2>&1 || true
  grep -n "canonicalize_path_arrays" "$ROOT_DIR/experiments/sionna_radar/src/sionna_radar/runner.py" 2>&1 || true
  echo
  echo "== source hashes =="
  sha256sum \
    "$ROOT_DIR/services/radar_api/app/core/path_layout.py" \
    "$ROOT_DIR/services/radar_api/app/core/beamforming.py" \
    "$ROOT_DIR/experiments/sionna_radar/src/sionna_radar/processing.py" \
    "$ROOT_DIR/experiments/sionna_radar/src/sionna_radar/runner.py" 2>&1 || true
} > "$REPORT_DIR/system.txt"

{
  echo "== API health =="
  curl -fsS --max-time 10 http://127.0.0.1:8000/api/health 2>&1 || true
  echo
  echo "== Sionna runtime health =="
  curl -fsS --max-time 30 http://127.0.0.1:8000/api/health/sionna_runtime 2>&1 || true
  echo
} > "$REPORT_DIR/health.txt"

"$PYTHON_BIN" - "$ROOT_DIR" "$CAMPAIGN_DIR" <<'PY' > "$REPORT_DIR/python_and_arrays.txt" 2>&1 || true
from __future__ import annotations

import importlib.metadata
import platform
import sys
import zipfile
from pathlib import Path

import numpy.lib.format

root = Path(sys.argv[1])
campaign = Path(sys.argv[2])
print("== Python ==")
print("executable:", sys.executable)
print("version:", sys.version.replace("\n", " "))
print("platform:", platform.platform())
for package in ("fastapi", "pydantic", "numpy", "scipy", "pandas", "pyarrow", "sionna-rt", "mitsuba", "drjit"):
    try:
        print(f"{package}: {importlib.metadata.version(package)}")
    except importlib.metadata.PackageNotFoundError:
        print(f"{package}: not installed in API Python")

print("\n== Relevant files ==")
if not campaign.is_dir():
    print("campaign directory not found:", campaign)
    raise SystemExit(0)

for path in sorted(campaign.rglob("*")):
    if path.is_file() and path.suffix in {".npz", ".json", ".yaml", ".csv", ".txt"}:
        print(f"{path.relative_to(campaign)} size_bytes={path.stat().st_size}")

print("\n== NPZ array headers only ==")
for path in sorted(campaign.rglob("*.npz")):
    print(f"[{path.relative_to(campaign)}] size_bytes={path.stat().st_size}")
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if not member.filename.endswith(".npy"):
                    continue
                with archive.open(member) as stream:
                    version = numpy.lib.format.read_magic(stream)
                    if version == (1, 0):
                        shape, _, dtype = numpy.lib.format.read_array_header_1_0(stream)
                    else:
                        shape, _, dtype = numpy.lib.format.read_array_header_2_0(stream)
                print(f"  {member.filename[:-4]} shape={shape} dtype={dtype} compressed_bytes={member.compress_size}")
    except Exception as exc:
        print(f"  ERROR reading NPZ headers: {type(exc).__name__}: {exc}")
PY

cat > "$REPORT_DIR/README.txt" <<EOF
This report contains task configuration/status, tracebacks, the last 4000 API/UI log lines,
software and hardware versions, source hashes, and NPZ array headers (shape/dtype only).
It does not contain CIR/path array values, imported model bytes, scene mesh bytes, or .env files.
Job: $JOB_ID
EOF

tar -czf "$OUTPUT" -C "$TEMP_DIR" "$(basename "$REPORT_DIR")"
echo "Created error report: $OUTPUT"
du -h "$OUTPUT"
