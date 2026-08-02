from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.signalcloud_tupd.catalog import load_catalog_recipe, scan_catalog
from tools.signalcloud_tupd.codec import load_recipe, recipe_to_dict, save_recipe_atomic
from tools.signalcloud_tupd.exporter import export_managed_recipe
from tools.signalcloud_tupd.simulation import TupdSandbox, make_test_inventory

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA8A1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = scan_catalog(ROOT)
        self.by_key = {entry.key: entry for entry in self.entries}

    def test_five_shared_recipe_proofs_exist(self) -> None:
        self.assertEqual(set(self.by_key), {
            "starter.compatible-signal-grip",
            "starter.forced-office-bracket",
            "starter.small-repair",
            "starter.full-repair",
            "starter.office-barrier",
        })
        for entry in self.entries:
            recipe = load_catalog_recipe(entry)
            self.assertEqual(recipe.schema, "signalcloud.tupd-recipe")
            self.assertLessEqual(recipe.result.point_budget, 50_000)

    def test_recipe_round_trip_preserves_future_fields(self) -> None:
        recipe = load_catalog_recipe(self.by_key["starter.compatible-signal-grip"])
        recipe.extensions["future_pivot14_field"] = {"socket_policy": "stable"}
        with tempfile.TemporaryDirectory() as directory:
            path = save_recipe_atomic(Path(directory) / "roundtrip.tupd", recipe)
            reloaded = load_recipe(path)
        self.assertEqual(
            reloaded.extensions["future_pivot14_field"], {"socket_policy": "stable"}
        )
        self.assertEqual(recipe_to_dict(reloaded)["schema_major"], 1)

    def test_compatible_forced_and_repairs_are_distinct(self) -> None:
        compatible = TupdSandbox().preview(
            load_catalog_recipe(self.by_key["starter.compatible-signal-grip"])
        )
        forced = TupdSandbox().preview(
            load_catalog_recipe(self.by_key["starter.forced-office-bracket"])
        )
        small = TupdSandbox().preview(
            load_catalog_recipe(self.by_key["starter.small-repair"])
        )
        full = TupdSandbox().preview(
            load_catalog_recipe(self.by_key["starter.full-repair"])
        )
        self.assertTrue(compatible.valid)
        self.assertFalse(compatible.forced)
        self.assertTrue(forced.valid)
        self.assertTrue(forced.forced)
        self.assertLess(forced.stability_percent, compatible.stability_percent)
        self.assertGreater(small.condition_after, small.condition_before)
        self.assertEqual(full.condition_after, 100.0)

    def test_failed_validation_and_commit_consume_nothing(self) -> None:
        recipe = load_catalog_recipe(self.by_key["starter.compatible-signal-grip"])
        inventory = make_test_inventory()
        inventory.items["consumable.tupd-tape"] = 0
        sandbox = TupdSandbox(inventory)
        before = sandbox.inventory.clone()
        preview = sandbox.preview(recipe)
        receipt = sandbox.commit(recipe)
        self.assertFalse(preview.valid)
        self.assertFalse(receipt.committed)
        self.assertEqual(sandbox.inventory.items, before.items)
        self.assertEqual(sandbox.inventory.xar, before.xar)
        self.assertTrue(sandbox.normal_save_unchanged)

    def test_matching_duplicate_full_repair_is_atomic(self) -> None:
        recipe = load_catalog_recipe(self.by_key["starter.full-repair"])
        sandbox = TupdSandbox()
        before_duplicate = sandbox.inventory.items["weapon.service-pistol.duplicate"]
        receipt = sandbox.commit(recipe)
        self.assertTrue(receipt.committed)
        self.assertEqual(sandbox.inventory.weapon_condition, 100.0)
        self.assertEqual(
            sandbox.inventory.items["weapon.service-pistol.duplicate"],
            before_duplicate - 1,
        )
        self.assertTrue(sandbox.normal_save_unchanged)

    def test_managed_export_is_reloadable_and_asset_doctor_clean(self) -> None:
        recipe = load_catalog_recipe(self.by_key["starter.office-barrier"])
        preview = TupdSandbox().preview(recipe)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "content").mkdir()
            destination = export_managed_recipe(recipe, preview, project)
            recipe_path = next(destination.glob("*.tupd"))
            reloaded = load_recipe(recipe_path)
            report = scan_content(project / "content")
        self.assertEqual(reloaded.recipe_id, recipe.recipe_id)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)

    def test_asset_doctor_rejects_executable_tupd_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            target = content / "user/tupd/bad/bad.tupd"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({
                "schema": "signalcloud.tupd-recipe",
                "recipe_id": "user.bad",
                "mode": "modification",
                "inputs": [],
                "consumed_inputs": [],
                "required_interfaces": [],
                "connections": [],
                "forced_connections": [],
                "validation_rules": [],
                "point_budget": 1200,
                "script": "rm -rf /",
            }), encoding="utf-8")
            report = scan_content(content)
        self.assertTrue(any(issue.code == "tupd.executable-field" for issue in report.issues))

    def test_desktop_studio_launcher_and_native_target_are_connected(self) -> None:
        app = (ROOT / "tools/signalcloud_tupd/app.py").read_text(encoding="utf-8")
        launcher = (ROOT / "tools/signalcloud_launcher.py").read_text(encoding="utf-8")
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        catalog = (ROOT / "tools/signalcloud_studio/app.py").read_text(encoding="utf-8")
        for token in ("Tupd Authoring Workbench", "Commit Sandbox", "Export & Reload"):
            self.assertIn(token, app)
        self.assertIn("launch_tupd_workbench", launcher)
        self.assertIn("almond_signal_tupd_preview", cmake)
        self.assertIn("TupdWorkbenchPlugin", catalog)

    def test_protected_f5_in_game_mode_uses_isolated_sandbox(self) -> None:
        source = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        for token in (
            "NativeScuiKind::tupd_workbench",
            "SDL_SCANCODE_F5",
            "TupdSandboxSession",
            "tupd_ghost_preview.build_points",
            "normal_save_unchanged",
            "SANDBOX COMMITTED",
            "MANAGED RECIPE EXPORTED",
        ):
            self.assertIn(token, source)
        panel = (ROOT / "content/core/ui/tupd_workbench.scui").read_text(encoding="utf-8")
        self.assertIn('protected_context: "safe-room-authoring"', panel)
        self.assertIn("failed validation consumes nothing", panel)

    def test_a7_warning_cleanup_and_a8_phase_marker(self) -> None:
        warning_test = (ROOT / "tests/test_showcase_info_overlay.cpp").read_text(encoding="utf-8")
        self.assertIn("wide overlay geometry contract", warning_test)
        self.assertIn("narrow overlay geometry contract", warning_test)
        starter_gate = (ROOT / "scripts/validate_showcase_starters.sh").read_text(encoding="utf-8")
        self.assertIn("(80, 80, 0, 0)", starter_gate)
        doc = ROOT / "docs/alpha/A8A1_TUPD_AUTHORING_KERNEL_FOUNDATION.md"
        self.assertTrue(doc.is_file())
        text = doc.read_text(encoding="utf-8").lower()
        for phrase in (
            "data-only", "isolated test inventory", "failed validation consumes nothing",
            "normal save", "pivot 14", "a7a2r2",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
