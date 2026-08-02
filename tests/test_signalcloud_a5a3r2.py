from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.signalcloud_fonts.validator import validate_scfont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "content/core/fonts/terminal_00/Terminal_00.scfont"


class SignalCloudA5A3R2Tests(unittest.TestCase):
    def test_terminal_font_is_valid_and_registered_as_font_asset(self) -> None:
        stats = validate_scfont(FONT)
        self.assertEqual(stats.name, "SC_term_00")
        self.assertEqual(stats.glyphs, 123)
        self.assertGreater(stats.points, 2_500)
        report = scan_content(ROOT / "content")
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)
        record = next(asset for asset in report.records if asset.relative_path.endswith("Terminal_00.scfont"))
        self.assertEqual(record.asset_type, "signalcloud_font")
        self.assertEqual(record.family, "font")

    def test_malformed_scfont_fails_without_affecting_core_font(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            malformed = Path(td) / "bad.scfont"
            malformed.write_text("SCFONT 1\nFONT bad\nMETRICS 9 8 5 7 0 2 1 4 11\nGLYPH 65 5\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_scfont(malformed)
        self.assertEqual(validate_scfont(FONT).glyphs, 123)

    def test_scui_uses_external_font_without_vertical_compression_or_overlap(self) -> None:
        source = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("const float font_scale = signalcloud::font::simple_text_scale", source)
        self.assertIn("SimpleTextRole::scui_menu", source)
        self.assertIn("style.point_radius = std::clamp(font_scale * 0.20F", source)
        self.assertIn("style.density = 1.05F", source)
        self.assertNotIn("basis.up * 0.70F", source)
        self.assertNotIn("font_scale * 0.58F", source)

    def test_ar_interface_uses_terminal_font_and_retains_legacy_fallback(self) -> None:
        header = (ROOT / "engine/ui/ar_interface.hpp").read_text(encoding="utf-8")
        source = (ROOT / "engine/ui/ar_interface.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("void set_font", header)
        self.assertIn("add_legacy_number", source)
        self.assertIn("append_simple_text_points", source)
        self.assertIn("ar_interface.set_font(font_service.default_font())", game)

    def test_scui_backplate_is_two_layer_solid_occluder(self) -> None:
        scui = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text(encoding="utf-8")
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        self.assertGreaterEqual(scui.count("5.00F"), 2)
        self.assertIn("flat out int vSolidBackplate", renderer)
        self.assertIn("uRenderClass == 2 && inDensity >= 4.5", renderer)
        self.assertIn("if (!solidBackplate && radius > 1.0) discard", renderer)
        self.assertIn("solidBackplate ? 1.0", renderer)

    def test_oblique_preview_uses_capsule_activation_and_spread_sampling(self) -> None:
        visibility = (ROOT / "engine/render/room_visibility.cpp").read_text(encoding="utf-8")
        level = (ROOT / "engine/world/liminal_level.cpp").read_text(encoding="utf-8")
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        self.assertIn("append_preview_spread", visibility)
        self.assertIn("preview_aperture_visible", visibility)
        self.assertIn("std::abs(signed_distance)", level)
        self.assertIn("lateral_excess", level)
        self.assertIn("crossedThreshold", renderer)
        self.assertIn("uPreviewHalfWidth + 0.90", renderer)

    def test_welcome_sign_has_constant_apparent_size_and_no_legacy_cloud(self) -> None:
        adapter = (ROOT / "engine/scfont/text_point_adapter.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("std::clamp(stats.camera_distance, 0.08F, 80.0F)", adapter)
        self.assertIn("stats.scale * 0.19F", adapter)
        self.assertIn('"WELCOME"', game)
        self.assertIn("append_constant_apparent_billboard", game)
        self.assertIn("suppress_legacy_welcome_cloud", game)
        self.assertIn("suppress the old fixed-scale blob cloud", game)

    def test_font_hot_reload_is_transactional_and_reported(self) -> None:
        bridge = (ROOT / "tools/asset_doctor/hot_reload_bridge.py").read_text(encoding="utf-8")
        status_hpp = (ROOT / "engine/assets/hot_reload_status.hpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn('"signalcloud_font"', bridge)
        self.assertIn("changed_font_count", status_hpp)
        self.assertIn("font_service.reload", game)
        self.assertIn("font_generation", game)

    def test_phase_marker_documentation_and_build_gates_exist(self) -> None:
        doc = (ROOT / "docs/alpha/A5A3R2_SCFONT_OBLIQUE_PREVIEW_BACKPLATE_CORRECTION.md").read_text(encoding="utf-8")
        for phrase in ("Terminal_00.scfont", "oblique", "prefix", "backplate", "legacy fallback"):
            self.assertIn(phrase, doc)
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("engine/scfont/scfont.cpp", cmake)
        self.assertIn("signalcloud_scfont_tests", cmake)
        for script_name in ("run_selftests.sh", "setup_dev_environment.sh"):
            script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
            self.assertIn("tools.signalcloud_fonts.validator", script)
            self.assertIn("engine/scfont/scfont.cpp", script)
        self.assertTrue((ROOT / "scripts/probe_changed_font_reload.sh").is_file())
        self.assertIn("changed_font_count", (ROOT / "tools/signalcloud_fonts/reload_probe.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
