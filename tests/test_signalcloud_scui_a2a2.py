from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudScuiA2A2Tests(unittest.TestCase):
    def test_native_runtime_is_part_of_core_and_has_dedicated_test(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("engine/ui/scui_native_runtime.cpp", cmake)
        self.assertIn("signalcloud_scui_runtime_tests", cmake)
        self.assertTrue((ROOT / "tests" / "test_scui_runtime.cpp").is_file())

    def test_runtime_contract_exposes_focus_paging_pointer_and_events(self) -> None:
        header = (ROOT / "engine" / "ui" / "scui_native_runtime.hpp").read_text(encoding="utf-8")
        for token in (
            "ScuiNativeKey",
            "focus_previous",
            "page_next",
            "handle_pointer_activate",
            "handle_wheel",
            "build_points",
            "take_events",
            "blocked_commands",
        ):
            self.assertIn(token, header)

    def test_game_opens_native_scui_without_importing_python(self) -> None:
        source = (ROOT / "app" / "game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("SDL_SCANCODE_F8", source)
        self.assertIn("ScuiNativeRuntime", source)
        self.assertIn("active_native_scui()->build_points", source)
        self.assertIn("native_scui.handle_pointer_activate", source)
        self.assertIn("native_scui.handle_wheel", source)
        self.assertIn("SCUI native command:", source)
        self.assertNotIn("Py_Initialize", source)
        self.assertNotIn("system(", source)

    def test_game_registers_only_explicit_proof_commands(self) -> None:
        source = (ROOT / "app" / "game_main.cpp").read_text(encoding="utf-8")
        registered = {
            line.split('register_command("', 1)[1].split('"', 1)[0]
            for line in source.splitlines()
            if "project_scui.register_command" in line
        }
        self.assertEqual(
            registered,
            {
                "authoring.project.select",
                "authoring.preview.toggle",
                "authoring.point_budget.set",
                "authoring.profile.refresh",
            },
        )

    def test_document_records_native_controls_and_safety(self) -> None:
        document = (ROOT / "docs" / "alpha" / "A2A2_NATIVE_POINT_SCUI_RENDERING.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("F8", document)
        self.assertIn("Gameplay movement, shooting", document)
        self.assertIn("Unknown commands remain blocked", document)
        self.assertIn("PointRenderer viewmodel stream", document)


if __name__ == "__main__":
    unittest.main()
