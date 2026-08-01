from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from tools.signalcloud_showcase.app import ShowcaseApp

source = root / "content/starter/showcase/office_shipping_crate/office_shipping_crate.pcp3"
app = ShowcaseApp(root)
app.withdraw()
app.update_idletasks()
app.import_path(source)
assert app.current is not None
assert len(app.current.document.points) > 100
app.run_simulation("drop")
assert "Animating drop" in app.status.get()
assert app.active_test == "drop"
assert "office_shipping_crate" in app.asset_id.get()
app.destroy()
print("SignalCloud 3D Environment & Physics Showcase Tk smoke PASS")
