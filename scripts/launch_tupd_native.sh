#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
sc_ensure_portable_core
ROOT="$SC_PROJECT_ROOT"
BINARY="$ROOT/build/almond_signal_tupd_preview"
if [[ ! -x "$BINARY" ]]; then
  echo "Native Tupd stage is not built; preparing SignalCloud runtime automatically."
  "$ROOT/scripts/setup_dev_environment.sh"
fi
if [[ ! -x "$BINARY" ]]; then
  echo "Native Tupd stage could not be built: $BINARY" >&2
  exit 1
fi
RECIPE="${1:-$ROOT/content/starter/tupd/compatible_signal_grip/compatible_signal_grip.tupd}"
shift || true
cd "$ROOT"
exec "$BINARY" --root="$ROOT" --recipe="$RECIPE" "$@"
