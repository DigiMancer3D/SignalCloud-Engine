#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
sc_ensure_portable_core
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON="${SC_PYTHON:-}"
if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
    PYTHON="$(command -v python3)"
fi
echo "Launching integrated +SCFS+ Alpha A1R4 v0.1.7 from: $ROOT"
exec "$PYTHON" "$ROOT/tools/scfs_main.py" --root "$ROOT" "$@"
