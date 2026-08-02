#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
sc_ensure_portable_core
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
exec "$PYTHON" "$ROOT/tools/signalcloud_studio.py" --root "$ROOT" --tool light-lab "$@"
