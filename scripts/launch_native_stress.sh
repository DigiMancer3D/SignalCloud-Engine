#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
sc_ensure_portable_core
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
[[ -x "$ROOT/build/almond_signal_native_stress" ]] || {
  echo "Native stress executable not built. Run ./scripts/setup_dev_environment.sh" >&2
  exit 4
}
exec "$PYTHON" "$ROOT/tools/native_stress_watchdog.py" "$ROOT" -- \
  "$ROOT/build/almond_signal_native_stress" --root="$ROOT" "$@"
