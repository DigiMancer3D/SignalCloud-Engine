from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_playbook.codec import load_playbook, validate_playbook
from tools.signalcloud_playbook.compiler import compile_playbook_runtime
from tools.signalcloud_playbook.evaluator import evaluate_playbook
from tools.signalcloud_playbook.model import PlaybookValidationError


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA6A1Tests(unittest.TestCase):
    def test_shipped_graphs_are_universal_bounded_and_deterministic(self) -> None:
        dog = load_playbook(ROOT / "content/core/playbooks/hash_dog_signal_investigate.playbook")
        water = load_playbook(ROOT / "content/core/playbooks/water_pressure_pulse.playbook")
        self.assertEqual(dog.subject_kind, "enemy")
        self.assertEqual(water.subject_kind, "environmental_effect")
        self.assertLessEqual(len(dog.nodes), 64)
        self.assertLessEqual(len(water.edges), 96)
        trace = evaluate_playbook(dog, {"path.available": True, "event": "event.sound_heard"})
        self.assertEqual([step.operation for step in trace], [
            "event.sound_heard", "move.investigate", "move.guard", "flow.reset"
        ])

    def test_compiler_is_deterministic_and_emits_two_graphs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "one.runtime"
            second = Path(directory) / "two.runtime"
            compile_playbook_runtime(ROOT, first)
            compile_playbook_runtime(ROOT, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            text = first.read_text(encoding="utf-8")
            self.assertIn("STATS 2 8 7 168", text)
            self.assertIn("environmental_effect water_pressure", text)

    def test_unknown_operation_and_unbounded_cycle_are_rejected(self) -> None:
        payload = json.loads((ROOT / "content/core/playbooks/hash_dog_signal_investigate.playbook").read_text())
        payload["nodes"][1]["action"] = "python.exec"
        with self.assertRaises(PlaybookValidationError):
            validate_playbook(payload)
        payload = json.loads((ROOT / "content/core/playbooks/hash_dog_signal_investigate.playbook").read_text())
        payload["nodes"][1]["timeout_seconds"] = 0
        payload["nodes"][2]["cooldown_seconds"] = 0
        payload["edges"].append({"from": "reset", "to": "hear_signal", "branch": "complete"})
        with self.assertRaises(PlaybookValidationError):
            validate_playbook(payload)

    def test_studio_catalog_and_launcher_expose_universal_lab(self) -> None:
        app = (ROOT / "tools/signalcloud_studio/app.py").read_text()
        plugin = (ROOT / "tools/signalcloud_studio/plugins/playbook.py").read_text()
        launcher = (ROOT / "scripts/launch_playbook_editor.sh").read_text()
        self.assertIn("PlaybookPlugin()", app)
        self.assertIn('key = "universal-playbook-lab"', plugin)
        self.assertIn("tools/playbook_editor.py", launcher)

    def test_screenshot_derived_text_profiles_are_split_by_role(self) -> None:
        header = (ROOT / "engine/scfont/text_scale_profile.hpp").read_text()
        self.assertIn("scui_menu: return 1.78F", header)
        self.assertIn("hud_compact: return 2.65F", header)
        self.assertIn("hud_menu: return 2.20F", header)
        self.assertIn("feedback: return 2.25F", header)
        scui = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text()
        hud = (ROOT / "engine/ui/ar_interface.cpp").read_text()
        self.assertIn("SimpleTextRole::scui_menu", scui)
        self.assertIn("SimpleTextRole::hud_menu", hud)
        self.assertIn("SimpleTextRole::feedback", hud)

    def test_rich_world_text_path_is_not_rescaled(self) -> None:
        rich = (ROOT / "engine/scfont/text_point_adapter.cpp").read_text()
        self.assertNotIn("text_scale_profile", rich)
        self.assertIn("append_constant_apparent_billboard", rich)

    def test_build_gates_compile_playbooks_before_native_build(self) -> None:
        for relative in ("scripts/run_selftests.sh", "scripts/setup_dev_environment.sh"):
            text = (ROOT / relative).read_text()
            self.assertIn("compile_playbook_runtime.sh", text)
        cmake = (ROOT / "CMakeLists.txt").read_text()
        self.assertIn("engine/ai/playbook.cpp", cmake)
        self.assertIn("signalcloud_playbook_runtime_tests", cmake)

    def test_phase_marker_and_documentation_exist(self) -> None:
        doc = ROOT / "docs/alpha/A6A1_UNIVERSAL_PLAYBOOK_AND_TEXT_SCALE_FOUNDATION.md"
        self.assertTrue(doc.is_file())
        text = doc.read_text()
        self.assertIn("architecture-wide", text)
        self.assertIn("Rich/world text remains unchanged", text)


if __name__ == "__main__":
    unittest.main()
