#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
SDL_INSTALL="$SC_SHARED_DEPS/sdl3-install"
BACKEND="${1:-auto}"
POINTS="${2:-}"
case "$BACKEND" in auto|x11|wayland) ;; *) echo "Usage: $0 [auto|x11|wayland] [point_count]"; exit 2;; esac
if [[ -n "$POINTS" && ! "$POINTS" =~ ^[0-9]+$ ]]; then
  echo "Point count must contain digits only."
  exit 2
fi

sc_ensure_portable_core

if ! "$ROOT/scripts/compile_illuminosity_runtime.sh"; then
  echo "Illuminosity light compilation failed; the native game was not launched." >&2
  exit 3
fi
if ! "$ROOT/scripts/compile_material_runtime.sh"; then
  echo "Material compilation failed; the native game was not launched." >&2
  exit 3
fi
if ! "$ROOT/scripts/compile_audio_interference_runtime.sh"; then
  echo "Audio-interference compilation failed; the native game was not launched." >&2
  exit 3
fi

GAME="$ROOT/build/almond_signal_live_tape"
if [[ ! -x "$GAME" ]]; then
  echo "Native game is not built; preparing the SignalCloud runtime automatically."
  echo "Running: $ROOT/scripts/setup_dev_environment.sh"
  if ! "$ROOT/scripts/setup_dev_environment.sh"; then
    echo "Automatic native game preparation failed. Review the build error above." >&2
    exit 3
  fi
fi
if [[ ! -x "$GAME" ]]; then
  echo "Automatic preparation finished without producing the native game executable." >&2
  exit 4
fi

if [[ -d "$SDL_INSTALL/lib" ]]; then
  export LD_LIBRARY_PATH="$SDL_INSTALL/lib:${LD_LIBRARY_PATH:-}"
fi
args=("--video=$BACKEND" "--root=$ROOT")
if [[ -n "$POINTS" ]]; then args+=("--points=$POINTS"); fi
exec "$GAME" "${args[@]}"
