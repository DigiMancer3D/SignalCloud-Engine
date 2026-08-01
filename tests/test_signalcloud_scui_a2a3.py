from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.documents import DocumentContextBus, DocumentContextStore, StudioDocumentContext
from tools.signalcloud_studio.scui.bindings import (
    JsonDocumentBinding,
    get_json_path,
    read_native_state_overlay,
    safe_project_path,
    set_json_path,
    write_native_state_overlay,
)
from tools.signalcloud_studio.scui.codec import load_scui, serialize_scui
from tools.signalcloud_studio.scui.light_lab import LIGHT_COMMANDS, LightLabScuiSession, light_panel_path


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudScuiA2A3Tests(unittest.TestCase):
    def test_light_panel_has_managed_document_bindings(self) -> None:
        panel = load_scui(light_panel_path(ROOT))
        self.assertTrue(panel.valid, panel.issues)
        self.assertEqual(panel.panel_id, "light_lab.control_surface")
        bindings = {control.control_id: control.document_binding for control in panel.controls if control.document_binding}
        self.assertEqual(len(bindings), 6)
        self.assertEqual(bindings["illuminosity"], "lights.0.illuminosity_percent")
        self.assertIn('document_binding: "lights.0.radius";', serialize_scui(panel))
        self.assertEqual(panel.raw_sections["panel"]["protected_context"], "safe-room-authoring")

    def test_json_path_binding_handles_objects_and_lists(self) -> None:
        document = {"lights": [{"radius": 9.0}], "future": {"keep": True}}
        self.assertEqual(get_json_path(document, "lights.0.radius"), 9.0)
        set_json_path(document, "lights.0.radius", 14.5)
        set_json_path(document, "day_night.time_of_day", 0.75)
        self.assertEqual(document["lights"][0]["radius"], 14.5)
        self.assertEqual(document["day_night"]["time_of_day"], 0.75)
        self.assertTrue(document["future"]["keep"])

    def test_safe_binding_path_rejects_project_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            with self.assertRaises(ValueError):
                safe_project_path(root, root.parent / "outside.slight")

    def test_binding_hydrates_and_saves_user_copy_preserving_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "content/core/lights/default.slight"
            output = root / "content/user/lights/copy.slight"
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({
                "schema": "signalcloud_light_set_v1",
                "lights": [{"illuminosity_percent": 70.0, "radius": 8.0, "scope": "local", "future": 9}],
                "day_night": {"day_illuminosity_percent": 90.0, "night_illuminosity_percent": 15.0, "time_of_day": 0.2},
                "future_top": {"keep": "yes"},
            }), encoding="utf-8")
            binding = JsonDocumentBinding.open(root, source, output)
            panel = load_scui(light_panel_path(ROOT))
            from tools.signalcloud_studio.scui.model import ScuiPanelState
            state = ScuiPanelState(values=dict(panel.initial_values))
            binding.hydrate(panel, state)
            self.assertEqual(state.values["light_i"], 70.0)
            binding.apply(panel.control("illuminosity"), 111.0)
            saved = binding.save_atomic()
            result = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(result["lights"][0]["illuminosity_percent"], 111.0)
            self.assertEqual(result["lights"][0]["future"], 9)
            self.assertEqual(result["future_top"]["keep"], "yes")
            self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["lights"][0]["illuminosity_percent"], 70.0)

    def test_light_session_uses_shared_light_document_or_managed_default(self) -> None:
        context = ToolContext(
            ROOT,
            document_context=StudioDocumentContext(),
            document_store=DocumentContextStore.for_project(ROOT, "test_a2a3_context.json"),
            document_bus=DocumentContextBus(),
        )
        try:
            session = LightLabScuiSession(context, lambda _text: None)
            self.assertEqual(session.binding.source_path.name, "authoring_lab_default.slight")
            self.assertEqual(session.binding.output_path.name, "authoring_lab_scui_light.slight")
            self.assertEqual({spec.command_id for spec in session.registry().specs()}, set(LIGHT_COMMANDS))
        finally:
            context.document_store.path.unlink(missing_ok=True)

    def test_native_overlay_writer_round_trips_atomic_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.udata"
            write_native_state_overlay(
                path,
                panel_id="light_lab.control_surface",
                source_document="content/user/lights/demo.slight",
                values={"light_i": 91.0, "light_scope": "area", "ignored": {"complex": True}},
            )
            self.assertEqual(read_native_state_overlay(path), {"light_i": 91.0, "light_scope": "area"})
            self.assertFalse(path.with_suffix(".udata.tmp").exists())

    def test_native_overlay_reader_is_forgiving(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "overlay.udata"
            path.write_text(
                '@udata 1\n[panel]\npanel_id: "light_lab.control_surface";\n'
                '[state]\nlight_i: 88.0;\nlight_scope: "room";\nbroken line\n',
                encoding="utf-8",
            )
            self.assertEqual(read_native_state_overlay(path), {"light_i": 88.0, "light_scope": "room"})

    def test_game_hides_system_cursor_and_limits_native_light_lab_to_safe_rooms(self) -> None:
        source = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("SDL_HideCursor", source)
        self.assertIn("SDL_ShowCursor", source)
        self.assertIn("SDL_CursorVisible", source)
        self.assertIn("SDL_SCANCODE_F7", source)
        self.assertIn("Native Light Lab SCUI is limited to protected safe rooms", source)
        self.assertIn("light_lab_native_state.udata", source)

    def test_studio_host_exposes_light_lab_scui_surface(self) -> None:
        source = (ROOT / "tools/signalcloud_studio/host.py").read_text(encoding="utf-8")
        self.assertIn("Open Light Lab SCUI", source)
        self.assertIn("mount_light_lab_panel", source)


if __name__ == "__main__":
    unittest.main()
