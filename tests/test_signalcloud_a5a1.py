from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_materials.compiler import compile_material_runtime

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA5A1Tests(unittest.TestCase):
    def test_shipped_jmap_and_texgraph_compile_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "runtime.udata"
            first = compile_material_runtime(ROOT, output_relative=str(out.relative_to(ROOT)) if ROOT in out.parents else "user_data/studio/a5_temp.udata")
            text_a = first.output.read_text(encoding="utf-8")
            second = compile_material_runtime(ROOT, output_relative="user_data/studio/a5_temp.udata")
            text_b = second.output.read_text(encoding="utf-8")
            self.assertEqual(text_a, text_b)
            self.assertEqual(first.material_count, 3)
            self.assertEqual(first.assignment_count, 3)
            self.assertEqual(first.warning_count, 0)
            first.output.unlink(missing_ok=True)

    def test_user_lock_and_opacity_hierarchy_are_authored(self) -> None:
        graph = json.loads((ROOT / "content/core/materials/reception_tape_surfaces.texgraph").read_text())
        floor = next(rule for rule in graph["rules"] if rule["surface"] == "floor")
        self.assertTrue(floor["locked"])
        carpet = json.loads((ROOT / "content/core/materials/office_carpet.jmap").read_text())
        self.assertEqual(carpet["schema"], "signalcloud_jitter_map_v1")
        self.assertEqual(set(carpet["opacity"]), {
            "point", "cluster", "object", "surface", "local_area", "room", "global", "runtime_effect"
        })
        self.assertIn(carpet["character"], {"smooth", "bumpy", "rocky"})

    def test_renderer_consumes_material_and_audio_uniforms(self) -> None:
        cpp = (ROOT / "engine/render/point_renderer.cpp").read_text()
        for token in (
            "uMaterialJG", "uMaterialJL", "uMaterialJC", "uMaterialJS",
            "uMaterialOpacity", "uMaterialSourceColors", "uSoundBand",
            "uSoundSeed", "uSoundObstruction", "materialDisplacement", "soundJitter",
        ):
            self.assertIn(token, cpp)
        self.assertIn("set_material_frame", (ROOT / "engine/render/point_renderer.hpp").read_text())

    def test_hash_dog_bark_bridges_visual_ripple_and_ai_hearing(self) -> None:
        game = (ROOT / "app/game_main.cpp").read_text()
        self.assertIn("Hash Dog bark: bounded low-band signal ripple", game)
        self.assertIn("sound_ripple.trigger_event(entity.position", game)
        self.assertIn("combat.emit_noise(entity.position", game)
        self.assertIn("FrequencyBand::low", game)

    def test_stress_reports_material_and_sound_costs(self) -> None:
        stress = (ROOT / "app/native_stress_main.cpp").read_text()
        self.assertIn('material_point_budget', stress)
        self.assertIn('active_materials', stress)
        self.assertIn('sound_interference_serial', stress)
        self.assertIn("Material budget:", stress)

    def test_material_opacity_is_applied_once_and_studio_exposes_lab(self) -> None:
        renderer = (ROOT / "engine/render/point_renderer.cpp").read_text()
        self.assertIn("vColor = vec4(color, authoredAlpha);", renderer)
        self.assertNotIn("authoredAlpha * materialOpacity", renderer)
        self.assertIn("alpha *= clamp(vMaterialOpacity", renderer)

        catalog = {item.key: item.display_name for item in __import__(
            "tools.signalcloud_studio.app", fromlist=["build_catalog"]
        ).build_catalog().infos()}
        self.assertEqual(catalog["jitter-texture-lab"], "Jitter & Material Lab")
        host = (ROOT / "tools/signalcloud_studio/host.py").read_text()
        self.assertIn("Open Jitter & Material Lab", host)
        self.assertIn("jitter_material_tk_smoke.py", (ROOT / "tests/test_scui_tk_smoke.sh").read_text())

    def test_build_gates_compile_material_runtime(self) -> None:
        for relative in ("scripts/run_selftests.sh", "scripts/setup_dev_environment.sh"):
            text = (ROOT / relative).read_text()
            self.assertIn("compile_material_runtime.sh", text)
        cmake = (ROOT / "CMakeLists.txt").read_text()
        self.assertIn("engine/materials/material_runtime.cpp", cmake)
        self.assertIn("signalcloud_material_runtime_tests", cmake)


if __name__ == "__main__":
    unittest.main()
