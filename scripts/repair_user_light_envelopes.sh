#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"

# The project directory contains a literal ':' in "Almond Signal: Live Tape".
# PYTHONPATH uses ':' as its Unix entry separator, so exporting the project path
# there splits it into invalid pieces. Run from the project root instead; the
# current directory is then Python's first import location without path parsing.
(
  cd "$ROOT"
  "$PYTHON" -m tools.signalcloud_lighting.license_repair "$ROOT"
)
