from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.pcp3.advanced_authoring import add_trigger, ensure_authoring
from tools.pcp3.io import export_asset
from tools.pcp3.model import PCPDocument, primitive_sphere
from tools.pcp3.runtime_factory import compile_runtime_factory, ensure_runtime_factory, runtime_factory_udata
from tools.pcp3.runtime_interaction import (
    InteractionSimulator,
    compile_runtime_interaction,
    ensure_runtime_interaction,
    runtime_interaction_udata,
    validate_runtime_interaction,
    write_runtime_interaction_files,
)


class Branch7GuardedInteractionTests(unittest.TestCase):
    def document(self) -> PCPDocument:
        doc = PCPDocument.new("environment_object")
        doc.asset_id = "branch7-test"
        factory = ensure_runtime_factory(doc)
        factory.update({"enabled": True, "game_enabled": True, "stress_enabled": True})
        interaction = ensure_runtime_interaction(doc)
        interaction.update({"enabled": True, "game_enabled": True, "stress_enabled": True})
        return doc

    def test_approved_actions_compile_with_timing(self) -> None:
        doc = self.document()
        authoring = ensure_authoring(doc)
        add_trigger(authoring, "proximity", (0, 0, 0), 2.0, "alert", "", 0.25, True)
        authoring["triggers"][0]["cooldown"] = 1.75
        factory_payload = compile_runtime_factory(doc)
        interaction_payload = compile_runtime_interaction(doc)
        trigger = interaction_payload["triggers"][0]
        self.assertEqual(trigger["runtime_status"], "approved")
        self.assertEqual(trigger["cooldown"], 1.75)
        self.assertIn("delay:", runtime_factory_udata(factory_payload))
        self.assertIn("cooldown:", runtime_factory_udata(factory_payload))
        self.assertIn("[trigger_policy.0]", runtime_interaction_udata(interaction_payload))

    def test_unsafe_action_stays_telemetry_only(self) -> None:
        doc = self.document()
        add_trigger(ensure_authoring(doc), "interaction", (0, 0, 0), 2.0, "damage", "player", 0.0, False)
        payload = compile_runtime_interaction(doc)
        self.assertEqual(payload["triggers"][0]["action"], "none")
        self.assertEqual(payload["triggers"][0]["runtime_status"], "telemetry_only")
        self.assertTrue(any(issue.code == "trigger_deferred" for issue in validate_runtime_interaction(doc)))

    def test_reveal_persists_and_zone_exit_resets(self) -> None:
        doc = self.document()
        add_trigger(ensure_authoring(doc), "scanner", (0, 0, 0), 1.0, "reveal", "", 0.0, False)
        simulator = InteractionSimulator(compile_runtime_interaction(doc))
        simulator.update(now=0.0, viewer=(0, 0, 0), scanner=False, zone="A")
        self.assertFalse(simulator.revealed)
        events = simulator.update(now=0.1, viewer=(0, 0, 0), scanner=True, zone="A")
        self.assertEqual(events[0]["action"], "reveal")
        self.assertTrue(simulator.revealed)
        simulator.update(now=1.0, viewer=(0, 0, 0), scanner=False, zone="A")
        self.assertTrue(simulator.revealed)
        simulator.update(now=2.0, viewer=(0, 0, 0), scanner=False, zone="B")
        self.assertFalse(simulator.revealed)

    def test_repeat_is_cooldown_bounded(self) -> None:
        doc = self.document()
        settings = ensure_runtime_interaction(doc)
        settings["default_cooldown"] = 1.3
        add_trigger(ensure_authoring(doc), "proximity", (0, 0, 0), 5.0, "alert", "", 0.0, True)
        simulator = InteractionSimulator(compile_runtime_interaction(doc))
        all_events = []
        for index in range(20):
            all_events += simulator.update(now=index * 0.1, viewer=(0, 0, 0), zone="A")
        self.assertEqual(len(all_events), 2)
        self.assertGreaterEqual(all_events[1]["time"] - all_events[0]["time"], 1.3 - 1e-9)

    def test_proxy_and_event_limits_are_bounded(self) -> None:
        doc = self.document()
        settings = ensure_runtime_interaction(doc)
        settings["max_active_proxies"] = 4
        settings["max_event_ledger"] = 16
        settings["default_cooldown"] = 0.05
        add_trigger(ensure_authoring(doc), "interaction", (0, 0, 0), 5.0, "spawn_proxy", "", 0.0, True)
        simulator = InteractionSimulator(compile_runtime_interaction(doc))
        for index in range(40):
            simulator.update(now=index * 0.1, viewer=(0, 0, 0), interaction_pressed=True, zone="A")
        self.assertLessEqual(len(simulator.proxies), 4)
        self.assertLessEqual(len(simulator.events), 16)


    def test_export_udata_names_interaction_sidecar(self) -> None:
        doc = self.document()
        doc.author.creator_name = "Interaction Tester"
        doc.points.extend(primitive_sphere((0, 0, 0), 0.5, 0.25, 1, (1, 1, 1, 1), 1.0, "light"))
        doc.metadata["interaction_json_file"] = "branch7-test.pcp3interaction.json"
        doc.metadata["interaction_udata_file"] = "branch7-test.pcp3interaction.udata"
        with tempfile.TemporaryDirectory() as temp:
            asset_dir = export_asset(doc, Path(temp), editor_name="Branch 7 Test")
            text = (asset_dir / "branch7_test.udata").read_text(encoding="utf-8")
            self.assertIn("[runtime_interaction]", text)
            self.assertIn("branch7-test.pcp3interaction.udata", text)

    def test_sidecar_round_trip_files(self) -> None:
        doc = self.document()
        add_trigger(ensure_authoring(doc), "timer", (0, 0, 0), 1.0, "pulse_light", "", 0.5, False)
        with tempfile.TemporaryDirectory() as folder:
            paths = write_runtime_interaction_files(Path(folder), doc)
            self.assertTrue(paths["json"].exists())
            self.assertTrue(paths["udata"].exists())
            self.assertIn("pcp3_guarded_interaction_v1", paths["json"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
