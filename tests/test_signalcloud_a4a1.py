from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_lighting.compiler import compile_light_document, resolve_light_source
from tools.asset_doctor.content_abi import scan_content, write_hot_reload_index
from tools.asset_doctor.hot_reload_bridge import stage_preview_reload

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA4A1Tests(unittest.TestCase):
    def _write_default(self, root: Path, payload: dict) -> Path:
        path = root / "content/core/lights/authoring_lab_default.slight"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def test_default_light_compiles_to_bounded_native_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_default(root, {
                "schema": "signalcloud_light_set_v1",
                "future_vendor_block": {"keep": [1, 2, 3]},
                "lights": [{
                    "id": "reception-key",
                    "name": "Reception Key",
                    "position": [0, 4.6, 3.8],
                    "target": [0, 1.2, 0.8],
                    "color": [1, 0.62, 0.24],
                    "illuminosity_percent": 96,
                    "radius": 12,
                    "scope": "room",
                    "zone": "Reception Tape",
                    "enabled": True,
                    "bounce_count_limit": 1,
                    "point_budget_cost": 640,
                }],
                "day_night": {"time_of_day": 0.35},
            })
            result = compile_light_document(root)
            self.assertEqual(result.light_count, 1)
            self.assertEqual(result.enabled_count, 1)
            self.assertEqual(result.point_budget_cost, 640)
            text = result.output_path.read_text(encoding="utf-8")
            self.assertIn('[light.0]', text)
            self.assertIn('scope: "room";', text)
            self.assertIn('zone: "Reception Tape";', text)
            self.assertIn('point_budget_cost: 640;', text)
            source = json.loads(result.source_path.read_text(encoding="utf-8"))
            self.assertEqual(source["future_vendor_block"], {"keep": [1, 2, 3]})

    def test_invalid_records_default_safely_without_executable_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_default(root, {
                "schema": "unknown_future_schema",
                "lights": [None, "bad"],
                "day_night": "bad",
            })
            result = compile_light_document(root)
            self.assertTrue(result.used_fallback)
            self.assertEqual(result.enabled_count, 0)
            self.assertGreater(result.warning_count, 0)
            text = result.output_path.read_text(encoding="utf-8")
            self.assertIn('id: "safe-fallback";', text)
            self.assertIn('enabled: false;', text)
            self.assertNotIn("eval(", text)
            self.assertNotIn("exec(", text)

    def test_managed_light_source_is_preferred(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            default = self._write_default(root, {"schema": "signalcloud_light_set_v1", "lights": []})
            managed = root / "content/user/lights/authoring_lab_scui_light.slight"
            managed.parent.mkdir(parents=True, exist_ok=True)
            managed.write_text(json.dumps({
                "schema": "signalcloud_light_set_v1",
                "lights": [{"id": "managed", "enabled": True}],
            }), encoding="utf-8")
            self.assertEqual(resolve_light_source(root), managed.resolve())
            result = compile_light_document(root)
            self.assertEqual(result.source_path, managed.resolve())
            self.assertNotEqual(result.source_path, default.resolve())

    def test_compiler_rejects_paths_outside_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            self._write_default(root, {"schema": "signalcloud_light_set_v1", "lights": []})
            external = Path(outside) / "outside.slight"
            external.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                compile_light_document(root, source=external)
            with self.assertRaises(ValueError):
                compile_light_document(root, output=Path(outside) / "runtime.udata")

    def test_shipped_light_declares_full_shared_model(self) -> None:
        payload = json.loads((ROOT / "content/core/lights/authoring_lab_default.slight").read_text(encoding="utf-8"))
        light = payload["lights"][0]
        for field in (
            "id", "position", "target", "color", "illuminosity_percent",
            "aperture_distance", "radius", "cone_or_degree_burst", "scope",
            "enabled", "dynamic", "bounce_count_limit", "bounce_cost",
            "shadow_policy", "day_night_binding", "point_budget_cost",
        ):
            self.assertIn(field, light)
        self.assertEqual(light["zone"], "Reception Tape")
        self.assertEqual(light["scope"], "room")

    def test_native_game_renderer_and_stress_use_shared_runtime(self) -> None:
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        renderer_h = (ROOT / "engine/render/point_renderer.hpp").read_text(encoding="utf-8")
        renderer_cpp = (ROOT / "engine/render/point_renderer.cpp").read_text(encoding="utf-8")
        stress = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn("IlluminosityRuntime illuminosity_runtime", game)
        self.assertIn("renderer.set_illuminosity_frame(authored_light_frame)", game)
        self.assertIn("set_illuminosity_frame", renderer_h)
        self.assertIn("uAuthoredLightColor", renderer_cpp)
        self.assertIn("uAuthoredGlobalStrength", renderer_cpp)
        self.assertIn("authored_light_budget", stress)
        self.assertIn("Authored light budget", stress)



    def test_protected_light_stage_compiles_complete_native_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            light = self._write_default(root, {
                "schema": "signalcloud_light_set_v1",
                "lights": [{
                    "id": "stage-key", "position": [1, 4, 2], "target": [0, 1, 0],
                    "color": [0.2, 0.8, 1.0], "illuminosity_percent": 72,
                    "radius": 10, "scope": "room", "zone": "Reception Tape",
                    "enabled": True, "bounce_count_limit": 2, "point_budget_cost": 777,
                }],
                "day_night": {"time_of_day": 0.25},
            })
            report = scan_content(root / "content")
            write_hot_reload_index(report, root, root / "user_data/studio/hot_reload_candidates.udata")
            payload = json.loads(light.read_text(encoding="utf-8"))
            payload["lights"][0]["color"] = [1.0, 0.1, 0.4]
            light.write_text(json.dumps(payload), encoding="utf-8")
            result = stage_preview_reload(root)
            self.assertEqual(result.changed_light_count, 1)
            status = (root / "user_data/studio/hot_reload_latest.udata").read_text(encoding="utf-8")
            self.assertIn("compiled_runtime_path", status)
            compiled = list((root / "user_data/studio/hot_reload/illuminosity").glob("*.udata"))
            self.assertEqual(len(compiled), 1)
            compiled_text = compiled[0].read_text(encoding="utf-8")
            self.assertIn("point_budget_cost: 777;", compiled_text)
            self.assertIn("color: [1.0,0.1,0.4];", compiled_text)
            game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
            self.assertIn("light->compiled_runtime_path", game)
            self.assertIn("illuminosity_runtime = std::move(staged_runtime)", game)

    def test_light_lab_round_trip_preserves_a4_fields(self) -> None:
        from tools.light_lab_gui import light_set_from_json, light_set_to_json

        source = json.loads((ROOT / "content/core/lights/authoring_lab_default.slight").read_text(encoding="utf-8"))
        source["lights"][0]["future_light_field"] = {"kept": True}
        source["day_night"]["future_day_field"] = "kept"
        lights, aperture, daynight, unknown, linked = light_set_from_json(source)
        encoded = light_set_to_json(
            lights, aperture, daynight, unknown_fields=unknown, linked_document=linked
        )
        light = encoded["lights"][0]
        for key in (
            "id", "aperture_distance", "cone_or_degree_burst", "zone",
            "enabled", "dynamic", "bounce_count_limit", "bounce_cost",
            "shadow_policy", "day_night_binding", "point_budget_cost", "seed",
            "future_light_field",
        ):
            self.assertEqual(light[key], source["lights"][0][key])
        self.assertEqual(light["scope"], "room")
        self.assertEqual(encoded["day_night"]["protected_global"], True)
        self.assertEqual(encoded["day_night"]["future_day_field"], "kept")

    def test_launch_and_test_gates_compile_authored_lights(self) -> None:
        for relative in (
            "scripts/launch_game.sh",
            "scripts/setup_dev_environment.sh",
            "scripts/run_selftests.sh",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("compile_illuminosity_runtime.sh", text)
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("engine/lighting/illuminosity_runtime.cpp", cmake)
        self.assertIn("signalcloud_illuminosity_runtime_tests", cmake)


if __name__ == "__main__":
    unittest.main()
