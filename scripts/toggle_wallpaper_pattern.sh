#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
cd "$ROOT"
"$PYTHON" - <<'PY'
from pathlib import Path
import json
from tools.signalcloud_materials.managed import ensure_managed_material_set
from tools.asset_doctor.asset_doctor import run
root=Path.cwd()
managed=ensure_managed_material_set(root)
# Establish a protected baseline before changing the managed document.
if run(root) != 0:
    raise SystemExit("Asset Doctor rejected the managed material baseline")
path=managed.files["wall"]
payload=json.loads(path.read_text(encoding="utf-8"))
pattern=payload.setdefault("pattern", {})
current=float(pattern.get("primary_spacing", 6.8))
pattern["primary_spacing"] = 8.0 if current < 7.4 else 6.8
path.write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n", encoding="utf-8")
from tools.asset_doctor.content_abi import write_asset_envelope
write_asset_envelope(root/"content", path, asset_id=payload["asset_id"], asset_type="jitter_map", family="materials", pack="user", license_id="LicenseRef-SignalCloud-User-Authored", hot_reload="authoring-only")
print(f"Wallpaper primary spacing changed to {pattern['primary_spacing']:.1f}m")
PY
"$ROOT/scripts/stage_hot_reload_preview.sh"
