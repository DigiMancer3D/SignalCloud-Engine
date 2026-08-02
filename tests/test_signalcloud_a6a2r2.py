from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA6A2R2Tests(unittest.TestCase):
    def test_scui_footer_replaces_header_and_redundant_hint(self) -> None:
        source = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text()
        self.assertNotIn('"NATIVE POINT SCUI / F8 CLOSE"', source)
        self.assertNotIn('"ARROWS / ENTER / MOUSE"', source)
        self.assertIn('"NATIVE POINT SCUI"', source)
        self.assertIn('"ARROWS / ENTER"', source)
        self.assertIn("add_right_aligned_text", source)

    def test_width_wrapping_has_no_forced_ellipsis(self) -> None:
        source = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text()
        self.assertNotIn('last += "..."', source)
        self.assertNotIn("last.append(ellipsis, '.')", source)
        self.assertIn("Width-aware wrapping already guarantees", source)

    def test_enlarged_text_uses_non_overlapping_line_steps(self) -> None:
        source = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text()
        for value in ("0.070F", "0.0580F", "0.0560F", "0.0540F"):
            self.assertIn(value, source)

    def test_ar_menu_and_interaction_have_internal_backplates(self) -> None:
        source = (ROOT / "engine/ui/ar_interface.cpp").read_text()
        self.assertIn("The vending menu is an AR overlay", source)
        self.assertIn("The interaction key is now a real Rich-text glyph", source)
        self.assertIn("append_rich_text_points", source)
        self.assertGreaterEqual(source.count("add_filled_rect(points, overlay_"), 4)
        self.assertIn("add_check(points, basis, -0.300F", source)
        self.assertIn("add_cross(points, basis, 0.300F", source)

    def test_welcome_moves_vertically_without_xz_slide(self) -> None:
        header = (ROOT / "engine/scfont/text_point_adapter.hpp").read_text()
        source = (ROOT / "engine/scfont/text_point_adapter.cpp").read_text()
        game = (ROOT / "app/game_main.cpp").read_text()
        self.assertIn("DistanceEasedBillboardPlacement", header)
        self.assertIn("placement.anchor.y +=", source)
        self.assertNotIn("placement.anchor.x +=", source)
        self.assertNotIn("placement.anchor.z +=", source)
        self.assertIn("distance_eased_billboard_placement", game)

    def test_phase_marker_and_report_exist(self) -> None:
        self.assertTrue((ROOT / "ALPHA_A6A2R2_INSTALLED.txt").is_file())
        report = ROOT / "docs/alpha/A6A2R2_SCUI_AR_BILLBOARD_VISUAL_ALIGNMENT.md"
        self.assertTrue(report.is_file())
        self.assertGreater(len(report.read_text()), 2500)


if __name__ == "__main__":
    unittest.main()
