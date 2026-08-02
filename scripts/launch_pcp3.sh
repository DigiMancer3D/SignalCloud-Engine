#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
sc_ensure_portable_core
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
mkdir -p "$ROOT/reports"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG="$ROOT/reports/pcp3_editor_${STAMP}.log"
if [[ ! -x "$ROOT/build/almond_signal_pcp_preview" ]]; then
  echo "Point Cloud Paint++ is opening in authoring-only mode."
  echo "The optional native 3D preview is not built; build it later with: ./scripts/setup_dev_environment.sh"
fi
set +e
"$PYTHON" "$ROOT/tools/signalcloud_studio.py" --root "$ROOT" --tool pcp3 2>&1 | tee -a "$LOG"
status=${PIPESTATUS[0]}
set -e
if (( status != 0 )); then
  echo "Point Cloud Paint++ exited with status $status"
  echo "Editor log: $LOG"
  [[ -f "$ROOT/reports/pcp3_crash_latest.log" ]] && echo "Crash log: $ROOT/reports/pcp3_crash_latest.log"
fi
exit "$status"
