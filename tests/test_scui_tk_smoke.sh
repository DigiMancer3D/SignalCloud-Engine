#!/usr/bin/env bash
set -euo pipefail
export TERM="${TERM:-xterm}"
ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PYTHON="${SC_PYTHON:-$(command -v python3)}"
cd "$ROOT"
can_use_display=0
if [[ -n "${DISPLAY:-}" ]]; then
  if "$PYTHON" - <<'PY' >/dev/null 2>&1
import tkinter as tk
root = tk.Tk()
root.destroy()
PY
  then
    can_use_display=1
  fi
fi
if [[ $can_use_display -eq 1 ]]; then
  "$PYTHON" tests/scui_tk_smoke.py
  "$PYTHON" tests/studio_host_responsive_smoke.py
  "$PYTHON" tests/jitter_material_tk_smoke.py
  "$PYTHON" tests/showcase_tk_smoke.py
  "$PYTHON" tests/tupd_tk_smoke.py
elif command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a "$PYTHON" tests/scui_tk_smoke.py
  xvfb-run -a "$PYTHON" tests/studio_host_responsive_smoke.py
  xvfb-run -a "$PYTHON" tests/jitter_material_tk_smoke.py
  xvfb-run -a "$PYTHON" tests/showcase_tk_smoke.py
  xvfb-run -a "$PYTHON" tests/tupd_tk_smoke.py
else
  echo "SKIP: SCUI Tk smoke requires a usable DISPLAY or xvfb-run"
fi
