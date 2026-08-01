from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.advanced_authoring import (
    add_anchor,
    add_bone,
    add_flow_node,
    add_keyframe,
    add_placement,
    add_wave,
    add_theme_slot,
    add_timeline_event,
    add_trigger,
    ensure_authoring,
)
from tools.pcp3.io import export_asset
from tools.pcp3.model import Layer, PCPDocument, PCPPoint, SEMANTIC_FLAGS
from tools.pcp3.runtime_bridge import (
    RuntimePreviewOptions,
    compile_preview_document,
    events_crossed,
    transform_xyz,
    write_runtime_preview_bundle,
    write_runtime_report,
)


class Branch5RuntimePreviewTests(unittest.TestCase):
    def make_document(self) -> PCPDocument:
        document = PCPDocument.new("enemy")
        document.asset_id = "runtime_test"
        document.display_name = "Runtime Test"
        document.layers = [Layer(1, "Body", semantic="enemy_body")]
        document.active_layer_id = 1
        document.points = [PCPPoint(1.0, 0.0, 0.0, layer_id=1, flags=SEMANTIC_FLAGS["enemy_body"])]
        authoring = ensure_authoring(document)
        clip = authoring["timelines"][0]
        clip["name"] = "Walk"
        clip["duration"] = 2.0
        clip["loop"] = True
        add_keyframe(clip, 0.0, "root", [0, 0, 0], [0, 0, 0], [1, 1, 1])
        add_keyframe(clip, 2.0, "root", [2, 0, 0], [0, 90, 0], [1, 1, 1])
        add_timeline_event(clip, 1.0, "sound", "alert_bark", {"volume": 0.5})
        add_bone(authoring, "root", "", [0, 0, 0], [0, 1, 0])
        add_anchor(authoring, "attack", "attack", [0.5, 0.7, 0])
        add_trigger(authoring, "proximity", [0, 0, 0], 1.0, "alert")
        add_placement(authoring, "hash_dog", "enemy", [2, 0, 0], [0, 0, 0], 1.0)
        add_flow_node(authoring, [0, 0, 0], [10, 0, 0], 2.0, 0.7)
        add_theme_slot(authoring, "enemy_body", "#FF0000", "Round Soft", "")
        add_wave(authoring, 1, ["hash_dog"], 2, 0.0)
        return document

    def test_root_transform_is_deterministic(self) -> None:
        result = transform_xyz((1.0, 0.0, 0.0), {
            "position": [1.0, 0.0, 0.0],
            "rotation_degrees": [0.0, 90.0, 0.0],
            "scale": [2.0, 1.0, 1.0],
        })
        self.assertAlmostEqual(result[0], 1.0, places=5)
        self.assertAlmostEqual(result[1], 0.0, places=5)
        self.assertAlmostEqual(result[2], -2.0, places=5)

    def test_events_crossed_handles_loop(self) -> None:
        clip = self.make_document().metadata["advanced_authoring"]["timelines"][0]
        self.assertEqual([event["action"] for event in events_crossed(clip, 0.5, 1.2)], ["alert_bark"])
        self.assertEqual(events_crossed(clip, 1.2, 0.2, looped=True), [])

    def test_preview_is_non_destructive_and_contains_overlays(self) -> None:
        document = self.make_document()
        source_point = (document.points[0].x, document.points[0].y, document.points[0].z, document.points[0].r)
        preview = compile_preview_document(document, "Walk", 1.0, RuntimePreviewOptions())
        self.assertEqual(source_point, (document.points[0].x, document.points[0].y, document.points[0].z, document.points[0].r))
        self.assertGreater(len(preview.points), len(document.points))
        self.assertFalse(preview.runtime["enabled"])
        self.assertFalse(preview.runtime["auto_preview_in_game"])
        self.assertTrue(any(layer.name == "Runtime Rig" for layer in preview.layers))
        self.assertTrue(any(layer.name == "Runtime Triggers" for layer in preview.layers))
        self.assertAlmostEqual(preview.points[0].r, 1.0, places=5)

    def test_runtime_report_and_bundle_round_trip(self) -> None:
        document = self.make_document()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = write_runtime_report(root / "asset.pcp3runtime.json", document, "Walk")
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "pcp3_runtime_preview_v1")
            self.assertEqual(payload["support"]["game_runtime_execution"], "deferred_until_explicit_pce_factories")
            bundle = write_runtime_preview_bundle(root, document, "Walk", 1.0)
            self.assertTrue(bundle["project"].exists())
            self.assertTrue(bundle["cloud"].exists())
            self.assertTrue(bundle["runtime"].exists())

    def test_export_udata_names_runtime_sidecar(self) -> None:
        document = self.make_document()
        document.author.creator_name = "Runtime Tester"
        document.metadata["runtime_sidecar_file"] = "runtime_test.pcp3runtime.json"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            asset_dir = export_asset(document, root, editor_name="Runtime Test")
            text = (asset_dir / "runtime_test.udata").read_text(encoding="utf-8")
            self.assertIn("[runtime_preview]", text)
            self.assertIn("runtime_test.pcp3runtime.json", text)

    def test_overlay_toggles_can_disable_every_overlay(self) -> None:
        document = self.make_document()
        options = RuntimePreviewOptions(
            geometry=True, rig=False, anchors=False, triggers=False, placements=False,
            flow=False, raid=False, theme=False, event_markers=False,
        )
        preview = compile_preview_document(document, "Walk", 0.0, options)
        self.assertEqual(len(preview.points), len(document.points))
        self.assertFalse(any(layer.group == "Runtime Preview" for layer in preview.layers))


if __name__ == "__main__":
    unittest.main()
