from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.advanced_authoring import (
    AUTHORING_SCHEMA,
    add_anchor,
    add_bone,
    add_clip,
    add_flow_node,
    add_keyframe,
    add_placement,
    add_theme_slot,
    add_timeline_event,
    add_trigger,
    add_wave,
    authoring_summary,
    capabilities_for,
    ensure_authoring,
    sample_clip,
    validate_authoring,
    write_authoring_report,
)
from tools.pcp3.brushes import BrushPreset, load_brush, save_brush
from tools.pcp3.io import load_project, save_project, udata_text
from tools.pcp3.model import PCPDocument


class Branch4AdvancedAuthoringTests(unittest.TestCase):
    def test_all_modes_have_advanced_capabilities(self) -> None:
        expected = {
            "enemy", "boss", "mini_boss", "raid", "friendly",
            "environment_object", "environment_theme", "room", "liquid",
        }
        self.assertEqual(expected, set(capabilities_for(key) and key for key in expected))

    def test_rig_clip_trigger_placement_flow_theme_and_wave_roundtrip(self) -> None:
        document = PCPDocument.new("boss")
        data = ensure_authoring(document)
        self.assertEqual(AUTHORING_SCHEMA, data["schema"])
        add_bone(data, "root", "", [0, 0, 0], [0, 1, 0])
        add_bone(data, "arm", "root", [0, 1, 0], [1, 1, 0])
        add_anchor(data, "claw", "attack", [1, 1, 0])
        clip = add_clip(data, "Attack", 2.0, 60, False)
        add_keyframe(clip, 0.0, "root", [0, 0, 0], [0, 0, 0], [1, 1, 1])
        add_keyframe(clip, 2.0, "root", [2, 0, 0], [0, 90, 0], [2, 2, 2])
        add_timeline_event(clip, 1.0, "attack", "claw_arc", {"damage": 4})
        add_trigger(data, "proximity", [0, 0, 0], 3.0, "wake_boss", "root", 0.5, False)
        add_placement(data, "ammo_tablet", "kiosk", [2, 0, 1], [0, 45, 0], 1.25, "arena")
        add_flow_node(data, [0, 0, 0], [10, 0, 0], 2.0, 0.7)
        add_theme_slot(data, "wall", "#112233", "Square Solid", "rock_wall")
        add_wave(data, 1, ["hash_dog", "formless_shadow"], 3, 2.0)
        document.metadata["advanced_authoring"] = data

        sample = sample_clip(clip, 1.0, "root")
        self.assertAlmostEqual(1.0, sample["position"][0])
        self.assertAlmostEqual(45.0, sample["rotation_degrees"][1])
        self.assertAlmostEqual(1.5, sample["scale"][0])
        flow = data["flow"]["nodes"][0]["direction"]
        self.assertAlmostEqual(1.0, math.sqrt(sum(value * value for value in flow)))

        summary = authoring_summary(document)
        self.assertEqual(2, summary["bones"])
        self.assertEqual(2, summary["keyframes"])
        self.assertEqual(1, summary["events"])
        self.assertEqual(1, summary["triggers"])
        self.assertEqual(1, summary["placements"])
        self.assertEqual(1, summary["flow_nodes"])
        self.assertEqual(1, summary["theme_slots"])
        self.assertEqual(1, summary["raid_waves"])

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "boss.pcp3"
            save_project(document, project)
            loaded = load_project(project)
            loaded_data = ensure_authoring(loaded)
            self.assertEqual("claw_arc", loaded_data["timelines"][1]["events"][0]["action"])
            report = write_authoring_report(Path(temp) / "boss.pcp3authoring.json", loaded)
            udata = udata_text(loaded, "boss.pcp3cloud", "boss.pcp3", "boss.pcpcert.json", "abc", {"author": {}})
            self.assertIn("[authoring]", udata)
            self.assertIn("pcp3_advanced_authoring_v1", udata)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(AUTHORING_SCHEMA, payload["schema"])
            self.assertEqual(2, payload["summary"]["bones"])
            self.assertEqual("forgiving_preserve_unknown_until_pce_runtime_support", payload["policy"])

    def test_validation_finds_cycle_and_missing_actions(self) -> None:
        document = PCPDocument.new("enemy")
        data = ensure_authoring(document)
        add_bone(data, "a", "b", [0, 0, 0], [0, 1, 0])
        add_bone(data, "b", "a", [0, 1, 0], [0, 2, 0])
        add_trigger(data, "proximity", [0, 0, 0], 1.0, "none")
        issues = validate_authoring(document)
        codes = {issue.code for issue in issues}
        self.assertIn("bone_cycle", codes)
        self.assertIn("trigger_action", codes)

    def test_theme_slot_updates_by_semantic(self) -> None:
        document = PCPDocument.new("environment_theme")
        data = ensure_authoring(document)
        add_theme_slot(data, "wall", "#111111", "Round Soft", "plaster_wall")
        add_theme_slot(data, "wall", "#222222", "Square Solid", "rock_wall")
        self.assertEqual(1, len(data["theme"]["slots"]))
        self.assertEqual("#222222", data["theme"]["slots"][0]["color"])

    def test_advanced_brush_metadata_roundtrip(self) -> None:
        brush = BrushPreset.round_soft("Bone Weight Test", 9)
        brush.metadata.update({
            "semantic": "bone",
            "environment_types": ["enemy", "boss"],
            "authoring_channel": "bone_weight",
            "channel_value": 0.75,
            "stamp_role": "rig",
        })
        with tempfile.TemporaryDirectory() as temp:
            path = save_brush(Path(temp) / "Bone_Weight_Test.3dbrush", brush)
            loaded = load_brush(path)
            self.assertEqual("bone_weight", loaded.metadata["authoring_channel"])
            self.assertEqual(0.75, loaded.metadata["channel_value"])
            self.assertEqual("rig", loaded.metadata["stamp_role"])


if __name__ == "__main__":
    unittest.main()
