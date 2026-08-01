from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_materials.wallpaper_probe import build_report, wall_shell_mask
from tools.signalcloud_materials.wallpaper_migration import migrate_managed_wallpaper

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA5A2R2Tests(unittest.TestCase):
    def test_wallpaper_restores_legacy_grain_with_sparse_seams(self) -> None:
        material = json.loads((ROOT / "content/core/materials/office_wallpaper.jmap").read_text())
        pattern = material["pattern"]
        self.assertEqual(pattern["mode"], "wallpaper_breakup")
        self.assertGreaterEqual(pattern["primary_spacing"], 6.4)
        self.assertGreaterEqual(pattern["breakup_scale"], 6.0)
        self.assertLessEqual(pattern["line_width"], 0.07)
        self.assertLessEqual(pattern["displacement_weight"], 0.012)
        self.assertLessEqual(pattern["color_weight"], 0.34)
        self.assertEqual(material["extensions"]["wallpaper_variant"], "legacy-grain-sparse-seam")

    def test_wallpaper_branch_has_no_periodic_height_wave(self) -> None:
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text()
        start = renderer.index("Wallpaper restores the useful A5a1 legacy jitter")
        end = renderer.index("} else if (patternMode == 3)", start)
        block = renderer[start:end]
        self.assertIn("legacyWallGrain", block)
        self.assertIn("brokenSeam", block)
        self.assertNotIn("verticalFade", block)
        self.assertNotIn("secondaryWave", block)

    def test_screen_space_weave_is_carpet_only(self) -> None:
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text()
        self.assertIn("flat out int vMaterialMode", renderer)
        self.assertIn("if (vMaterialMode == 1)", renderer)
        fragment = renderer[renderer.index("if (vMaterialPattern > 0.0)"):renderer.index("if (vSound > 0.0)")]
        self.assertIn("fiberWeave", fragment)
        self.assertNotIn("vMaterialMode == 2", fragment)
        self.assertNotIn("vMaterialMode == 3", fragment)

    def test_wallpaper_is_limited_to_structural_shell_colors(self) -> None:
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text()
        for token in ("floorShellMask", "wallShellMask", "ceilingShellMask", "wallBalanceMask"):
            self.assertIn(token, renderer)
        self.assertGreater(wall_shell_mask((0.72, 0.64, 0.36)), 0.55)
        self.assertLess(wall_shell_mask((0.31, 0.25, 0.12)), 0.02)
        self.assertLess(wall_shell_mask((0.18, 0.86, 0.96)), 0.02)

    def test_cpu_probe_reports_low_contrast_nonperiodic_wallpaper(self) -> None:
        report = build_report(ROOT / "content/core/materials/office_wallpaper.jmap")
        self.assertLess(report["pattern_range"], 0.24)
        self.assertLessEqual(report["sparse_seam_runs_12m"], 4)
        self.assertFalse(report["periodic_height_wave"])
        self.assertFalse(report["screen_space_wall_weave"])
        self.assertGreater(report["structural_wall_mask"], 0.55)
        self.assertLess(report["reception_desk_mask"], 0.02)

    def test_toggle_and_editor_use_sparse_wallpaper_defaults(self) -> None:
        toggle = (ROOT / "scripts/toggle_wallpaper_pattern.sh").read_text()
        lab = (ROOT / "tools/jitter_texture_lab.py").read_text()
        self.assertIn("8.0 if current < 7.4 else 6.8", toggle)
        self.assertIn("primary = tk.DoubleVar(value=6.8)", lab)
        self.assertIn("no vertical periodic wave", lab)
        self.assertTrue((ROOT / "scripts/report_wallpaper_pattern.sh").is_file())

    def test_untouched_managed_a5a2_wallpaper_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            core = root / "content/core/materials"
            user = root / "content/user/materials/reception_tape"
            core.mkdir(parents=True)
            user.mkdir(parents=True)
            shutil.copy2(ROOT / "content/core/materials/office_wallpaper.jmap", core / "office_wallpaper.jmap")
            payload = json.loads((ROOT / "content/core/materials/office_wallpaper.jmap").read_text())
            payload["asset_id"] = "user.material.reception_tape.office_wallpaper"
            payload["pattern"] = {
                "mode": "wallpaper_breakup", "primary_spacing": 3.4,
                "secondary_spacing": 2.2, "breakup_scale": 4.6,
                "breakup_strength": 0.44, "displacement_weight": 0.035,
                "color_weight": 0.48, "line_width": 0.12,
            }
            path = user / "office_wallpaper.jmap"
            path.write_text(json.dumps(payload))
            self.assertEqual(migrate_managed_wallpaper(root), "migrated")
            migrated = json.loads(path.read_text())
            self.assertEqual(migrated["pattern"]["primary_spacing"], 6.8)
            self.assertEqual(migrated["extensions"]["a5a2r2_migrated_from"], "untouched-a5a2-default")

    def test_custom_managed_wallpaper_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            core = root / "content/core/materials"
            user = root / "content/user/materials/reception_tape"
            core.mkdir(parents=True)
            user.mkdir(parents=True)
            shutil.copy2(ROOT / "content/core/materials/office_wallpaper.jmap", core / "office_wallpaper.jmap")
            payload = json.loads((ROOT / "content/core/materials/office_wallpaper.jmap").read_text())
            payload["asset_id"] = "user.material.reception_tape.office_wallpaper"
            payload["pattern"]["primary_spacing"] = 9.25
            path = user / "office_wallpaper.jmap"
            path.write_text(json.dumps(payload))
            self.assertEqual(migrate_managed_wallpaper(root), "preserved-custom")
            self.assertEqual(json.loads(path.read_text())["pattern"]["primary_spacing"], 9.25)


if __name__ == "__main__":
    unittest.main()
