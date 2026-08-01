from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA7A2R2Tests(unittest.TestCase):
    def test_native_info_toggle_switches_world_and_ui_modes(self) -> None:
        source = (ROOT / "app/showcase_main.cpp").read_text(encoding="utf-8")
        for token in (
            "bool status_overlay = false",
            "SDL_SCANCODE_I",
            'status_overlay ? "INFO UI OVERLAY" : "INFO WORLD PLATE"',
            "if (!status_overlay)",
            "append_showcase_info_overlay",
            "upload_viewmodel_points",
        ):
            self.assertIn(token, source)

    def test_ui_overlay_is_top_left_fitted_and_point_backed(self) -> None:
        source = (ROOT / "engine/ui/showcase_info_overlay.cpp").read_text(encoding="utf-8")
        for token in (
            "plane_center - right * (half_width - margin_x)",
            "up * (half_height - margin_y)",
            "add_plate(0.0030F",
            "add_plate(0.0015F",
            "append_simple_text_points",
            "available_width / layout.width",
            "available_height / layout.height",
        ):
            self.assertIn(token, source)

    def test_help_and_title_report_info_mode(self) -> None:
        source = (ROOT / "app/showcase_main.cpp").read_text(encoding="utf-8")
        self.assertIn("S SNAPSHOT  I INFO", source)
        self.assertIn('" · info " << (status_overlay ? "UI" : "WORLD")', source)
        self.assertIn("SignalCloud Showcase A7a2r2", source)

    def test_native_visualization_test_has_no_unused_variable_warning_shape(self) -> None:
        source = (ROOT / "tests/test_showcase_visualization.cpp").read_text(encoding="utf-8")
        self.assertIn("(void)point;", source)
        self.assertIn("(void)moved_object;", source)
        self.assertIn("A7a2r2 Showcase visualization", source)

    def test_desktop_showcase_and_exporter_identify_current_sibling(self) -> None:
        app = (ROOT / "tools/signalcloud_showcase/app.py").read_text(encoding="utf-8")
        exporter = (ROOT / "tools/signalcloud_showcase/exporter.py").read_text(encoding="utf-8")
        self.assertIn("A7a2r2", app)
        self.assertIn("SignalCloud Showcase A7a2r2", exporter)

    def test_phase_marker_and_closure_document_exist(self) -> None:
        self.assertTrue((ROOT / "ALPHA_A7A2R2_INSTALLED.txt").is_file())
        document = ROOT / "docs/alpha/A7A2R2_SHOWCASE_INFO_OVERLAY.md"
        self.assertTrue(document.is_file())
        text = document.read_text(encoding="utf-8").lower()
        for phrase in (
            "top-left", "in-world point plate", "pointrenderer viewmodel path",
            "two-sheet backplate", "a7 is complete",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
