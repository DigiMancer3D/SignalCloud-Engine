from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.advanced_authoring import (
    add_flow_node,
    add_keyframe,
    add_placement,
    add_timeline_event,
    add_trigger,
    add_theme_slot,
    ensure_authoring,
)
from tools.pcp3.model import PCPDocument
from tools.pcp3.runtime_factory import (
    FACTORY_SCHEMA,
    compile_runtime_factory,
    ensure_runtime_factory,
    runtime_factory_udata,
    validate_runtime_factory,
    write_runtime_factory_files,
)


class Branch6RuntimeFactoryTests(unittest.TestCase):
    def document(self) -> PCPDocument:
        doc = PCPDocument.new("room")
        doc.asset_id = "factory_room"
        authoring = ensure_authoring(doc)
        clip = authoring["timelines"][0]
        clip["duration"] = 2.0
        add_keyframe(clip, 0.0, "root", [0, 0, 0], [0, 0, 0], [1, 1, 1])
        add_keyframe(clip, 2.0, "root", [2, 0, 0], [0, 90, 0], [1, 1, 1])
        add_timeline_event(clip, 1.0, "script", "unsafe_demo")
        add_placement(authoring, "nested_orb", "object", [1, 0, 0], [0, 0, 0], 1.0, "props")
        add_trigger(authoring, "scanner", [0, 1, 0], 3.0, "reveal", "door")
        add_trigger(authoring, "damage", [0, 1, 0], 2.0, "apply_damage", "player")
        add_flow_node(authoring, [0, 0, 0], [10, 0, 0], 2.0, 0.5)
        add_theme_slot(authoring, "wall", "#123456", "Square Solid", "plaster_wall")
        factory = ensure_runtime_factory(doc)
        factory.update({
            "enabled": True,
            "game_enabled": True,
            "stress_enabled": True,
            "scanner_gate": True,
            "proximity_gate": True,
            "proximity_radius": 24.0,
            "selected_clip": "Default",
        })
        return doc

    def test_guarded_compile(self) -> None:
        payload = compile_runtime_factory(self.document())
        self.assertEqual(payload["schema"], FACTORY_SCHEMA)
        self.assertEqual(len(payload["timeline"]["keyframes"]), 2)
        self.assertEqual(len(payload["nested_placements"]), 1)
        self.assertEqual(payload["triggers"][0]["runtime_status"], "approved")
        self.assertEqual(payload["triggers"][1]["runtime_status"], "telemetry_only")
        self.assertEqual(payload["triggers"][1]["action"], "none")
        self.assertEqual(payload["limits"]["max_nesting_depth"], 1)
        self.assertEqual(payload["support"]["arbitrary_scripts"], "blocked")

    def test_validation_exposes_blocked_scripts(self) -> None:
        issues = validate_runtime_factory(self.document())
        codes = {issue.code for issue in issues}
        self.assertIn("scripts_blocked", codes)
        self.assertIn("trigger_type_deferred", codes)
        self.assertIn("trigger_action_deferred", codes)
        self.assertIn("factory_compilable", codes)

    def test_udata_and_files(self) -> None:
        doc = self.document()
        payload = compile_runtime_factory(doc)
        text = runtime_factory_udata(payload)
        self.assertIn("[factory]", text)
        self.assertIn("[keyframe.1]", text)
        self.assertIn("[placement.0]", text)
        self.assertIn("[theme.0]", text)
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_runtime_factory_files(Path(tmp), doc)
            self.assertTrue(paths["json"].exists())
            self.assertTrue(paths["udata"].exists())
            loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["asset_id"], "factory_room")

    def test_unknown_factory_fields_survive(self) -> None:
        doc = self.document()
        factory = ensure_runtime_factory(doc)
        factory["future_attributes"]["future_runtime_mode"] = {"value": 77}
        ensure_runtime_factory(doc)
        self.assertEqual(factory["future_attributes"]["future_runtime_mode"]["value"], 77)


if __name__ == "__main__":
    unittest.main()
