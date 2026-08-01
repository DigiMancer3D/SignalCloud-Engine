from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.asset_doctor import run as run_asset_doctor
from tools.asset_doctor.hot_reload_bridge import stage_preview_reload
from tools.signalcloud_materials.compiler import compile_material_runtime
from tools.signalcloud_materials.managed import ensure_managed_material_set, save_surface_pattern

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA5A2Tests(unittest.TestCase):
    def test_wallpaper_is_broad_flat_broken_and_deterministic(self) -> None:
        wall = json.loads((ROOT / "content/core/materials/office_wallpaper.jmap").read_text())
        pattern = wall["pattern"]
        self.assertEqual(pattern["mode"], "wallpaper_breakup")
        self.assertGreaterEqual(pattern["primary_spacing"], 3.0)
        self.assertGreaterEqual(pattern["secondary_spacing"], 1.8)
        self.assertGreaterEqual(pattern["breakup_strength"], 0.35)
        self.assertLessEqual(pattern["displacement_weight"], 0.05)
        self.assertLessEqual(wall["jitter"]["runtime_amplitude"], 0.01)

    def test_compiler_emits_surface_pattern_contract_deterministically(self) -> None:
        first = compile_material_runtime(ROOT)
        text1 = first.output.read_text()
        second = compile_material_runtime(ROOT)
        text2 = second.output.read_text()
        self.assertEqual(first.signature, second.signature)
        self.assertEqual(text1, text2)
        for token in ("pattern_mode", "primary_spacing", "breakup_strength", "displacement_weight", "color_weight"):
            self.assertIn(token, text1)

    def test_managed_user_material_set_has_unique_ids_and_is_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copytree(ROOT / "content/core/materials", root / "content/core/materials")
            managed = ensure_managed_material_set(root)
            self.assertTrue(managed.created)
            ids = []
            for path in managed.files.values():
                ids.append(json.loads(path.read_text())["asset_id"])
            ids.append(json.loads(managed.graph.read_text())["asset_id"])
            self.assertEqual(len(ids), len(set(ids)))
            save_surface_pattern(root, "wall", {
                "mode": "wallpaper_breakup", "primary_spacing": 4.8,
                "secondary_spacing": 2.4, "breakup_scale": 5.2,
                "breakup_strength": 0.5, "displacement_weight": 0.02,
                "color_weight": 0.46, "line_width": 0.1,
            })
            result = compile_material_runtime(root)
            self.assertIn("content/user/materials/reception_tape_surfaces.texgraph", result.output.read_text())
            self.assertIn("primary_spacing: 4.800000", result.output.read_text())

    def test_protected_stage_compiles_changed_material_runtime(self) -> None:
        wallpaper = ROOT / "content/core/materials/office_wallpaper.jmap"
        original = wallpaper.read_text()
        try:
            self.assertEqual(run_asset_doctor(ROOT), 0)
            payload = json.loads(original)
            payload["pattern"]["primary_spacing"] = 4.2
            wallpaper.write_text(json.dumps(payload, indent=2) + "\n")
            result = stage_preview_reload(ROOT)
            self.assertGreaterEqual(result.changed_material_count, 1)
            status = (ROOT / "user_data/studio/hot_reload_latest.udata").read_text()
            self.assertIn("changed_material_count", status)
            self.assertIn("hot_reload/materials", status)
        finally:
            wallpaper.write_text(original)
            run_asset_doctor(ROOT)
            compile_material_runtime(ROOT)
            stage_preview_reload(ROOT)

    def test_renderer_uses_surface_local_projection_and_mode_specific_breakup(self) -> None:
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text()
        self.assertIn("Stable world-anchored surface coordinates", renderer)
        self.assertIn("wallpaper_breakup", (ROOT / "engine/materials/material_runtime.cpp").read_text())
        self.assertIn("wallFacesX", renderer)
        self.assertIn("uMaterialPrimarySpacing", renderer)
        self.assertIn("displacementWeight", renderer)
        material_block = renderer[renderer.index("Stable world-anchored surface coordinates"):renderer.index("float deformationPass")]
        self.assertNotIn("uTime", material_block)

    def test_native_f9_declares_material_reload_and_receipt(self) -> None:
        game = (ROOT / "app/game_main.cpp").read_text()
        status_h = (ROOT / "engine/assets/hot_reload_status.hpp").read_text()
        self.assertIn("changed_material_set", game)
        self.assertIn("material_applied", game)
        self.assertIn("material_runtime_signature", game)
        self.assertIn("changed_material_count", status_h)

    def test_studio_exposes_managed_surface_editor_and_probe_scripts(self) -> None:
        lab = (ROOT / "tools/jitter_texture_lab.py").read_text()
        self.assertIn("Edit Reception surfaces", lab)
        self.assertIn("Save managed copy", lab)
        self.assertIn("Stage protected preview", lab)
        self.assertTrue((ROOT / "scripts/create_managed_material_set.sh").is_file())
        self.assertTrue((ROOT / "scripts/toggle_wallpaper_pattern.sh").is_file())

    def test_installed_tree_has_no_package_only_skip_or_python_cache(self) -> None:
        self.assertFalse((ROOT / "tests/test_signalcloud_a5a1r1_installer.py").exists())
        caches = list(ROOT.rglob("__pycache__"))
        self.assertEqual(caches, [])

    def test_embedded_glsl_preflight_is_part_of_build_gates(self) -> None:
        self.assertTrue((ROOT / "tools/check_embedded_glsl.py").is_file())
        for script in ("scripts/run_selftests.sh", "scripts/setup_dev_environment.sh"):
            self.assertIn("check_embedded_glsl.py", (ROOT / script).read_text())


if __name__ == "__main__":
    unittest.main()
