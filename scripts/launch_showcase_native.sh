#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
sc_ensure_portable_core
ROOT="$SC_PROJECT_ROOT"
ASSET="${1:-$ROOT/content/starter/showcase/office_shipping_crate/office_shipping_crate.pcp3cloud}"
PHYSICS="${2:-$ROOT/content/starter/showcase/office_shipping_crate/office_shipping_crate.scphysics}"
TEST="${3:-drop}"
if (($# >= 3)); then shift 3; else set --; fi
VISUALIZATION="${ASSET%.pcp3cloud}.scshowcase"
BINARY="$ROOT/build/almond_signal_showcase"
if [[ ! -x "$BINARY" ]]; then
  echo "Native Showcase is not built; preparing SignalCloud native targets automatically."
  "$ROOT/scripts/setup_dev_environment.sh"
fi
args=(
  --asset="$ASSET"
  --physics="$PHYSICS"
  --test="$TEST"
  --video="${SC_VIDEO_BACKEND:-auto}"
  --snapshot-dir="$ROOT/user_data/showcase_snapshots"
)
[[ -f "$VISUALIZATION" ]] && args+=(--visualization="$VISUALIZATION")
exec "$BINARY" "${args[@]}" "$@"
