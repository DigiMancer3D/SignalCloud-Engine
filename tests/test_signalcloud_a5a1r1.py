from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.signalcloud_lighting.license_repair import repair_user_light_envelopes

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA5A1R1Tests(unittest.TestCase):
    def test_renderer_isolates_environment_materials_from_dynamic_and_overlay_passes(self) -> None:
        cpp = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        header = (ROOT / "engine/render/point_renderer.hpp").read_text(encoding="utf-8")
        self.assertIn("uniform int uRenderClass", cpp)
        self.assertIn("bool environmentPass = uRenderClass == 0", cpp)
        self.assertIn("bool stableOverlay = uRenderClass == 2", cpp)
        self.assertIn("materialEnabled = float(uMaterialEnabled[materialIndex]) * (environmentPass", cpp)
        self.assertIn("tactical_mode ? 2 : 1", cpp)
        self.assertGreaterEqual(cpp.count("uniform1i(render_class_location_, 2)"), 2)
        self.assertIn("render_class_location_", header)

    def test_stable_overlay_bypasses_world_deformation_and_animated_noise(self) -> None:
        cpp = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        self.assertIn("float deformationPass = stableOverlay ? 0.0 : 1.0", cpp)
        self.assertIn("vStableOverlay", cpp)
        self.assertIn("mix(0.86 + 0.23 * hash12", cpp)
        self.assertIn("1.0, stable", cpp)
        self.assertIn("float normalLight = stableOverlay ? 1.0", cpp)
        self.assertIn("float authoredAlpha = stableOverlay ? inColor.a", cpp)

    def test_ceiling_is_flat_cool_and_has_bounded_fixture_drop(self) -> None:
        ceiling = json.loads((ROOT / "content/core/materials/ceiling_tile.jmap").read_text(encoding="utf-8"))
        carpet = json.loads((ROOT / "content/core/materials/office_carpet.jmap").read_text(encoding="utf-8"))
        self.assertEqual(ceiling["character"], "smooth")
        self.assertLessEqual(ceiling["jitter"]["runtime_amplitude"], 0.002)
        self.assertGreater(ceiling["palette"]["source"][2], carpet["palette"]["source"][2])
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        self.assertIn("ceilingFixture * 0.070", renderer)
        self.assertIn("fixtureRim", renderer)
        self.assertIn("hanging-fixture silhouette", renderer)

    def test_hud_edge_layout_moves_vitals_and_towers_outward(self) -> None:
        ar = (ROOT / "engine/ui/ar_interface.cpp").read_text(encoding="utf-8")
        for token in (
            "-0.64F, -0.345F, 0.24F",
            "0.40F, -0.345F, 0.24F",
            "-0.642F, 0.188F",
            "0.624F, 0.188F",
        ):
            self.assertIn(token, ar)

    def test_native_scui_uses_taller_glyphs_and_wider_character_advance(self) -> None:
        runtime = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text(encoding="utf-8")
        # A5a3r2 keeps the accepted 5x9 path as emergency fallback while the
        # native SCFONT path supplies the normal taller, Advance-aware text.
        self.assertIn("std::array<std::uint8_t, 9> glyph", runtime)
        self.assertIn("scale * 6.8F", runtime)
        self.assertIn("taller 5x9 point alphabet", runtime)
        self.assertIn("SimpleTextRole::scui_menu", runtime)
        self.assertIn("simple_text_scale", runtime)
        self.assertIn("font_scale * 0.20F", runtime)

    def test_user_sclight_repair_removes_license_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset = root / "content/user/lights/demo.sclight"
            asset.parent.mkdir(parents=True)
            asset.write_text('{"schema":"signalcloud_light_set_v3","lights":[]}\n', encoding="utf-8")
            repaired = repair_user_light_envelopes(root)
            self.assertEqual(len(repaired), 1)
            envelope = repaired[0].read_text(encoding="utf-8")
            self.assertIn("LicenseRef-SignalCloud-User-Authored", envelope)
            report = scan_content(root / "content")
            self.assertEqual(report.error_count, 0)
            self.assertEqual(report.warning_count, 0)


if __name__ == "__main__":
    unittest.main()
