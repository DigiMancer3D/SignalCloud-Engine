#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
sc_repair_future_timestamps "$ROOT"
SHARED_DEPS="$SC_SHARED_DEPS"
SDL_INSTALL="$SHARED_DEPS/sdl3-install"
cd "$ROOT"

missing_commands=()
for command in python3 cmake c++ tar ninja; do
  command -v "$command" >/dev/null 2>&1 || missing_commands+=("$command")
done
if ((${#missing_commands[@]} > 0)); then
  printf 'Missing required commands: %s\n' "${missing_commands[*]}"
  printf 'Install with:\n  sudo apt update && sudo apt install -y build-essential cmake ninja-build python3 python3-venv python3-tk tar\n'
  exit 2
fi

packages=(git ninja-build pkg-config python3-venv python3-tk libgl1-mesa-dev libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxi-dev libxfixes-dev libxss-dev libxtst-dev libxkbcommon-dev libwayland-dev wayland-protocols libdecor-0-dev)
missing_packages=()
if command -v dpkg-query >/dev/null 2>&1; then
  for package in "${packages[@]}"; do
    dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' || missing_packages+=("$package")
  done
fi
if ((${#missing_packages[@]} > 0)); then
  echo "Installing only missing Python/SDL3/OpenGL/X11/Wayland development packages:"
  printf '  %s\n' "${missing_packages[*]}"
  sudo apt-get update
  sudo apt-get install -y "${missing_packages[@]}"
else
  echo "SignalCloud platform build prerequisites are already present."
fi

mkdir -p "$(dirname "$SC_PYTHON_ENV")"
if [[ ! -x "$SC_PYTHON" ]]; then
  python3 -m venv "$SC_PYTHON_ENV"
  echo "Created shared SignalCloud Python environment: $SC_PYTHON_ENV"
else
  echo "Reusing shared SignalCloud Python environment: $SC_PYTHON_ENV"
fi

# Use the shared interpreter after the environment has been created or found.
# Keep a system-python fallback for damaged or manually copied environments.
PYTHON="$SC_PYTHON"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

sc_ensure_portable_core

find_sdl_config() {
  find "$1" -type f -name SDL3Config.cmake -print -quit 2>/dev/null || true
}

mkdir -p "$SHARED_DEPS"
SDL_CONFIG="$(find_sdl_config "$SDL_INSTALL")"
if [[ -n "$SDL_CONFIG" ]]; then
  echo "Reusing SignalCloud SDL3 cache: $SDL_INSTALL"
else
  echo "No installed SDL3 cache was found. The pinned CMake fallback will download and build SDL3 once."
fi

"$ROOT/scripts/compile_illuminosity_runtime.sh"
"$ROOT/scripts/compile_material_runtime.sh"
"$ROOT/scripts/compile_audio_interference_runtime.sh"
"$ROOT/scripts/compile_playbook_runtime.sh"
"$PYTHON" -m tools.signalcloud_fonts.validator "$ROOT/content/core/fonts/terminal_00/Terminal_00.scfont"
"$PYTHON" tools/check_cpp_literals.py engine/ai/playbook.cpp engine/physics/showcase_runtime.cpp engine/physics/showcase_visualization.cpp engine/items/tupd_runtime.cpp engine/ui/tupd_ghost_preview.cpp app/game_main.cpp app/tupd_main.cpp app/main.cpp app/native_stress_main.cpp app/showcase_main.cpp app/illuminosity_bake_main.cpp engine/assets/hot_reload_status.cpp engine/audio/audio_interference_runtime.cpp engine/materials/material_runtime.cpp engine/scfont/scfont.cpp engine/scfont/font_service.cpp engine/scfont/text_point_adapter.cpp engine/render/point_renderer.cpp engine/render/room_visibility.cpp engine/render/sound_ripple.cpp engine/ui/ar_interface.cpp engine/ui/scui_native_runtime.cpp engine/world/liminal_level.cpp
# The embedded GLSL checker has a single optional path argument. The shader
# source currently lives in point_renderer.cpp; the remaining C++ files are
# covered by the literal preflight immediately above.
"$PYTHON" tools/check_embedded_glsl.py engine/render/point_renderer.cpp
"$PYTHON" -m py_compile tools/public_release_audit.py
"$ROOT/scripts/repair_user_light_envelopes.sh"
"$PYTHON" tools/asset_doctor/asset_doctor.py "$ROOT" --repair-paths
"$PYTHON" -m tools.asset_doctor.hot_reload_bridge "$ROOT"
"$PYTHON" tools/stress_content_catalog.py "$ROOT" --output-prefix reports/stress_content_catalog
"$PYTHON" tools/stress_workload_registry.py "$ROOT"

sc_prepare_cmake_build_dir "$ROOT" "$ROOT/build" Ninja

cmake_args=(
  -S . -B build -G Ninja
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
  -DSC_BUILD_GUI=ON
)
if [[ -n "$SDL_CONFIG" ]]; then
  cmake_args+=("-DCMAKE_PREFIX_PATH=$SDL_INSTALL" -DSC_FETCH_SDL3=OFF)
else
  cmake_args+=("-DFETCHCONTENT_BASE_DIR=$SHARED_DEPS/fetch" -DSC_FETCH_SDL3=ON)
fi
cmake "${cmake_args[@]}"
cmake --build build --parallel "$SC_BUILD_JOBS"

if [[ ! -x "$ROOT/build/almond_signal_live_tape" ]]; then
  echo "The native ALMOND SIGNAL executable was not produced."
  exit 5
fi
if [[ ! -x "$ROOT/build/almond_signal_native_stress" ]]; then
  echo "The engine-native stress executable was not produced."
  exit 6
fi
if [[ ! -x "$ROOT/build/almond_signal_pcp_preview" ]]; then
  echo "The Point Cloud Paint++ native preview executable was not produced."
  exit 7
fi
if [[ ! -x "$ROOT/build/almond_signal_showcase" ]]; then
  echo "The 3D Environment & Physics Showcase executable was not produced."
  exit 8
fi
if [[ ! -x "$ROOT/build/almond_signal_tupd_preview" ]]; then
  echo "The native Tupd sandbox executable was not produced."
  exit 9
fi

echo "SignalCloud Pivot 13 a3 Threshold Pursuit, Vertical Perception & Tablet Identity environment is ready."
echo "Project build: $ROOT/build"
echo "Shared Python environment: $SC_PYTHON_ENV"
echo "Layout mode: $SC_LAYOUT_MODE"
echo "Shared dependency root: $SHARED_DEPS"
echo "Native stress build: $ROOT/build/almond_signal_native_stress"
echo "Point Cloud Paint++ preview: $ROOT/build/almond_signal_pcp_preview"
echo "3D Environment & Physics Showcase: $ROOT/build/almond_signal_showcase"
echo "Tupd native sandbox: $ROOT/build/almond_signal_tupd_preview"
echo "Quick validation: ./scripts/run_native_stress_quick_tests.sh"
echo "Full tests: ./scripts/run_selftests.sh"
echo "Then: ./scripts/launch_control_panel.sh"
echo "Public source audit: ./scripts/audit_public_source.sh"
