from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content, write_asset_envelope
from tools.signalcloud_tupd.catalog import scan_catalog, scan_result_instances
from tools.signalcloud_tupd.codec import load_recipe, load_result_instance, save_recipe_atomic
from tools.signalcloud_tupd.exporter import export_managed_recipe
from tools.signalcloud_tupd.simulation import TupdSandbox

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA8A2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.by_key = {entry.key: entry for entry in scan_catalog(ROOT)}

    def recipe(self, key: str):
        return load_recipe(self.by_key[key].path)

    def test_starters_declare_revision_sockets_tags_and_tests(self) -> None:
        self.assertEqual(len(self.by_key), 5)
        for entry in self.by_key.values():
            recipe = load_recipe(entry.path)
            self.assertEqual(recipe.schema_minor, 1)
            self.assertEqual(recipe.recipe_revision, 1)
            self.assertTrue(recipe.base_item_id)
            self.assertTrue(recipe.test_actions)
            self.assertTrue(recipe.result.sockets)
            self.assertTrue(recipe.result.tags)

    def test_commit_result_is_explicitly_not_equipped(self) -> None:
        sandbox = TupdSandbox()
        recipe = self.recipe("starter.compatible-signal-grip")
        receipt = sandbox.commit(recipe)
        self.assertTrue(receipt.committed)
        self.assertIsNotNone(sandbox.result_instance)
        self.assertEqual(sandbox.result_instance.state, "COMMITTED / NOT EQUIPPED")
        blocked = sandbox.test_result("inspect")
        self.assertFalse(blocked.accepted)
        self.assertIn("equip/spawn", blocked.outcome)
        self.assertTrue(sandbox.normal_save_unchanged)

    def test_weapon_equips_and_barrier_spawns(self) -> None:
        weapon = TupdSandbox()
        weapon.commit(self.recipe("starter.compatible-signal-grip"))
        self.assertTrue(weapon.equip_or_spawn())
        self.assertTrue(weapon.result_instance.equipped)
        self.assertFalse(weapon.result_instance.spawned)

        barrier = TupdSandbox()
        barrier.commit(self.recipe("starter.office-barrier"))
        self.assertTrue(barrier.equip_or_spawn())
        self.assertFalse(barrier.result_instance.equipped)
        self.assertTrue(barrier.result_instance.spawned)

    def test_declared_tests_are_bounded_distinct_and_stateful(self) -> None:
        sandbox = TupdSandbox()
        recipe = self.recipe("starter.compatible-signal-grip")
        sandbox.commit(recipe)
        sandbox.equip_or_spawn()
        inspect = sandbox.test_result("inspect")
        handle = sandbox.test_result("handle")
        collision = sandbox.test_result("collision")
        self.assertTrue(inspect.accepted)
        self.assertTrue(handle.accepted)
        self.assertTrue(collision.accepted)
        self.assertEqual(len({inspect.signature, handle.signature, collision.signature}), 3)
        self.assertEqual(sandbox.result_instance.test_count, 3)
        self.assertTrue(sandbox.normal_save_unchanged)

    def test_before_after_comparison_exposes_real_changes(self) -> None:
        normal = TupdSandbox().preview(self.recipe("starter.compatible-signal-grip")).comparison()
        forced = TupdSandbox().preview(self.recipe("starter.forced-office-bracket")).comparison()
        repair = TupdSandbox().preview(self.recipe("starter.full-repair")).comparison()
        self.assertGreater(normal.weight_after, normal.weight_before)
        self.assertLess(forced.stability_after, forced.stability_before)
        self.assertGreater(repair.condition_after, repair.condition_before)
        self.assertTrue(normal.added_sockets)
        self.assertGreaterEqual(forced.forced_connection_count, 1)

    def test_recipe_revision_and_connection_authoring_round_trip(self) -> None:
        recipe = self.recipe("starter.compatible-signal-grip")
        recipe.recipe_revision = 7
        recipe.connections.append("part.signal-grip>weapon.service-pistol@socket.grip.aux")
        recipe.result.sockets.append("aux")
        recipe.result.tags.append("user-revision")
        with tempfile.TemporaryDirectory() as directory:
            path = save_recipe_atomic(Path(directory) / "revision.tupd", recipe)
            reloaded = load_recipe(path)
        self.assertEqual(reloaded.recipe_revision, 7)
        self.assertIn("aux", reloaded.result.sockets)
        self.assertIn("user-revision", reloaded.result.tags)
        self.assertEqual(reloaded.connections[-1], recipe.connections[-1])

    def test_export_writes_reloadable_indexed_result_instance(self) -> None:
        recipe = self.recipe("starter.office-barrier")
        sandbox = TupdSandbox()
        preview = sandbox.preview(recipe)
        sandbox.commit(recipe)
        sandbox.equip_or_spawn()
        sandbox.test_result("interact")
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "content").mkdir()
            destination = export_managed_recipe(
                recipe, preview, project, sandbox.result_instance, sandbox.test_history
            )
            instance_path = next(destination.glob("*.tupdinstance"))
            reloaded = load_result_instance(instance_path)
            entries = scan_result_instances(project)
            report = scan_content(project / "content")
        self.assertEqual(reloaded.state, "SPAWNED")
        self.assertEqual(reloaded.test_count, 1)
        self.assertEqual(len(entries), 1)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)

    def test_asset_doctor_rejects_executable_instance_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            target = content / "user/tupd/bad/bad.tupdinstance"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({
                "schema": "signalcloud.tupd-instance",
                "instance_id": "bad.instance",
                "recipe_id": "bad.recipe",
                "result_id": "bad.result",
                "point_budget": 1200,
                "interfaces": [], "sockets": [], "tags": [], "applied_parts": [],
                "connections": [], "forced_connections": [], "test_actions": [],
                "command": "unsafe",
            }), encoding="utf-8")
            write_asset_envelope(
                content, target, asset_id="user.bad.instance", asset_type="tupd_instance",
                family="items", pack="user", license_id="LicenseRef-UserAuthored",
                dependencies=[], hot_reload="authoring-only",
            )
            report = scan_content(content)
        self.assertTrue(any(issue.code == "tupd-instance.executable-field" for issue in report.issues))

    def test_workbench_and_native_surfaces_explain_the_four_step_flow(self) -> None:
        app = (ROOT / "tools/signalcloud_tupd/app.py").read_text(encoding="utf-8")
        panel = (ROOT / "content/core/ui/tupd_workbench.scui").read_text(encoding="utf-8")
        native = (ROOT / "app/tupd_main.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        for token in ("Preview/Compare", "Commit Sandbox", "Equip/Spawn", "Test Result", "QUICK_GUIDE"):
            self.assertIn(token, app)
        for token in ("RESULT CREATED / NOT EQUIPPED", "SCANCODE_E", "SCANCODE_X", "SCANCODE_A"):
            self.assertIn(token, native)
        for token in ("tupd.instance.equip", "tupd.instance.test", "tupd.instance.clear", "tupd.test-action.select"):
            self.assertIn(token, panel)
            self.assertIn(token, game)

    def test_phase_marker_quick_start_and_native_gate_exist(self) -> None:
        alpha_doc = ROOT / "docs/alpha/A8A2_TUPD_RESULT_INSTANCE_TESTING.md"
        quick = ROOT / "docs/help/TUPD_A8_QUICK_START.md"
        self.assertTrue(alpha_doc.is_file())
        self.assertTrue(quick.is_file())
        text = (alpha_doc.read_text(encoding="utf-8") + quick.read_text(encoding="utf-8")).lower()
        for phrase in (
            "commit does not equip", "equip or spawn", "declared test", ".tupdinstance",
            "normal save", "comprehensive guide", "a8 closure",
        ):
            self.assertIn(phrase, text)
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("signalcloud_tupd_instance_tests", cmake)


if __name__ == "__main__":
    unittest.main()
