#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
echo "Game root        : $SC_PROJECT_ROOT"
echo "Live Tape parent : $SC_LIVE_TAPE_PARENT"
echo "Game executable  : $SC_PROJECT_ROOT/build/almond_signal_live_tape"
echo "Native stress    : $SC_PROJECT_ROOT/build/almond_signal_native_stress"
echo "Catalog JSON     : $SC_PROJECT_ROOT/reports/stress_content_catalog.json"
