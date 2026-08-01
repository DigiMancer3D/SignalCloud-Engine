from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA5A3R1Tests(unittest.TestCase):
    def test_preview_uses_canonical_threshold_geometry_and_hysteresis(self) -> None:
        source = (ROOT / "engine/world/liminal_level.cpp").read_text(encoding="utf-8")
        self.assertIn("threshold envelopes exist", source)
        self.assertIn("canonical.normal = canonical.normal * -1.0F", source)
        # A5a3r2 supersedes the one-sided source-distance hysteresis with a
        # capsule around the exact opening so oblique/crossed approaches persist.
        self.assertIn("const float normal_distance = std::abs(signed_distance)", source)
        self.assertIn("lateral_excess", source)

    def test_preview_has_bounded_inferred_visibility_floor(self) -> None:
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        self.assertIn("uPreviewStrength", renderer)
        self.assertIn("prevents a valid clipped preview from collapsing into a black void", renderer)
        self.assertIn("authoredAlpha = max(authoredAlpha", renderer)

    def test_audio_wave_count_creates_separate_rings(self) -> None:
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        self.assertIn("for (int waveIndex = 0; waveIndex < 8; ++waveIndex)", renderer)
        self.assertIn("ringRadius = uSoundRadius - float(waveIndex) * waveSpacing", renderer)
        self.assertNotIn("soundBandFrequency * max(1.0, float(uSoundWaveCount))", renderer)

    def test_scui_success_notice_uses_official_ring_check_style(self) -> None:
        source = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("growth-explosion entry", source)
        self.assertIn("add_circle(out, notice_basis", source)
        self.assertIn("notice_started_seconds_", source)
        notice = source[source.index("if (!notice_message_.empty()") : source.index("if (pointer_visible_)")]
        self.assertNotIn("add_filled_rect", notice)

    def test_reception_marker_is_persistent_welcome_sign(self) -> None:
        project = json.loads((ROOT / "content/pcp3_assets/environment_object/a3_preview_marker/a3_preview_marker.pcp3").read_text(encoding="utf-8"))
        self.assertEqual(project["display_name"], "Reception WELCOME Sign")
        self.assertTrue(project["runtime"]["auto_preview_in_game"])
        self.assertEqual(project["runtime"]["preview_zone"], "Reception Tape")
        self.assertGreaterEqual(project["point_count"], 250)
        self.assertIn("WELCOME", project["author"]["title"])

    def test_phase_marker_and_documentation_exist(self) -> None:
        self.assertTrue((ROOT / "ALPHA_A5A3R1_INSTALLED.txt").is_file())
        doc = (ROOT / "docs/alpha/A5A3R1_PREVIEW_AUDIO_NOTIFICATION_CORRECTION.md").read_text(encoding="utf-8")
        for phrase in ("threshold envelope", "multi-ring", "WELCOME", "Blackhole Portal"):
            self.assertIn(phrase, doc)


if __name__ == "__main__":
    unittest.main()
