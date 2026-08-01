#!/usr/bin/env bash
set -euo pipefail
export TERM="${TERM:-xterm}"
export PYTHONDONTWRITEBYTECODE=1
SC_PYCACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/signalcloud-selftests-pycache.XXXXXX")"
export PYTHONPYCACHEPREFIX="$SC_PYCACHE_DIR"
cleanup_selftest_cache() { rm -rf -- "$SC_PYCACHE_DIR"; }
trap cleanup_selftest_cache EXIT
trap 'code=$?; echo "FAIL: SignalCloud self-tests stopped at line ${LINENO} (exit ${code})." >&2; exit ${code}' ERR
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
sc_repair_future_timestamps "$ROOT"
cd "$ROOT"
find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

"$ROOT/scripts/compile_illuminosity_runtime.sh"
"$ROOT/scripts/compile_material_runtime.sh"
"$ROOT/scripts/compile_audio_interference_runtime.sh"
"$ROOT/scripts/compile_playbook_runtime.sh"
"$PYTHON" -m tools.signalcloud_fonts.validator "$ROOT/content/core/fonts/terminal_00/Terminal_00.scfont"
"$ROOT/scripts/probe_changed_font_reload.sh"
"$ROOT/scripts/report_wallpaper_pattern.sh"
"$ROOT/scripts/repair_user_light_envelopes.sh"
"$ROOT/scripts/probe_changed_light_reload.sh"
"$ROOT/scripts/export_sclight.sh" --output user_data/studio/a4a3_selftest_export.sclight --no-compile
rm -f "$ROOT/user_data/studio/a4a3_selftest_export.sclight"
"$PYTHON" tools/asset_doctor/asset_doctor.py "$ROOT" --repair-paths
"$PYTHON" -m tools.asset_doctor.hot_reload_bridge "$ROOT"
"$PYTHON" tools/check_cpp_literals.py engine/ai/playbook.cpp engine/benchmark/machine_profile.cpp engine/benchmark/stress_safety.cpp engine/benchmark/workload_ramp.cpp engine/physics/showcase_runtime.cpp engine/physics/showcase_visualization.cpp engine/items/tupd_runtime.cpp engine/ui/tupd_ghost_preview.cpp app/game_main.cpp app/tupd_main.cpp app/main.cpp app/native_stress_main.cpp app/showcase_main.cpp app/illuminosity_bake_main.cpp engine/assets/hot_reload_status.cpp engine/audio/audio_interference_runtime.cpp engine/materials/material_runtime.cpp engine/scfont/scfont.cpp engine/scfont/font_service.cpp engine/scfont/text_point_adapter.cpp engine/render/point_renderer.cpp engine/render/room_visibility.cpp engine/render/sound_ripple.cpp engine/ui/ar_interface.cpp engine/ui/scui_native_runtime.cpp engine/world/liminal_level.cpp
"$PYTHON" tools/check_embedded_glsl.py engine/render/point_renderer.cpp
"$PYTHON" -m py_compile tools/native_stress_launcher.py tools/native_stress_hud.py tools/native_stress_watchdog.py tools/machine_profile_manager.py tools/stress_workload_registry.py tools/public_release_audit.py
"$PYTHON" tools/stress_content_catalog.py "$ROOT" --output-prefix reports/stress_content_catalog
"$PYTHON" tools/stress_workload_registry.py "$ROOT"
sc_prepare_cmake_build_dir "$ROOT" "$ROOT/build-core" Ninja
cmake -S . -B build-core -G Ninja -DCMAKE_BUILD_TYPE=Debug -DSC_BUILD_GUI=OFF
cmake --build build-core --parallel
ctest --test-dir build-core --output-on-failure
"$ROOT/build-core/signalcloud_illuminosity_bake" "$ROOT"
"$PYTHON" tools/machine_profile_manager.py "$ROOT" --json > reports/machine_profile_status.json
"$ROOT/scripts/validate_showcase_starters.sh"
find "$ROOT" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete
"$PYTHON" -m unittest discover -v -s tests -p 'test_*.py'
PUBLIC_AUDIT_TMP="$(mktemp -d "${TMPDIR:-/tmp}/signalcloud-a10a1-public-stage.XXXXXX")"
"$PYTHON" tools/public_release_audit.py "$ROOT" --output "$PUBLIC_AUDIT_TMP/stage"
rm -rf -- "$PUBLIC_AUDIT_TMP"
"$ROOT/tests/test_scui_tk_smoke.sh" "$ROOT"
"$ROOT/tests/test_stress_launch_bridge.sh"
"$ROOT/build-core/signalcloud_diagnostics" "$ROOT"

