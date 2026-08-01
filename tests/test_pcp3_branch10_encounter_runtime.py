from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.advanced_authoring import add_placement, add_wave, ensure_authoring
from tools.pcp3.encounter_runtime import (
    ENCOUNTER_SCHEMA,
    add_boss_phase,
    compile_encounter_runtime,
    encounter_runtime_udata,
    ensure_encounter_runtime,
    simulate_encounter,
    validate_encounter_runtime,
    write_encounter_runtime_files,
)
from tools.pcp3.io import udata_text
from tools.pcp3.model import PCPDocument, PCPPoint
from tools.pcp3.world_assembly import ensure_world_assembly


class Branch10EncounterRuntimeTests(unittest.TestCase):
    def make_encounter(self) -> PCPDocument:
        doc = PCPDocument.new("room")
        doc.asset_id = "branch10_arena"
        doc.display_name = "Branch 10 Arena"
        doc.runtime["preview_zone"] = "Reception Tape"
        doc.points.extend([PCPPoint(-2, 0, -2), PCPPoint(2, 2, 2)])
        world = ensure_world_assembly(doc)
        world.update({"enabled": True, "game_enabled": True, "stress_enabled": True, "host_zone": "Reception Tape"})
        authoring = ensure_authoring(doc)
        add_wave(authoring, 1, ["enemy_a", "enemy_b"], 3, 0.0)
        add_wave(authoring, 2, ["boss_a"], 1, 0.5)
        add_placement(authoring, "friendly_a", "friendly", [1, 0, 1], [0, 0, 0], 1.0, "helpers")
        settings = ensure_encounter_runtime(doc)
        settings.update({
            "enabled": True,
            "game_enabled": True,
            "stress_enabled": True,
            "encounter_id": "arena_pressure",
            "host_zone": "Reception Tape",
            "start_condition": "world_enter",
            "entity_lifetime": 1.0,
            "inter_wave_delay": 0.5,
            "completion_delay": 0.2,
            "reward_policy": "combined_hook",
            "reward_proofs": 2,
            "reward_xar": 12,
            "reward_scrap": 3,
        })
        add_boss_phase(doc, "Opening", 0.0, "Alert", "hover", "#AA33FF", "burst")
        add_boss_phase(doc, "Pressure", 0.6, "Attack", "approach_viewer", "enemy_body", "attack")
        return doc

    def test_defaults_and_limits(self) -> None:
        doc = PCPDocument.new("room")
        settings = ensure_encounter_runtime(doc)
        self.assertEqual(settings["schema"], ENCOUNTER_SCHEMA)
        settings["max_waves"] = 999
        settings["max_active_entities"] = 0
        settings["reward_xar"] = 999999
        ensure_encounter_runtime(doc)
        self.assertEqual(settings["max_waves"], 16)
        self.assertEqual(settings["max_active_entities"], 1)
        self.assertEqual(settings["reward_xar"], 99999)

    def test_compile_waves_boss_friendlies_and_reward(self) -> None:
        payload = compile_encounter_runtime(self.make_encounter())
        self.assertEqual(payload["schema"], ENCOUNTER_SCHEMA)
        self.assertTrue(payload["enabled"])
        self.assertEqual(len(payload["waves"]), 2)
        self.assertEqual(sum(wave["count"] for wave in payload["waves"]), 4)
        self.assertEqual(len(payload["boss_phases"]), 2)
        self.assertEqual(payload["friendlies"][0]["asset_id"], "friendly_a")
        self.assertEqual(payload["reward"]["proofs"], 2)
        self.assertEqual(payload["reward"]["execution"], "telemetry_hook_no_save_mutation")
        self.assertEqual(payload["limits"]["max_reference_depth"], 1)

    def test_deterministic_simulation_sequences_waves_and_reward(self) -> None:
        payload = compile_encounter_runtime(self.make_encounter())
        events = simulate_encounter(payload, duration=20.0, step=0.25)
        kinds = [event["kind"] for event in events]
        self.assertEqual(kinds[0], "encounter_started")
        self.assertEqual(kinds.count("wave_started"), 2)
        self.assertEqual(kinds.count("spawn"), 4)
        self.assertEqual(kinds.count("wave_cleared"), 2)
        self.assertEqual(kinds[-2:], ["encounter_completed", "reward_hook"])
        reward = events[-1]
        self.assertEqual((reward["proofs"], reward["xar"], reward["scrap"]), (2, 12, 3))

    def test_manual_start_remains_inactive(self) -> None:
        doc = self.make_encounter()
        ensure_encounter_runtime(doc)["start_condition"] = "manual"
        self.assertEqual(simulate_encounter(compile_encounter_runtime(doc), 60.0), [])

    def test_validation_reports_missing_references_but_compiles(self) -> None:
        doc = self.make_encounter()
        with tempfile.TemporaryDirectory() as temp:
            issues = validate_encounter_runtime(doc, Path(temp))
        codes = {issue.code for issue in issues}
        self.assertIn("wave_asset_missing", codes)
        self.assertIn("friendly_asset_missing", codes)
        self.assertIn("encounter_compilable", codes)

    def test_udata_and_sidecars(self) -> None:
        doc = self.make_encounter()
        payload = compile_encounter_runtime(doc)
        text = encounter_runtime_udata(payload)
        self.assertIn("[encounter]", text)
        self.assertIn("[reward]", text)
        self.assertIn("[wave.0]", text)
        self.assertIn("[boss_phase.0]", text)
        self.assertIn("[friendly.0]", text)
        with tempfile.TemporaryDirectory() as temp:
            paths = write_encounter_runtime_files(Path(temp), doc)
            loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["encounter"]["id"], "arena_pressure")
            self.assertTrue(paths["udata"].exists())

    def test_main_udata_names_encounter_sidecars(self) -> None:
        doc = self.make_encounter()
        doc.metadata["encounter_json_file"] = "branch10_arena.pcp3encounter.json"
        doc.metadata["encounter_udata_file"] = "branch10_arena.pcp3encounter.udata"
        cert = {"author": {}, "serial_id": "PCP3-TEST", "created_epoch_octal": "0o1"}
        text = udata_text(doc, "branch10_arena.pcp3cloud", "branch10_arena.pcp3", "branch10_arena.pcpcert.json", "abc", cert)
        self.assertIn("[runtime_encounter]", text)
        self.assertIn("branch10_arena.pcp3encounter.udata", text)
        self.assertIn("telemetry_hook_until_explicit_game_approval", text)

    def test_future_fields_survive(self) -> None:
        doc = self.make_encounter()
        settings = ensure_encounter_runtime(doc)
        settings["future_attributes"]["encounter_director"] = {"version": 2}
        settings["boss_phases"][0]["future_attributes"]["phase_music"] = "hum"
        ensure_encounter_runtime(doc)
        self.assertEqual(settings["future_attributes"]["encounter_director"]["version"], 2)
        self.assertEqual(settings["boss_phases"][0]["future_attributes"]["phase_music"], "hum")


if __name__ == "__main__":
    unittest.main()
