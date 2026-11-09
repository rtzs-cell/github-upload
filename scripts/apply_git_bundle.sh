#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE=""
TARGET_TAG=""
INSTALL_DEPENDENCIES=0
RESTART_MODE="auto"

usage() {
  cat <<'EOF'
Usage: ./scripts/apply_git_bundle.sh BUNDLE [options]

Verify and apply a radar-workbench release bundle to this Git checkout.

Options:
  --tag TAG                Select a release tag from the bundle
  --install-dependencies   Re-run the installer after switching versions
  --restart                Start services after the update even if stopped
  --no-restart             Leave services stopped after the update
  -h, --help               Show this help

The default preserves the current service state. Tracked source changes must be
clean; ignored runtime data and .env.radar are preserved.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      shift
      TARGET_TAG="${1:-}"
      ;;
    --install-dependencies)
      INSTALL_DEPENDENCIES=1
      ;;
    --restart)
      RESTART_MODE="always"
      ;;
    --no-restart)
      RESTART_MODE="never"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -* )
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$BUNDLE" ]]; then
        echo "Only one bundle may be supplied." >&2
        exit 2
      fi
      BUNDLE="$1"
      ;;
  esac
  shift
done

[[ -n "$BUNDLE" ]] || { usage >&2; exit 2; }
BUNDLE="$(realpath "$BUNDLE")"
[[ -f "$BUNDLE" ]] || { echo "Bundle not found: $BUNDLE" >&2; exit 1; }
git -C "$ROOT_DIR" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "The target directory is not a Git checkout: $ROOT_DIR" >&2
  exit 1
}

if ! git -C "$ROOT_DIR" diff --quiet || ! git -C "$ROOT_DIR" diff --cached --quiet; then
  echo "Tracked files have local changes. Commit or stash them before updating." >&2
  exit 1
fi

CHECKSUM_FILE="$BUNDLE.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
  (
    cd "$(dirname "$BUNDLE")"
    sha256sum -c "$(basename "$CHECKSUM_FILE")"
  )
else
  echo "Warning: no checksum file found at $CHECKSUM_FILE" >&2
fi

git -C "$ROOT_DIR" bundle verify "$BUNDLE"

mapfile -t BUNDLE_TAGS < <(
  git -C "$ROOT_DIR" bundle list-heads "$BUNDLE" |
    awk '$2 ~ /^refs\/tags\/radar-v[^^]+$/ {sub("refs/tags/", "", $2); print $2}'
)
if [[ -z "$TARGET_TAG" ]]; then
  if [[ "${#BUNDLE_TAGS[@]}" -ne 1 ]]; then
    echo "Bundle contains ${#BUNDLE_TAGS[@]} radar release tags; select one with --tag." >&2
    printf '  %s\n' "${BUNDLE_TAGS[@]}" >&2
    exit 1
  fi
  TARGET_TAG="${BUNDLE_TAGS[0]}"
fi
if ! printf '%s\n' "${BUNDLE_TAGS[@]}" | grep -Fxq "$TARGET_TAG"; then
  echo "Tag is not present in the bundle: $TARGET_TAG" >&2
  exit 1
fi

PREVIOUS_COMMIT="$(git -C "$ROOT_DIR" rev-parse HEAD)"
PREVIOUS_BRANCH="$(git -C "$ROOT_DIR" symbolic-ref --quiet --short HEAD || true)"
CANDIDATE_REF="refs/radar-updates/candidate-$$"
SUCCESS=0
SWITCHED=0
WAS_RUNNING=0
SHOULD_START=0
STOP_ATTEMPTED=0

for pid_file in \
  "$ROOT_DIR/outputs/radar_workbench/logs/radar_api.pid" \
  "$ROOT_DIR/outputs/radar_workbench/logs/radar_ui.pid"; do
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    WAS_RUNNING=1
  fi
done
case "$RESTART_MODE" in
  always) SHOULD_START=1 ;;
  never) SHOULD_START=0 ;;
  auto) SHOULD_START="$WAS_RUNNING" ;;
esac

