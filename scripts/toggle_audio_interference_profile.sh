#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common_paths.sh"
cd "$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
"$PYTHON" - <<'PY'
from pathlib import Path
from tools.signalcloud_audio.managed import load_profile, save_profile
from tools.signalcloud_audio.compiler import compile_audio_interference_runtime
from tools.asset_doctor.asset_doctor import run
from tools.asset_doctor.hot_reload_bridge import stage_preview_reload
root = Path.cwd()
path, payload = load_profile(root)
# Establish the protected baseline after the managed profile exists but before
# changing it. Rebuilding the index after the edit would make the new hash look
# unchanged and defeat the F9 proof.
if run(root) != 0:
    raise SystemExit("Asset Doctor rejected the managed audio baseline")
current = int(payload.get("visual", {}).get("wave_count", 3))
next_value = 5 if current == 3 else 3
save_profile(root, {"wave_count": next_value})
compile_audio_interference_runtime(root)
result = stage_preview_reload(root)
print(f"Hash Dog ripple wave count changed to {next_value}")
print(f"Changed types: lights {result.changed_light_count} | SCUI {result.changed_scui_count} | PCP3 {result.changed_pcp3_count} | materials {result.changed_material_count} | audio {result.changed_audio_count}")
PY
