#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
OUTPUT="${1:-$SC_LIVE_TAPE_PARENT/SignalCloud-Public-Source-Audit}"
rm -rf -- "$OUTPUT"
"$PYTHON" "$ROOT/tools/public_release_audit.py" "$ROOT" \
  --output "$OUTPUT" --replace --strict-release
printf '\nAudit report:\n  %s\n' "$OUTPUT/SignalCloud-Engine/PUBLIC_SOURCE_AUDIT.md"
