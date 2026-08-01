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
from tools.signalcloud_materials.managed import ensure_managed_material_set
result = ensure_managed_material_set(Path.cwd())
print(f"Managed material graph: {result.graph}")
for surface, path in result.files.items():
    print(f"  {surface}: {path}")
PY
"$ROOT/scripts/run_asset_doctor.sh"
