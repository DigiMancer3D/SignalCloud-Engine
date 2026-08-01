#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common_paths.sh"
cd "$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
"$PYTHON" - <<'PY'
from pathlib import Path
from tools.signalcloud_audio.managed import ensure_managed_audio_profile
from tools.signalcloud_audio.compiler import compile_audio_interference_runtime
root = Path.cwd()
result = ensure_managed_audio_profile(root)
compiled = compile_audio_interference_runtime(root)
print(("Created" if result.created else "Reusing") + f" managed audio profile: {result.path}")
print(f"Runtime signature: {compiled.signature}")
PY
