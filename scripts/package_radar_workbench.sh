#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_LOCAL_DATA=0
WITH_EXAMPLE_DATA=0
EXPERIMENT_ID=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-local-data) WITH_LOCAL_DATA=1 ;;
    --with-example-data) WITH_EXAMPLE_DATA=1 ;;
    --with-experiment) shift; EXPERIMENT_ID="${1:-}" ;;
    --output) shift; OUTPUT="${1:-}" ;;
    *) echo "Usage: $0 [--with-local-data] [--with-example-data] [--with-experiment ID] [--output FILE]" >&2; exit 2 ;;
  esac
  shift
done

if [[ ! -f "$ROOT_DIR/apps/radar-workbench/dist/index.html" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Frontend build is missing and npm is unavailable." >&2
    exit 1
  fi
  (cd "$ROOT_DIR/apps/radar-workbench" && npm ci && npm run build)
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -z "$OUTPUT" ]]; then
  OUTPUT="$ROOT_DIR/radar-workbench-$TIMESTAMP.tar.zst"
fi
OUTPUT="$(realpath -m "$OUTPUT")"

paths=(VERSION README.md .gitignore .dockerignore .env.docker.example Containerfile compose.yaml docs services experiments scripts apps/radar-workbench)
if [[ "$WITH_LOCAL_DATA" -eq 1 ]]; then
  [[ -d "$ROOT_DIR/outputs/radar_workbench/experiments" ]] && paths+=(outputs/radar_workbench/experiments)
  [[ -d "$ROOT_DIR/outputs/radar_workbench/campaigns" ]] && paths+=(outputs/radar_workbench/campaigns)
  [[ -d "$ROOT_DIR/outputs/radar_workbench/path_exports" ]] && paths+=(outputs/radar_workbench/path_exports)
fi
if [[ "$WITH_EXAMPLE_DATA" -eq 1 ]]; then
  paths+=(outputs/sionna_radar_campaigns/C002_full_radar_sensing)
fi
if [[ -n "$EXPERIMENT_ID" ]]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "jq is required to generate the portable scene JSON." >&2
    exit 1
  fi
  if [[ ! "$EXPERIMENT_ID" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "Invalid experiment ID: $EXPERIMENT_ID" >&2
    exit 2
  fi
  EXPERIMENT_ROOT="$ROOT_DIR/outputs/radar_workbench/experiments/$EXPERIMENT_ID"
  if [[ ! -f "$EXPERIMENT_ROOT/experiment_manifest.json" || ! -f "$EXPERIMENT_ROOT/input/experiment_config.json" ]]; then
    echo "Experiment is incomplete or does not exist: $EXPERIMENT_ID" >&2
    exit 1
  fi
  if [[ "$WITH_LOCAL_DATA" -eq 0 ]]; then
    paths+=("outputs/radar_workbench/experiments/$EXPERIMENT_ID")
  fi
fi

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
cat > "$TEMP_DIR/DEPLOYMENT_MANIFEST.txt" <<EOF
created_at_utc=$TIMESTAMP
local_data=$WITH_LOCAL_DATA
example_data=$WITH_EXAMPLE_DATA
included_experiment=${EXPERIMENT_ID:-none}
source_commit=$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || echo unavailable)
source_worktree_dirty=$(git -C "$ROOT_DIR" status --porcelain 2>/dev/null | grep -q . && echo true || echo false)
install_command=./scripts/install_radar_workbench.sh
EOF

temp_paths=(DEPLOYMENT_MANIFEST.txt)
if [[ -n "$EXPERIMENT_ID" ]]; then
  PORTABLE_SCENE_DIR="$TEMP_DIR/portable_scenes/$EXPERIMENT_ID"
  mkdir -p "$PORTABLE_SCENE_DIR"
  jq \
    --arg exported_at "$TIMESTAMP" \
    --arg experiment_id "$EXPERIMENT_ID" \
    '{
      export_kind: "radar_workbench_scene",
      schema_version: "0.2.0",
      exported_at_utc: $exported_at,
      source_experiment_id: $experiment_id,
      scene: (.scene | del(.scene_xml, .scene_xml_path))
    }' \
    "$EXPERIMENT_ROOT/input/experiment_config.json" \
    > "$PORTABLE_SCENE_DIR/scene_import.json"
  cat > "$PORTABLE_SCENE_DIR/README.md" <<EOF
# 场景导入

完整实验方案已放在：

\`outputs/radar_workbench/experiments/$EXPERIMENT_ID/\`

安装脚本会自动重定位其中的场景路径。若只需把几何场景导入另一实验方案，请在界面“场景几何”中选择“导入场景 JSON”，使用本目录的 \`scene_import.json\`，然后点击“保存场景”。
EOF
  (
    cd "$PORTABLE_SCENE_DIR"
    sha256sum scene_import.json > scene_import.json.sha256
  )
  temp_paths+=(portable_scenes)
fi

tar --zstd -cf "$OUTPUT" \
  --transform='s,^,radar_simulate/,' \
  --exclude='apps/radar-workbench/node_modules' \
  --exclude='apps/radar-workbench/.vite' \
  --exclude='services/radar_api/.pytest_cache' \
  --exclude='**/__pycache__' \
  -C "$ROOT_DIR" "${paths[@]}" \
  -C "$TEMP_DIR" "${temp_paths[@]}"

(
  cd "$(dirname "$OUTPUT")"
  sha256sum "$(basename "$OUTPUT")" > "$(basename "$OUTPUT").sha256"
)

echo "Created: $OUTPUT"
echo "Checksum: $OUTPUT.sha256"
du -h "$OUTPUT"
