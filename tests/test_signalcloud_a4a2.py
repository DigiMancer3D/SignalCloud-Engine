from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_lighting.compiler import compile_light_document
from tools.signalcloud_lighting.reload_probe import run_probe

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA4A2Tests(unittest.TestCase):
    def test_shipped_scope_demonstration_contains_four_bounded_lights(self) -> None:
        payload = json.loads(
            (ROOT / "content/core/lights/authoring_lab_default.slight").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["schema"], "signalcloud_light_set_v2")
        self.assertEqual(
            {light["scope"] for light in payload["lights"]},
            {"local", "area", "room", "global"},
        )
        self.assertEqual(len(payload["lights"]), 4)
        self.assertEqual(payload["runtime_budget"]["max_active_lights"], 4)
        self.assertEqual(payload["runtime_budget"]["max_point_budget"], 2048)
        self.assertEqual(payload["runtime_budget"]["max_diagnostic_rays"], 32)
        self.assertLessEqual(
            sum(light["point_budget_cost"] for light in payload["lights"] if light["enabled"]),
            payload["runtime_budget"]["max_point_budget"],
        )

    def test_compiler_emits_budget_contract_and_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "content/core/lights/authoring_lab_default.slight"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema": "signalcloud_light_set_v2",
                        "runtime_budget": {
                            "max_active_lights": 2,
                            "max_point_budget": 500,
                            "rays_per_light": 4,
                            "max_diagnostic_rays": 8,
                            "stress_scale": 1.0,
                        },
                        "lights": [
                            {
                                "id": "high",
                                "enabled": True,
                                "point_budget_cost": 300,
                                "budget_priority": 900,
                            },
                            {
                                "id": "middle",
                                "enabled": True,
                                "point_budget_cost": 200,
                                "budget_priority": 500,
                            },
                            {
                                "id": "low",
                                "enabled": True,
                                "point_budget_cost": 100,
                                "budget_priority": 100,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = compile_light_document(root)
            self.assertEqual(result.light_count, 3)
            self.assertEqual(result.selected_light_count, 2)
            self.assertEqual(result.selected_point_budget_cost, 500)
            self.assertEqual(result.max_point_budget, 500)
            runtime = result.output_path.read_text(encoding="utf-8")
            self.assertIn("[runtime-budget]", runtime)
            self.assertIn("max_active_lights: 2;", runtime)
            self.assertIn("budget_priority: 900;", runtime)
            report = json.loads(result.report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["budget_limited_count"], 1)
            self.assertIn("deterministically budget-limited", " ".join(report["warnings"]))

    def test_changed_light_probe_is_deterministic_and_non_destructive(self) -> None:
        source = ROOT / "content/core/lights/authoring_lab_default.slight"
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        result = run_probe(ROOT)
        after = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["changed_light_count"], 1)
        self.assertEqual(result["invalid_count"], 0)
        self.assertFalse(result["live_content_modified"])
        self.assertEqual(before, after)
        self.assertNotEqual(
            result["before_illuminosity_percent"],
            result["changed_illuminosity_percent"],
        )

    def test_renderer_uses_four_bounded_authored_light_uniforms(self) -> None:
        header = (ROOT / "engine/lighting/illuminosity_runtime.hpp").read_text(encoding="utf-8")
        renderer_h = (ROOT / "engine/render/point_renderer.hpp").read_text(encoding="utf-8")
        renderer_cpp = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        self.assertIn("kMaxEvaluatedLocalLights = 4U", header)
        self.assertIn("local_lights", header)
        self.assertIn("authored_light_position_locations_", renderer_h)
        self.assertIn("uAuthoredLightPositions[4]", renderer_cpp)
        self.assertIn("uAuthoredLightColors[4]", renderer_cpp)
        self.assertIn("authoredIndex < 4", renderer_cpp)
        self.assertNotIn("uAuthoredLightEnabled", renderer_cpp)

    def test_pcp3_content_abi_envelopes_are_not_runtime_sidecars(self) -> None:
        source = (ROOT / "engine/pcp3/pcp3_asset.cpp").read_text(encoding="utf-8")
        self.assertIn('filename.ends_with(".asset.udata")', source)
        self.assertIn("PCP3 runtime sidecars", source)
        marker = ROOT / "content/pcp3_assets/environment_object/a3_preview_marker"
        self.assertTrue((marker / "a3_preview_marker.pcp3cloud").is_file())
        self.assertFalse((marker / "a3_preview_marker.pcp3.asset.pcp3cloud").exists())

    def test_stress_runner_exposes_bounded_light_budget_scale(self) -> None:
        stress = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn("light_budget_scale", stress)
        self.assertIn('--light-budget-scale=', stress)
        self.assertIn("set_budget_scale", stress)
        self.assertIn("selected_point_budget_cost", stress)

    def test_all_light_diagnostics_and_changed_probe_are_gated(self) -> None:
        diagnostics = (ROOT / "app/main.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        selftests = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        common_paths = (ROOT / "scripts/common_paths.sh").read_text(encoding="utf-8")
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("diagnostic_rays_all", diagnostics)
        self.assertIn("diagnostic_rays_all", game)
        self.assertIn("probe_changed_light_reload.sh", selftests)
        self.assertIn("app/native_stress_main.cpp", selftests)
        self.assertIn("sc_prepare_cmake_build_dir", selftests)
        self.assertIn("CMAKE_HOME_DIRECTORY:INTERNAL", common_paths)
        self.assertIn("CMAKE_CACHEFILE_DIR:INTERNAL", common_paths)
        self.assertIn("signalcloud_illuminosity_multilight_tests", cmake)

    def test_light_lab_round_trip_preserves_runtime_budget(self) -> None:
        from tools.light_lab_gui import light_set_from_json, light_set_to_json

        source = json.loads(
            (ROOT / "content/core/lights/authoring_lab_default.slight").read_text(encoding="utf-8")
        )
        lights, aperture, daynight, unknown, linked = light_set_from_json(source)
        encoded = light_set_to_json(
            lights, aperture, daynight, unknown_fields=unknown, linked_document=linked
        )
        self.assertEqual(encoded["runtime_budget"], source["runtime_budget"])
        self.assertEqual(len(encoded["lights"]), 4)
        for before, after in zip(source["lights"], encoded["lights"], strict=True):
            self.assertEqual(after["budget_priority"], before["budget_priority"])


if __name__ == "__main__":
    unittest.main()