rollback() {
  local status="$1"
  trap - EXIT
  set +e
  git -C "$ROOT_DIR" update-ref -d "$CANDIDATE_REF"
  if [[ "$SUCCESS" -ne 1 && "$SWITCHED" -eq 1 ]]; then
    echo "Update failed; restoring $PREVIOUS_COMMIT." >&2
    "$ROOT_DIR/scripts/stop_radar_workbench.sh" >/dev/null 2>&1 || true
    if [[ -n "$PREVIOUS_BRANCH" ]]; then
      git -C "$ROOT_DIR" checkout --quiet "$PREVIOUS_BRANCH" || \
        git -C "$ROOT_DIR" checkout --quiet --detach "$PREVIOUS_COMMIT"
    else
      git -C "$ROOT_DIR" checkout --quiet --detach "$PREVIOUS_COMMIT"
    fi
  fi
  if [[ "$SUCCESS" -ne 1 && "$WAS_RUNNING" -eq 1 && ( "$SWITCHED" -eq 1 || "$STOP_ATTEMPTED" -eq 1 ) ]]; then
    "$ROOT_DIR/scripts/start_radar_workbench.sh" || true
  fi
  exit "$status"
}
trap 'rollback $?' EXIT

git -C "$ROOT_DIR" fetch --quiet "$BUNDLE" "refs/tags/$TARGET_TAG:$CANDIDATE_REF"
TARGET_OBJECT="$(git -C "$ROOT_DIR" rev-parse "$CANDIDATE_REF")"
TARGET_COMMIT="$(git -C "$ROOT_DIR" rev-parse "$CANDIDATE_REF^{commit}")"

if ! git -C "$ROOT_DIR" merge-base --is-ancestor "$PREVIOUS_COMMIT" "$TARGET_COMMIT"; then
  echo "Current commit is not an ancestor of $TARGET_TAG; refusing a divergent update." >&2
  exit 1
fi
if git -C "$ROOT_DIR" show-ref --verify --quiet "refs/tags/$TARGET_TAG"; then
  EXISTING_OBJECT="$(git -C "$ROOT_DIR" rev-parse "refs/tags/$TARGET_TAG")"
  if [[ "$EXISTING_OBJECT" != "$TARGET_OBJECT" ]]; then
    echo "Local tag $TARGET_TAG differs from the signed-off bundle tag." >&2
    exit 1
  fi
else
  git -C "$ROOT_DIR" update-ref "refs/tags/$TARGET_TAG" "$TARGET_OBJECT"
fi

if [[ "$WAS_RUNNING" -eq 1 ]]; then
  STOP_ATTEMPTED=1
  "$ROOT_DIR/scripts/stop_radar_workbench.sh"
fi
git -C "$ROOT_DIR" checkout --quiet --detach "$TARGET_TAG"
SWITCHED=1

[[ -s "$ROOT_DIR/VERSION" ]] || { echo "Release has no VERSION file." >&2; exit 1; }
RELEASE_VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
[[ "$TARGET_TAG" == "radar-v$RELEASE_VERSION" ]] || {
  echo "Release tag $TARGET_TAG does not match VERSION=$RELEASE_VERSION." >&2
  exit 1
}
[[ -f "$ROOT_DIR/apps/radar-workbench/dist/index.html" ]] || {
  echo "Release has no prebuilt frontend." >&2
  exit 1
}

if [[ "$INSTALL_DEPENDENCIES" -eq 1 ]]; then
  "$ROOT_DIR/scripts/install_radar_workbench.sh"
fi
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  "$ROOT_DIR/scripts/verify_deployment.sh"
else
  echo "No local .venv found; source integrity passed, deployment verification skipped."
fi
if [[ "$SHOULD_START" -eq 1 ]]; then
  "$ROOT_DIR/scripts/start_radar_workbench.sh"
fi

SUCCESS=1
git -C "$ROOT_DIR" update-ref -d "$CANDIDATE_REF"
echo "Updated successfully: $PREVIOUS_COMMIT -> $TARGET_TAG ($TARGET_COMMIT)"
