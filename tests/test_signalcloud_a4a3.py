from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.signalcloud_lighting.compiler import compile_light_document
from tools.signalcloud_lighting.exporter import export_sclight
from tools.signalcloud_studio.scui.codec import load_scui

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA4A3Tests(unittest.TestCase):
    def test_native_light_panel_exposes_timeline_probe_and_bake(self) -> None:
        panel = load_scui(ROOT / "content/core/ui/light_lab_control_surface.scui")
        commands = {control.command_id for control in panel.controls if control.command_id}
        self.assertTrue(
            {
                "light.timeline.play",
                "light.timeline.pause",
                "light.timeline.stop",
                "light.probe.sample",
                "light.diagnostics.bake",
            }.issubset(commands)
        )
        self.assertGreaterEqual(len(panel.controls), 14)

    def test_game_timeline_has_separate_manual_and_playback_ownership(self) -> None:
        source = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("std::numeric_limits<float>::quiet_NaN()", source)
        self.assertIn("illuminosity_runtime.play_day_night()", source)
        self.assertIn("illuminosity_runtime.pause_day_night(true)", source)
        self.assertIn("illuminosity_runtime.stop_day_night(0.35F)", source)
        self.assertIn("bake_illuminosity_grid", source)
        self.assertIn("probe_surface(player.position(), current_zone)", source)

    def test_canonical_sclight_export_is_deterministic_and_compilable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "content/core/lights/demo.slight"
            source.parent.mkdir(parents=True)
            source.write_text(
                json.dumps(
                    {
                        "schema": "signalcloud_light_set_v2",
                        "runtime_budget": {"max_active_lights": 2, "max_point_budget": 1024},
                        "lights": [
                            {
                                "id": "demo",
                                "name": "Demo",
                                "position": [0, 3, 0],
                                "target": [0, 1, 0],
                                "color": [1, 0.5, 0.2],
                                "illuminosity_percent": 80,
                                "radius": 10,
                                "scope": "room",
                                "zone": "Reception Tape",
                                "enabled": True,
                                "point_budget_cost": 256,
                            }
                        ],
                        "day_night": {"time_of_day": 0.35, "playing": True, "paused": True},
                        "future": {"keep": "yes"},
                    }
                ),
                encoding="utf-8",
            )
            output = root / "content/user/lights/demo.sclight"
            first = export_sclight(root, source=source, output=output, compile_runtime=False)
            first_bytes = first.read_bytes()
            second = export_sclight(root, source=source, output=output, compile_runtime=False)
            self.assertEqual(first_bytes, second.read_bytes())
            payload = json.loads(second.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "signalcloud_light_set_v3")
            self.assertEqual(payload["future"], {"keep": "yes"})
            self.assertTrue(payload["canonical_export"]["data_only"])
            result = compile_light_document(root, source=second)
            self.assertEqual(result.light_count, 1)
            runtime = result.output_path.read_text(encoding="utf-8")
            self.assertIn("paused: true;", runtime)

    def test_asset_doctor_classifies_sclight_as_light_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            content = Path(temporary) / "content"
            asset = content / "user/lights/demo.sclight"
            asset.parent.mkdir(parents=True)
            asset.write_text(
                json.dumps({"schema": "signalcloud_light_set_v3", "lights": []}),
                encoding="utf-8",
            )
            report = scan_content(content)
            records = [record for record in report.records if record.relative_path.endswith("demo.sclight")]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].asset_type, "light_set")

    def test_light_lab_preserves_pause_and_exposes_export(self) -> None:
        source = (ROOT / "tools/light_lab_gui.py").read_text(encoding="utf-8")
        self.assertIn('"paused": bool(daynight.paused)', source)
        self.assertIn('text="Export .sclight"', source)
        self.assertIn("export_sclight", source)

    def test_build_and_selftest_gates_include_authoring_bake(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("engine/lighting/illuminosity_bake.cpp", cmake)
        self.assertIn("signalcloud_illuminosity_bake", cmake)
        self.assertIn("signalcloud_illuminosity_authoring_tests", cmake)
        selftest = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        self.assertIn("export_sclight.sh", selftest)
        self.assertIn("signalcloud_illuminosity_bake", selftest)


if __name__ == "__main__":
    unittest.main()
