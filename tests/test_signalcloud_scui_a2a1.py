from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_studio.commands import CommandRegistry
from tools.signalcloud_studio.scui import (
    ScuiDispatcher,
    ScuiPanelState,
    load_scui,
    parse_scui,
    save_scui_atomic,
    serialize_scui,
)
from tools.signalcloud_studio.scui.model import ScuiPanelEvent
from tools.signalcloud_studio.scui.proof import build_proof_registry, proof_panel_path
from tools.signalcloud_studio.scui.tk_renderer import ScuiTkRenderer


ROOT = Path(__file__).resolve().parents[1]
PROOF = proof_panel_path(ROOT)


class SignalCloudScuiA2A1Tests(unittest.TestCase):
    def test_proof_panel_loads_and_orders_controls(self) -> None:
        panel = load_scui(PROOF)
        self.assertTrue(panel.valid, panel.issues)
        self.assertEqual(panel.panel_id, "authoring_lab.project_selector")
        self.assertEqual(
            [control.control_id for control in panel.controls],
            ["intro", "project", "safe_preview", "point_budget", "profile_progress", "refresh"],
        )
        self.assertEqual(panel.initial_values["point_budget"], 8_000_000)

    def test_unknown_panel_and_control_fields_survive_round_trip(self) -> None:
        panel = load_scui(PROOF)
        self.assertIn("future_alpha_hint", panel.raw_sections["panel"])
        self.assertIn("future_native_role", panel.control("project").raw_fields)
        serialized = serialize_scui(panel)
        reloaded = parse_scui(serialized)
        self.assertEqual(reloaded.raw_sections["panel"]["future_alpha_hint"]["preserve"], True)
        self.assertEqual(reloaded.control("project").raw_fields["future_native_role"], "project-picker")

    def test_atomic_save_reloads_valid_document(self) -> None:
        panel = load_scui(PROOF)
        panel.initial_values["safe_preview"] = False
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "panel.scui"
            save_scui_atomic(panel, destination)
            loaded = load_scui(destination)
            self.assertTrue(loaded.valid)
            self.assertFalse(loaded.initial_values["safe_preview"])
            self.assertFalse(destination.with_suffix(".scui.tmp").exists())

    def test_malformed_lines_are_recoverable_but_bad_schema_is_error(self) -> None:
        panel = parse_scui(
            '@udata 1\n[panel]\nschema_name: "signalcloud.scui";\n'
            'schema_major: 1;\npanel_id: "demo.panel";\ntitle: "Demo";\n'
            'broken line\n[control.future]\ntype: "quantum-knob";\n'
        )
        self.assertTrue(panel.valid)
        self.assertTrue(any("missing semicolon" in issue.message for issue in panel.issues))
        self.assertTrue(any("unsupported control type" in issue.message for issue in panel.issues))
        invalid = parse_scui(
            '@udata 1\n[panel]\nschema_name: "signalcloud.scui";\n'
            'schema_major: 2;\npanel_id: "demo.panel";\ntitle: "Demo";\n'
        )
        self.assertFalse(invalid.valid)

    def test_unknown_command_is_telemetry_only(self) -> None:
        registry = CommandRegistry()
        state = ScuiPanelState()
        dispatcher = ScuiDispatcher(registry, state)
        event = dispatcher.emit(
            panel_id="demo.panel",
            control_id="bad",
            command_id="os.shell.execute",
            payload={"value": True},
        )
        self.assertEqual(state.blocked_events, [event])
        self.assertIn("not allowlisted", state.validation[0])

    def test_allowlisted_proof_commands_receive_panel_event(self) -> None:
        received: list[str] = []
        registry = CommandRegistry()
        registry.register("proof.command", lambda event: received.append(event.transaction_id))
        state = ScuiPanelState()
        event = ScuiDispatcher(registry, state).emit(
            panel_id="demo.panel",
            control_id="go",
            command_id="proof.command",
            payload={"value": "ok"},
        )
        self.assertEqual(received, [event.transaction_id])
        self.assertFalse(state.blocked_events)

    def test_proof_registry_contains_only_explicit_commands(self) -> None:
        registry = build_proof_registry()
        self.assertEqual(
            {spec.command_id for spec in registry.specs()},
            {
                "authoring.point_budget.set",
                "authoring.preview.toggle",
                "authoring.profile.refresh",
                "authoring.project.select",
            },
        )
        self.assertFalse(registry.contains("subprocess.run"))

    def test_tk_renderer_declares_clear_supported_and_degraded_types(self) -> None:
        self.assertIn("slider", ScuiTkRenderer.SUPPORTED_TYPES)
        self.assertIn("graph-inspector", ScuiTkRenderer.SUPPORTED_TYPES)
        self.assertNotIn("tabs", ScuiTkRenderer.SUPPORTED_TYPES)

    def test_host_exposes_embedded_scui_proof_action(self) -> None:
        source = (ROOT / "tools" / "signalcloud_studio" / "host.py").read_text(encoding="utf-8")
        self.assertIn("Open SCUI Proof", source)
        self.assertIn("mount_proof_panel", source)
        self.assertIn("content/core/ui/authoring_lab_project_selector.scui", source)

    def test_native_scui_parser_is_part_of_core_build(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("engine/ui/scui_panel.cpp", cmake)
        self.assertIn("signalcloud_scui_tests", cmake)
        header = (ROOT / "engine" / "ui" / "scui_panel.hpp").read_text(encoding="utf-8")
        self.assertIn("ScuiNativeLayout", header)
        self.assertIn("ScuiNativeCommandRegistry", header)


if __name__ == "__main__":
    unittest.main()
