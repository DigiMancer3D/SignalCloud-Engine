from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.certificate import validate_certificate
from tools.pcp3.io import export_asset, export_ply, import_ply, load_project, save_project
from tools.pcp3.model import PCPDocument, primitive_box, primitive_sphere


class PCP3PipelineTests(unittest.TestCase):
    def test_roundtrip_certificate_export_and_ply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "content").mkdir()
            document = PCPDocument.new("environment_object")
            document.asset_id = "signal_orb"
            document.display_name = "Signal Orb"
            document.author.creator_name = "Test Creator"
            document.author.title = "Signal Orb"
            document.author.description = "A branch1 test object."
            document.author.tags = ["test", "orb"]
            document.runtime["auto_preview_in_game"] = True
            document.points.extend(primitive_sphere((0, 1, 0), 1.0, 0.22, 1, (0.2, 0.8, 1.0, 1.0), 2.0, "light"))

            project = root / "user_data" / "pcp3" / "projects" / "signal_orb.pcp3"
            paths = save_project(document, project)
            certificate = json.loads(paths["cert"].read_text(encoding="utf-8"))
            self.assertNotIn("version", certificate)
            self.assertFalse(validate_certificate(certificate))

            loaded = load_project(project)
            self.assertEqual(len(loaded.points), len(document.points))
            self.assertEqual(loaded.asset_id, "signal_orb")
            loaded.points[0].radius = 3.5
            save_project(loaded, project, editor_name="Test Creator")
            certificate = json.loads(paths["cert"].read_text(encoding="utf-8"))
            self.assertEqual(certificate["version"], 2)
            self.assertEqual(len(certificate["proof_chain"]), 2)
            self.assertFalse(validate_certificate(certificate))
            tampered = json.loads(json.dumps(certificate))
            tampered["proof_chain"][-1]["checksum"] = "0" * 64
            self.assertTrue(validate_certificate(tampered))

            source_serial = certificate["serial_id"]
            asset_dir = export_asset(loaded, root, project, editor_name="Test Creator")
            self.assertTrue((asset_dir / "signal_orb.udata").is_file())
            exported_certificate = json.loads((asset_dir / "signal_orb.pcpcert.json").read_text(encoding="utf-8"))
            self.assertEqual(exported_certificate["serial_id"], source_serial)
            self.assertGreaterEqual(exported_certificate.get("version", 1), 2)
            udata = (asset_dir / "signal_orb.udata").read_text(encoding="utf-8")
            self.assertIn('data_type: {"value":"pcp3_asset"};', udata)
            self.assertIn('asset_kind: {"value":"environment_object"};', udata)
            self.assertIn('unsupported_attribute_policy', udata)

            ply = root / "signal_orb.ply"
            export_ply(loaded, ply)
            imported = import_ply(ply)
            self.assertEqual(len(imported), len(loaded.points))

    def test_unknown_settings_are_preserved(self) -> None:
        document = PCPDocument.from_dict({
            "schema": "pcp3_project_v0",
            "environment_type": "room",
            "settings": {"width": 12.0, "future_volumetric_field": {"mode": "later"}},
            "layers": [{"id": 1, "name": "Base", "future_layer_shader": "later"}],
        })
        self.assertIn("future_volumetric_field", document.settings.future_attributes)
        self.assertEqual(document.layers[0].future_attributes["future_layer_shader"], "later")
        self.assertEqual(document.environment_type, "room")

    def test_large_primitives_are_bounded(self) -> None:
        document = PCPDocument.new("room")
        points = primitive_box((0, 3, 0), (8, 6, 10), 0.5, 1, (1, 1, 1, 1), 1.5, "wall")
        document.points.extend(points)
        lower, upper = document.bounds()
        self.assertAlmostEqual(lower[0], -4.0)
        self.assertAlmostEqual(upper[1], 6.0)
        self.assertGreater(len(points), 100)


if __name__ == "__main__":
    unittest.main()
