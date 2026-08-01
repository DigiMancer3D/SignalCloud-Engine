from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.advanced_authoring import add_flow_node, add_placement, add_theme_slot, ensure_authoring
from tools.pcp3.model import PCPDocument, PCPPoint
from tools.pcp3.io import udata_text
from tools.pcp3.world_assembly import (
    WORLD_SCHEMA,
    add_portal,
    add_spawn_point,
    compile_world_assembly,
    ensure_world_assembly,
    validate_world_assembly,
    world_assembly_udata,
    write_world_assembly_files,
    write_world_reference_report,
)


class Branch9WorldAssemblyTests(unittest.TestCase):
    def make_room(self) -> PCPDocument:
        doc = PCPDocument.new("room")
        doc.asset_id = "branch9_room"
        doc.display_name = "Branch 9 Room"
        doc.runtime["preview_zone"] = "Reception Tape"
        doc.points.extend([
            PCPPoint(-2, 0, -2, flags=2),
            PCPPoint(2, 0, 2, flags=2),
            PCPPoint(-2, 2, -2, flags=1),
            PCPPoint(2, 2, 2, flags=3),
            PCPPoint(0, 0.25, 0, flags=6),
            PCPPoint(0, -0.25, 0, flags=7),
        ])
        authoring = ensure_authoring(doc)
        add_placement(authoring, "signal_orb", "object", [1, 0.5, 1], [0, 45, 0], 1.0, "props")
        add_flow_node(authoring, [0, 0.25, 0], [10, 0, 0], 2.0, 0.5)
        add_theme_slot(authoring, "wall", "#123456", "Square Solid", "plaster_wall")
        world = ensure_world_assembly(doc)
        world.update({
            "enabled": True,
            "game_enabled": True,
            "stress_enabled": True,
            "world_id": "world_a",
            "room_id": "room_a",
            "room_name": "Room A",
            "host_zone": "Reception Tape",
            "execute_portals": True,
            "liquid_runtime": True,
            "show_bounds_debug": True,
        })
        add_portal(
            doc,
            portal_id="north_door",
            kind="door",
            position=[0, 1, -2],
            size=[1.2, 2.2, 0.4],
            destination_asset_id="room_b",
            destination_portal_id="south_door",
        )
        add_spawn_point(doc, "default_spawn", "default", [0, 0.2, 1.5], 180)
        return doc

    def test_defaults_and_limits(self) -> None:
        doc = PCPDocument.new("room")
        world = ensure_world_assembly(doc)
        self.assertEqual(world["schema"], WORLD_SCHEMA)
        self.assertFalse(world["enabled"])
        world["max_portals"] = 999
        world["portal_cooldown"] = -1
        ensure_world_assembly(doc)
        self.assertEqual(world["max_portals"], 32)
        self.assertEqual(world["portal_cooldown"], 0.1)

    def test_compile_portal_liquid_theme_and_placement(self) -> None:
        payload = compile_world_assembly(self.make_room())
        self.assertEqual(payload["schema"], WORLD_SCHEMA)
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["world"]["room_id"], "room_a")
        self.assertEqual(payload["portals"][0]["destination_asset_id"], "room_b")
        self.assertEqual(payload["spawn_points"][0]["role"], "default")
        self.assertEqual(payload["placements"][0]["asset_id"], "signal_orb")
        self.assertEqual(payload["theme"]["slots"][0]["semantic"], "wall")
        self.assertEqual(payload["liquid"]["surface_points"], 1)
        self.assertEqual(payload["liquid"]["volume_points"], 1)
        self.assertAlmostEqual(payload["liquid"]["flow_nodes"][0]["direction"][0], 1.0)
        self.assertEqual(payload["limits"]["max_reference_depth"], 1)

    def test_validation_exposes_missing_references_but_stays_compilable(self) -> None:
        doc = self.make_room()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            issues = validate_world_assembly(doc, root)
        codes = {issue.code for issue in issues}
        self.assertIn("portal_asset_missing", codes)
        self.assertIn("placement_missing", codes)
        self.assertIn("world_compilable", codes)

    def test_udata_and_sidecar_round_trip(self) -> None:
        doc = self.make_room()
        payload = compile_world_assembly(doc)
        text = world_assembly_udata(payload)
        self.assertIn("[world]", text)
        self.assertIn("[portal.0]", text)
        self.assertIn("[spawn.0]", text)
        self.assertIn("[world_placement.0]", text)
        self.assertIn("[world_theme.0]", text)
        self.assertIn("[world_flow.0]", text)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = write_world_assembly_files(root, doc, root)
            audit = write_world_reference_report(root / "audit.json", doc, root)
            loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["asset_id"], "branch9_room")
            self.assertTrue(paths["udata"].exists())
            self.assertEqual(json.loads(audit.read_text(encoding="utf-8"))["schema"], "pcp3_world_reference_audit_v1")

    def test_main_udata_names_world_sidecars(self) -> None:
        doc = self.make_room()
        doc.metadata["world_json_file"] = "branch9_room.pcp3world.json"
        doc.metadata["world_udata_file"] = "branch9_room.pcp3world.udata"
        doc.metadata["world_reference_file"] = "branch9_room.pcp3world.references.json"
        cert = {"author": {}, "serial_id": "PCP3-TEST", "created_epoch_octal": "0o1"}
        text = udata_text(doc, "branch9_room.pcp3cloud", "branch9_room.pcp3", "branch9_room.pcpcert.json", "abc", cert)
        self.assertIn("[runtime_world]", text)
        self.assertIn("branch9_room.pcp3world.udata", text)
        self.assertIn("branch9_room.pcp3world.references.json", text)

    def test_unknown_fields_survive(self) -> None:
        doc = self.make_room()
        world = ensure_world_assembly(doc)
        world["future_attributes"]["world_stream_partition"] = {"value": 9}
        world["portals"][0]["future_attributes"]["future_lock"] = "almond"
        ensure_world_assembly(doc)
        self.assertEqual(world["future_attributes"]["world_stream_partition"]["value"], 9)
        self.assertEqual(world["portals"][0]["future_attributes"]["future_lock"], "almond")


if __name__ == "__main__":
    unittest.main()
