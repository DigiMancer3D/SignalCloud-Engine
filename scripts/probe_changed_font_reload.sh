#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
cd "$SC_PROJECT_ROOT"
exec "$PYTHON" -m tools.signalcloud_fonts.reload_probe "$SC_PROJECT_ROOT"
