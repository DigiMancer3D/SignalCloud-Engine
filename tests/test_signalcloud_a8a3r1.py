from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA8A3R1Tests(unittest.TestCase):
    def test_workbench_action_bar_uses_responsive_flow_rows(self) -> None:
        app = (ROOT / "tools/signalcloud_tupd/app.py").read_text(encoding="utf-8")
        self.assertIn("from tools.signalcloud_studio.ui import FlowBar", app)
        self.assertIn("toolbar = FlowBar(header", app)
        self.assertIn("group = toolbar.group()", app)
        self.assertNotIn('ttk.Button(toolbar, text=text, command=command).pack(side="left"', app)
        for label in (
            "Open Recipe…", "Duplicate Recipe", "Validate Graph", "Commit Sandbox",
            "Equip/Spawn Result", "Native Stage", "Export & Reload", "Asset Doctor",
        ):
            self.assertIn(label, app)

    def test_graph_layout_fits_real_visible_canvas(self) -> None:
        app = (ROOT / "tools/signalcloud_tupd/app.py").read_text(encoding="utf-8")
        self.assertIn("width = max(280, self.graph.winfo_width())", app)
        self.assertIn("height = max(260, self.graph.winfo_height())", app)
        self.assertIn("node_half_width", app)
        self.assertIn("x_radius = max(0.0, min(225.0", app)
        self.assertIn("y_radius = max(0.0, min(150.0", app)
        self.assertNotIn("width = max(640, self.graph.winfo_width())", app)

    def test_native_result_is_world_space_and_info_remains_overlay(self) -> None:
        native = (ROOT / "app/tupd_main.cpp").read_text(encoding="utf-8")
        header = (ROOT / "engine/ui/tupd_ghost_preview.hpp").read_text(encoding="utf-8")
        source = (ROOT / "engine/ui/tupd_ghost_preview.cpp").read_text(encoding="utf-8")
        self.assertIn("TupdGhostPlacementMode::world_stage", native)
        self.assertIn("auto world_points = ghost.build_points", native)
        self.assertIn("upload_dynamic_points(world_points", native)
        self.assertIn("upload_viewmodel_points(ui_points", native)
        self.assertNotIn("upload_viewmodel_points(overlay_points", native)
        self.assertIn("enum class TupdGhostPlacementMode", header)
        self.assertIn("placement.world_center", source)
        self.assertIn("camera-overlay placement remains", source.lower())

    def test_revision_marker_and_handoff_exist(self) -> None:
        marker = ROOT / "ALPHA_A8A3R1_INSTALLED.txt"
        handoff = ROOT / "docs/alpha/A8A3R1_TUPD_VISUAL_USABILITY_REPAIR.md"
        rule = ROOT / "content/core/rules/a8a3r1_tupd_visual_usability_repair.udata"
        self.assertTrue(marker.is_file())
        self.assertTrue(handoff.is_file())
        self.assertTrue(rule.is_file())
        self.assertTrue(Path(str(rule) + ".asset.udata").is_file())
        text = (marker.read_text(encoding="utf-8") + handoff.read_text(encoding="utf-8") + rule.read_text(encoding="utf-8")).lower()
        for phrase in ("responsive", "world-space", "graph", "normal save", "a9"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