if [[ -x "$ROOT/build/almond_signal_live_tape" ]]; then
  echo "Native GUI executable present: $ROOT/build/almond_signal_live_tape"
else
  echo "Native GUI is not built yet; run ./scripts/setup_dev_environment.sh"
fi
if [[ -x "$ROOT/build/almond_signal_tupd_preview" ]]; then
  echo "Native Tupd executable present: $ROOT/build/almond_signal_tupd_preview"
fi

echo "Python runtime: $PYTHON"
echo "All SignalCloud game, stress, seven-tool Studio including integrated +SCFS+, two-state glyph clipboard, persistent C1/C2 color slots, ordered rich-text layers, enlarged flat-text profiles, near-full-window SCUI with split footer and no forced ellipses, point-backed Rich F/vending AR, distance-eased Reception WELCOME billboard, universal bounded Playbook foundation, native SCFONT text, AR/HUD, solid layer-safe backplates, Asset Doctor, Pack Builder/Installer, multi-light Illuminosity runtime, render-class-isolated jitter/material runtime, stable UI/viewmodel overlays, managed material and audio-wave authoring, protected SCUI/light/material/audio/font/PCP3 reload, Light Lab, Point Cloud Paint++, the accepted A7a2r2 3D Environment & Physics Showcase, the accepted A8a1 data-only Tupd recipe kernel, the accepted A8a2 explicit result lifecycle, the accepted A8a3 deterministic graph validator and authoring closure, plus the accepted A8a3r1 responsive Tupd repair and the A9a1 shared machine-profile schema, privacy-safe fingerprint, conservative first-run fallback, candidate validation, atomic promotion with previous-known-good preservation, staleness checks, workload registry, and game/tool profile consumption, plus the accepted A9a1r1 shared stress SCFONT, recovered-route candidate gate, explicit validation evidence, target-specific Official + Promote workflow, and active-profile startup target bootstrap, plus the accepted A9a1r2 plain result-path pointer, legacy pointer recovery, safe detached folder actions, and explicit promotion-receipt status, plus the A9a2 parent watchdog heartbeat, clean-stop and hard-abort controls, per-stage journal, automatic partial-report recovery, orphaned-session recovery, profile-preservation boundary, and exploratory-limit status, plus the accepted A9a2r1 external Python-cache hygiene, release-active profile checks, complete CSV stage journals, authoritative hard-abort provenance, and stable performance-content machine-profile signatures, plus the accepted A9a2r2 LF/CRLF canonical-manifest parity and matching game/status profile validation, plus the accepted A9a3 workload and memory foundation, and the A9a3r1 user-owned thermal safe/fail/force-stop thresholds, processor/GPU sensor policy and Sensor Doctor, sustained force-stop hold, 88% RAM envelope, 91% CPU and 97% GPU frame-budget advisories, and frozen final HUD wall timer, plus the accepted A9a3r2 phase-aware generation watchdog and persistent truthful final HUD state, plus the A10a1 repository-safe public staging policy, generated/private exclusion boundary, readable local-path normalization, credential blocking, deterministic source manifest/archive builder, and explicit owner-controlled license gate passed."
