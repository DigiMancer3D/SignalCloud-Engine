from __future__ import annotations

import tkinter as tk
import json
from pathlib import Path
import sys
import shutil
import tempfile

root_path = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_path))

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.scui import ScuiTkRenderer, load_scui
from tools.signalcloud_studio.scui.light_lab import mount_light_lab_panel
from tools.signalcloud_studio.scui.proof import build_proof_registry
from tools.signalcloud_studio.scui.panel_browser import mount_registry_browser
from tools.signalcloud_studio.asset_doctor_panel import mount_asset_doctor_panel
from tools.signalcloud_studio.pack_builder_panel import mount_pack_builder_panel


root = tk.Tk()
root.withdraw()
panel = load_scui(root_path / "content/core/ui/authoring_lab_project_selector.scui")
renderer = ScuiTkRenderer(root, panel, registry=build_proof_registry())
renderer.frame.pack(fill="both", expand=True)
root.update_idletasks()
assert set(renderer.widgets) == {"intro", "project", "safe_preview", "point_budget", "profile_progress", "refresh"}
renderer.set_value("point_budget", 4_000_000)
assert renderer.get_value("point_budget") == 4_000_000
renderer.frame.destroy()

with tempfile.TemporaryDirectory() as temp:
    isolated_root = Path(temp) / "signalcloud"
    shutil.copytree(root_path / "content" / "core" / "ui", isolated_root / "content" / "core" / "ui")
    shutil.copytree(root_path / "content" / "core" / "lights", isolated_root / "content" / "core" / "lights")
    isolated_context = ToolContext(isolated_root)

    host = tk.Frame(root)
    host.pack(fill="both", expand=True)
    session = mount_light_lab_panel(host, isolated_context, lambda _text: None)
    root.update_idletasks()
    assert session.renderer is not None
    assert set(session.renderer.widgets) == {
        "intro", "scope", "illuminosity", "radius", "day_i", "night_i", "time_of_day",
        "timeline_play", "timeline_pause", "timeline_stop", "probe", "bake", "reload", "save"
    }
    default_light = json.loads(
        (isolated_root / "content/core/lights/authoring_lab_default.slight").read_text(encoding="utf-8")
    )["lights"][0]["illuminosity_percent"]
    assert session.renderer.get_value("light_i") == float(default_light)
    session.renderer.set_value("light_i", 84.0)
    assert session.renderer.get_value("light_i") == 84.0
    host.destroy()

    registry_host = tk.Frame(root)
    registry_host.pack(fill="both", expand=True)
    browser = mount_registry_browser(registry_host, isolated_context, lambda _text: None)
    root.update_idletasks()
    assert browser.registry.valid
    assert set(browser.registry.keys()) == {"project-selector", "light-lab", "tupd-workbench"}
    browser.open_selected()
    root.update_idletasks()
    assert browser.panel_host.winfo_children()
    registry_host.destroy()

    doctor_host = tk.Frame(root)
    doctor_host.pack(fill="both", expand=True)
    doctor = mount_asset_doctor_panel(doctor_host, isolated_context, lambda _text: None)
    root.update_idletasks()
    assert doctor.report.error_count == 0
    assert doctor.report.valid_count >= 4
    doctor_host.destroy()

    pack_host = tk.Frame(root)
    pack_host.pack(fill="both", expand=True)
    pack_builder = mount_pack_builder_panel(pack_host, isolated_context, lambda _text: None)
    root.update_idletasks()
    assert pack_builder.source.get() == "content/user"
    assert pack_builder.pack_id.get() == "user.authoring-pack"
    pack_host.destroy()
    root.destroy()
print("SCUI Tk renderer, registry browser, Asset Doctor, Pack Builder, and managed Light Lab binding smoke PASS")
