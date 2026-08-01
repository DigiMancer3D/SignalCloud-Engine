#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -x "$ROOT/scripts/launch_native_stress.sh" ]]
[[ -x "$ROOT/scripts/launch_native_stress_gui.sh" ]]
[[ -x "$ROOT/scripts/recover_native_stress_runs.sh" ]]
[[ -x "$ROOT/tools/native_stress_watchdog.py" ]]
grep -q "native_stress_watchdog.py" "$ROOT/scripts/launch_native_stress.sh"
[[ -x "$ROOT/scripts/launch_pcp3.sh" ]]
[[ -f "$ROOT/tools/pcp3/editor_branch2r2.py" ]]
[[ ! -e "$ROOT/scripts/select_stresslab.sh" ]]
[[ ! -e "$ROOT/scripts/launch_stresslab.sh" ]]
echo "PASS: watchdog-protected native stress, recovery, and PCP3 launch bridge; obsolete compatibility StressLab remains removed"
