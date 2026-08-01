#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
"$ROOT/scripts/compile_illuminosity_runtime.sh"
BINARY=""
for candidate in \
  "$ROOT/build/signalcloud_illuminosity_bake" \
  "$ROOT/build-core/signalcloud_illuminosity_bake"; do
  if [[ -x "$candidate" ]]; then
    BINARY="$candidate"
    break
  fi
done
if [[ -z "$BINARY" ]]; then
  sc_prepare_cmake_build_dir "$ROOT" "$ROOT/build-core" Ninja
  cmake -S "$ROOT" -B "$ROOT/build-core" -G Ninja -DCMAKE_BUILD_TYPE=Debug -DSC_BUILD_GUI=OFF
  cmake --build "$ROOT/build-core" --target signalcloud_illuminosity_bake --parallel
  BINARY="$ROOT/build-core/signalcloud_illuminosity_bake"
fi
"$BINARY" "$ROOT" "$@"
