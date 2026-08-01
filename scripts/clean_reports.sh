#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
KEEP_RUNS="${PCP3_KEEP_NATIVE_RUNS:-3}"
MODE="${1:-manual}"
REPORTS="$ROOT/reports"
ARCHIVE="$ROOT/user_data/report_archive"
STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$REPORTS" "$ARCHIVE/native_stress_runs" "$ARCHIVE/transient/$STAMP"

# Move old completed native stress runs into user_data instead of deleting them.
if [[ -d "$REPORTS/native_stress_runs" ]]; then
  mapfile -t runs < <(find "$REPORTS/native_stress_runs" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
  if (( ${#runs[@]} > KEEP_RUNS )); then
    for run in "${runs[@]:KEEP_RUNS}"; do
      mv "$run" "$ARCHIVE/native_stress_runs/"
    done
  fi
fi

# Live-status pointers are transient and should never be inherited as current state.
for file in native_stress_live.json native_stress_latest_path.txt; do
  if [[ -f "$REPORTS/$file" ]]; then
    mv "$REPORTS/$file" "$ARCHIVE/transient/$STAMP/$file"
  fi
done

# Keep only the five newest PCP3 editor logs; archive older ones.
mapfile -t logs < <(find "$REPORTS" -maxdepth 1 -type f -name 'pcp3_editor_*.log' -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2-)
if (( ${#logs[@]} > 5 )); then
  for log in "${logs[@]:5}"; do
    mv "$log" "$ARCHIVE/transient/$STAMP/"
  done
fi

# Remove empty timestamp archive created when there was nothing transient.
rmdir "$ARCHIVE/transient/$STAMP" 2>/dev/null || true
printf 'Report cleanup complete (%s). Kept newest %s native stress run(s); older results were archived under user_data/report_archive.\n' "$MODE" "$KEEP_RUNS"
