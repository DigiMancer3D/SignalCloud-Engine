#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
sc_force_normalize_timestamps "$ROOT"
echo "SignalCloud source timestamps normalized and generated build caches removed."
echo "Shared Python environment was preserved: $SC_PYTHON_ENV"
