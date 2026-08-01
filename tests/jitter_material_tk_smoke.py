from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.jitter_texture_lab import JitterLab

app = JitterLab(root_path=ROOT)
app.withdraw()
app.update_idletasks()
app.update()

assert app.project_root == ROOT.resolve()
assert app.canvas.winfo_exists()
assert len(app.dots) > 0
assert 0.0 <= app.opacity.get() <= 1.0
assert app.layer.get() in {
    "Normal", "HD Light", "HD Texture", "Outer Light", "Outer Texture", "Inner Texture"
}

app.destroy()
print("SignalCloud Jitter & Material Lab Tk smoke PASS")
