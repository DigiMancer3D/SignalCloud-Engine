#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
sc_ensure_portable_core
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
cd "$SC_PROJECT_ROOT"
exec "$PYTHON" tools/playbook_editor.py --root "$SC_PROJECT_ROOT" "$@"
