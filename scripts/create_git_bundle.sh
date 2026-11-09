#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
TARGET_TAG="radar-v$VERSION"
FROM_TAG=""
OUTPUT=""
FORCE=0

usage() {
  cat <<'EOF'
Usage: ./scripts/create_git_bundle.sh [options]

Create a verified Git release bundle and a matching SHA-256 file.

Options:
  --tag TAG        Target release tag (default: radar-v<VERSION>)
  --from-tag TAG   Create an incremental bundle after this release tag
  --output FILE    Output bundle path
  --force          Replace an existing output bundle and checksum
  -h, --help       Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      shift
      TARGET_TAG="${1:-}"
      ;;
    --from-tag)
      shift
      FROM_TAG="${1:-}"
      ;;
    --output)
      shift
      OUTPUT="${1:-}"
      ;;
    --force)
      FORCE=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

[[ -n "$TARGET_TAG" ]] || { echo "Target tag cannot be empty." >&2; exit 2; }
[[ "$TARGET_TAG" == radar-v* ]] || {
  echo "Release tag must use the radar-v<version> format." >&2
  exit 2
}
git -C "$ROOT_DIR" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "Not a Git repository: $ROOT_DIR" >&2
  exit 1
}
git -C "$ROOT_DIR" show-ref --verify --quiet "refs/tags/$TARGET_TAG" || {
  echo "Release tag does not exist: $TARGET_TAG" >&2
  exit 1
}
if [[ "$(git -C "$ROOT_DIR" cat-file -t "$TARGET_TAG")" != "tag" ]]; then
  echo "Release tag must be annotated: $TARGET_TAG" >&2
  exit 1
fi
TAG_VERSION="$(git -C "$ROOT_DIR" show "$TARGET_TAG:VERSION" 2>/dev/null | tr -d '[:space:]')"
if [[ "$TARGET_TAG" != "radar-v$TAG_VERSION" ]]; then
  echo "Tag $TARGET_TAG does not match VERSION=$TAG_VERSION at the tagged commit." >&2
  exit 1
fi

if [[ -n "$FROM_TAG" ]]; then
  git -C "$ROOT_DIR" show-ref --verify --quiet "refs/tags/$FROM_TAG" || {
    echo "Base tag does not exist: $FROM_TAG" >&2
    exit 1
  }
  git -C "$ROOT_DIR" merge-base --is-ancestor "$FROM_TAG^{commit}" "$TARGET_TAG^{commit}" || {
    echo "$FROM_TAG is not an ancestor of $TARGET_TAG." >&2
    exit 1
  }
fi

if [[ -z "$OUTPUT" ]]; then
  mkdir -p "$ROOT_DIR/deliverables"
  if [[ -n "$FROM_TAG" ]]; then
    OUTPUT="$ROOT_DIR/deliverables/${FROM_TAG}-to-${TARGET_TAG}.bundle"
  else
    OUTPUT="$ROOT_DIR/deliverables/${TARGET_TAG}-full.bundle"
  fi
fi
OUTPUT="$(realpath -m "$OUTPUT")"
CHECKSUM_FILE="$OUTPUT.sha256"
mkdir -p "$(dirname "$OUTPUT")"

if [[ "$FORCE" -ne 1 && ( -e "$OUTPUT" || -e "$CHECKSUM_FILE" ) ]]; then
  echo "Output already exists. Use --force to replace it: $OUTPUT" >&2
  exit 1
fi

rm -f "$OUTPUT" "$CHECKSUM_FILE"
if [[ -n "$FROM_TAG" ]]; then
  git -C "$ROOT_DIR" bundle create "$OUTPUT" "$TARGET_TAG" "^$FROM_TAG"
else
  git -C "$ROOT_DIR" bundle create "$OUTPUT" "$TARGET_TAG"
fi
git -C "$ROOT_DIR" bundle verify "$OUTPUT" >/dev/null
(
  cd "$(dirname "$OUTPUT")"
  sha256sum "$(basename "$OUTPUT")" > "$(basename "$CHECKSUM_FILE")"
)

echo "Created bundle: $OUTPUT"
echo "Checksum: $CHECKSUM_FILE"
git -C "$ROOT_DIR" bundle list-heads "$OUTPUT"
du -h "$OUTPUT"
