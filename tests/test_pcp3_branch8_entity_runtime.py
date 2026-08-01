from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.advanced_authoring import add_anchor, add_bone, add_clip, add_keyframe, ensure_authoring
from tools.pcp3.entity_runtime import (
    assign_bone_channels,
    choose_entity_state,
    compile_entity_runtime,
    deform_point,
    ensure_entity_runtime,
    entity_runtime_udata,
    validate_entity_runtime,
    write_entity_runtime_files,
)
from tools.pcp3.model import PCPDocument, PCPPoint


class Branch8EntityRuntimeTests(unittest.TestCase):
    def make_enemy(self) -> PCPDocument:
        doc = PCPDocument.new("enemy")
        doc.asset_id = "branch8_entity_test"
        authoring = ensure_authoring(doc)
        authoring["timelines"].clear()
        add_bone(authoring, "root", "", (0, 0, 0), (0, 1, 0))
        add_bone(authoring, "arm", "root", (0, 0.75, 0), (1, 0.75, 0))
        add_anchor(authoring, "attack_origin", "attack", (1, 0.75, 0))
        clip = add_clip(authoring, "Idle", 2.0, 30, True)
        add_keyframe(clip, 0.0, "arm", (0, 0, 0), (0, 0, 0), (1, 1, 1))
        add_keyframe(clip, 1.0, "arm", (0, 0, 0), (0, 0, 90), (1, 1, 1))
        add_keyframe(clip, 2.0, "arm", (0, 0, 0), (0, 0, 0), (1, 1, 1))
        settings = ensure_entity_runtime(doc)
        settings.update({"enabled": True, "game_enabled": True, "stress_enabled": True, "attack_anchor": "attack_origin"})
        settings["state_clips"] = {state: "Idle" for state in ("idle", "move", "alert", "attack")}
        return doc

    def test_channels_are_unique_and_stable(self) -> None:
        doc = self.make_enemy()
        first = assign_bone_channels(doc)
        second = assign_bone_channels(doc)
        self.assertEqual(first, second)
        self.assertEqual(len(set(first.values())), 2)
        self.assertEqual(first["root"], 0)
        self.assertEqual(first["arm"], 1)

    def test_compile_and_weighted_deformation(self) -> None:
        doc = self.make_enemy()
        payload = compile_entity_runtime(doc)
        arm_channel = next(b["weight_channel"] for b in payload["bones"] if b["name"] == "arm")
        point = PCPPoint(1.0, 0.75, 0.0, attribute0=1.0, attribute1=float(1000 + arm_channel))
        x, y, z = deform_point(point, payload, "idle", 1.0)
        self.assertAlmostEqual(x, 0.0, places=4)
        self.assertAlmostEqual(y, 1.75, places=4)
        self.assertAlmostEqual(z, 0.0, places=4)
        self.assertEqual(payload["policy"], "guarded_entity_visual_runtime_no_damage_or_save_mutation")

    def test_partial_weight_and_legacy_root_marker(self) -> None:
        doc = self.make_enemy()
        authoring = ensure_authoring(doc)
        clip = authoring["timelines"][0]
        add_keyframe(clip, 1.0, "root", (1, 0, 0), (0, 0, 0), (1, 1, 1))
        payload = compile_entity_runtime(doc)
        point = PCPPoint(0.0, 0.0, 0.0, attribute0=0.5, attribute1=41.0)
        x, _, _ = deform_point(point, payload, "idle", 1.0)
        self.assertAlmostEqual(x, 0.5, places=4)

    def test_distance_state_machine(self) -> None:
        payload = compile_entity_runtime(self.make_enemy())
        self.assertEqual(choose_entity_state(payload, 50.0, 0.0), "idle")
        self.assertEqual(choose_entity_state(payload, 5.0, 0.0), "move")
        self.assertEqual(choose_entity_state(payload, 1.0, 0.6), "alert")
        self.assertEqual(choose_entity_state(payload, 1.0, 0.0), "attack")

    def test_sidecar_round_trip_and_udata(self) -> None:
        doc = self.make_enemy()
        with tempfile.TemporaryDirectory() as temp:
            paths = write_entity_runtime_files(Path(temp), doc)
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            text = paths["udata"].read_text(encoding="utf-8")
            self.assertEqual(payload["schema"], "pcp3_entity_runtime_v1")
            self.assertIn("[bone.0]", text)
            self.assertIn("[bone_keyframe.0]", text)
            self.assertIn("movement_profile", entity_runtime_udata(payload))

    def test_validation_reports_missing_weights(self) -> None:
        doc = self.make_enemy()
        issues = validate_entity_runtime(doc)
        self.assertTrue(any(issue.code == "no_weighted_points" for issue in issues))
        doc.points.append(PCPPoint(0, 0, 0, attribute0=1.0, attribute1=1000.0))
        issues = validate_entity_runtime(doc)
        self.assertFalse(any(issue.code == "no_weighted_points" for issue in issues))


if __name__ == "__main__":
    unittest.main()
