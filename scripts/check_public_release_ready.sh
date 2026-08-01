#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/signalcloud-public-release-check.XXXXXX")"
trap 'rm -rf -- "$TMP"' EXIT
"$PYTHON" "$ROOT/tools/public_release_audit.py" "$ROOT" \
  --output "$TMP/stage" --strict-release
