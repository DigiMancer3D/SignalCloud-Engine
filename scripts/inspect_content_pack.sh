#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${SIGNALCLOUD_PYTHON:-python3}"
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <pack.scpack.zip> [--json]" >&2
  exit 2
fi
cd "$ROOT"
exec env PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON" -m tools.asset_doctor.pack_manager "$ROOT" "$@"
