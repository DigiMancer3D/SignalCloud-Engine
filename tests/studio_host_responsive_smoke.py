from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.signalcloud_studio.app import build_catalog
from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.host import SignalCloudStudioHost


with tempfile.TemporaryDirectory() as temp:
    isolated = Path(temp) / "signalcloud"
    shutil.copytree(ROOT / "content", isolated / "content")
    (isolated / "user_data").mkdir(parents=True, exist_ok=True)

    host = SignalCloudStudioHost(
        ToolContext(isolated),
        build_catalog(),
        process_factory=lambda *_args, **_kwargs: None,
    )
    host.minsize(420, 420)
    host.geometry("520x540")
    host.update_idletasks()
    try:
        host.main_pane.sashpos(0, 145)
    except Exception:
        pass
    host.update_idletasks()
    host.update()

    assert host.viewport.active_axis == "x"
    assert host.viewport.axis_x.get() and not host.viewport.axis_y.get()
    host.viewport.select_axis("y")
    assert host.viewport.active_axis == "y"
    assert host.viewport.axis_y.get() and not host.viewport.axis_x.get()
    host.viewport.select_axis("x")

    # Narrow width must produce multiple rows in at least one responsive
    # action surface. The exact tab row count may vary by desktop font metrics.
    host.select_action_group("scui")
    host.update_idletasks()
    host.update()
    tab_rows = [int(item.grid_info().get("row", 0)) for item in host.tab_bar.items]
    action_rows = [int(item.grid_info().get("row", 0)) for item in host.action_bar.items]
    assert max(tab_rows + action_rows) >= 1, (tab_rows, action_rows)

    host.select_action_group("content")
    host.open_pack_builder()
    host.update_idletasks()
    host.update()
    assert host.active_embedded is not None
    assert host.footer.winfo_ismapped()
    assert host.footer.winfo_y() + host.footer.winfo_height() <= host.winfo_height()

    host.open_asset_doctor()
    host.update_idletasks()
    host.update()
    assert host.active_embedded is not None
    assert host.footer.winfo_ismapped()
    assert host.viewport.scrollbar.winfo_ismapped()

    host.open_pack_manager()
    host.update_idletasks()
    host.update()
    assert host.active_embedded is not None
    assert host.footer.winfo_ismapped()
    assert host.viewport.scrollbar.winfo_ismapped()

    host.select_action_group("scui")
    host.open_scui_proof()
    host.update_idletasks()
    host.update()
    assert host.active_embedded is not None
    assert host.footer.winfo_ismapped()

    host.destroy()

print("SignalCloud responsive Studio host smoke PASS")
