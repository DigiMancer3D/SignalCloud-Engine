from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.brushes import BrushPreset, load_brush, save_brush
from tools.pcp3.environment_profiles import (
    PROFILES,
    apply_mode_template,
    point_budget,
    profile_for,
    validate_document,
    validation_counts,
    write_validation_report,
)
from tools.pcp3.model import ENVIRONMENT_TYPES, PCPDocument, PCPPoint


class PCP3Branch3ModeStudioTests(unittest.TestCase):
    def test_all_environment_modes_have_profiles_and_required_layers(self) -> None:
        self.assertEqual(set(ENVIRONMENT_TYPES), set(PROFILES))
        for kind in ENVIRONMENT_TYPES:
            profile = profile_for(kind)
            self.assertEqual(profile.key, kind)
            self.assertTrue(profile.layers)
            self.assertTrue(any(layer.required for layer in profile.layers))
            self.assertGreater(point_budget(PCPDocument.new(kind)), 0)

    def test_mode_template_is_idempotent_and_reuses_empty_base_layer(self) -> None:
        document = PCPDocument.new("room")
        first = apply_mode_template(document, include_optional=True)
        names = [layer.name for layer in document.layers]
        self.assertIn("Walls", names)
        self.assertIn("Portals", names)
        self.assertNotIn("Base Points", names)
        second = apply_mode_template(document, include_optional=True)
        self.assertTrue(first)
        self.assertEqual(second, [])
        self.assertEqual(len(names), len(document.layers))

    def test_validation_reports_nonfinite_and_missing_mode_data(self) -> None:
        document = PCPDocument.new("enemy")
        document.asset_id = "enemy_test"
        document.display_name = "Enemy Test"
        document.author.creator_name = "Tester"
        apply_mode_template(document, include_optional=False)
        document.points.append(PCPPoint(float("nan"), 0.0, 0.0, layer_id=document.active_layer_id))
        issues = validate_document(document)
        counts = validation_counts(issues)
        self.assertGreaterEqual(counts["error"], 1)
        self.assertTrue(any(issue.code == "nonfinite_points" for issue in issues))
        self.assertTrue(any(issue.code == "missing_mode_metadata" for issue in issues))

    def test_validation_sidecar_round_trip(self) -> None:
        document = PCPDocument.new("environment_object")
        document.asset_id = "validation_orb"
        document.display_name = "Validation Orb"
        document.author.creator_name = "Tester"
        document.metadata["object_class"] = "light_prop"
        apply_mode_template(document, include_optional=True)
        document.points.append(PCPPoint(0.0, 0.0, 0.0, flags=8, layer_id=document.active_layer_id))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation_orb.pcp3validation.json"
            write_validation_report(path, document)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "pcp3_validation_v1")
            self.assertEqual(payload["environment_type"], "environment_object")
            self.assertEqual(payload["point_count"], 1)
            self.assertEqual(payload["policy"], "forgiving_export_preserve_unknown")

    def test_mode_aware_brush_metadata_round_trip(self) -> None:
        brush = BrushPreset.round_soft()
        brush.metadata["semantic"] = "enemy_body"
        brush.metadata["environment_types"] = ["enemy", "boss"]
        brush.metadata["tags"] = ["organic", "soft"]
        with tempfile.TemporaryDirectory() as directory:
            path = save_brush(Path(directory) / "Organic.3dbrush", brush)
            loaded = load_brush(path)
            self.assertEqual(loaded.metadata["semantic"], "enemy_body")
            self.assertEqual(loaded.metadata["environment_types"], ["enemy", "boss"])
            self.assertEqual(loaded.metadata["tags"], ["organic", "soft"])


if __name__ == "__main__":
    unittest.main()
