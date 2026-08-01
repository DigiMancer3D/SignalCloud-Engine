#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
SC_PYCACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/signalcloud-native-quick-pycache.XXXXXX")"
export PYTHONPYCACHEPREFIX="$SC_PYCACHE_DIR"
trap 'rm -rf -- "$SC_PYCACHE_DIR"' EXIT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
cd "$ROOT"

sc_repair_future_timestamps "$ROOT"

sc_prepare_cmake_build_dir "$ROOT" "$ROOT/build-core" Ninja

cmake -S . -B build-core -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DSC_BUILD_GUI=OFF \
  -DBUILD_TESTING=ON
cmake --build build-core --target signalcloud_native_stress_route_tests signalcloud_machine_profile_tests signalcloud_pcp3_asset_tests --parallel
ctest --test-dir build-core -R "signalcloud_(native_stress_route|machine_profile|pcp3_asset)_tests" --output-on-failure

PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
"$PYTHON" -m py_compile tools/native_stress_launcher.py tools/native_stress_hud.py tools/signalcloud_launcher.py tools/stress_content_catalog.py tools/stress_workload_registry.py tools/machine_profile_manager.py tools/pcp3/*.py tools/pcp3_editor.py
"$PYTHON" -m unittest tests.test_native_stress_hud tests.test_pcp3_pipeline -v

for script in scripts/*.sh; do
  bash -n "$script"
done

printf 'PASS: quick native route, machine-profile promotion kernel, workload registry, GUI defaults, movable live HUD, PCP3 pipeline, finale options, and launcher validation\n'
