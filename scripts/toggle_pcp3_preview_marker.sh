#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${SIGNALCLOUD_PYTHON:-python3}"
exec env PYTHONPATH="$ROOT" "$PYTHON" -m tools.asset_doctor.pcp3_reload_probe "$ROOT"
