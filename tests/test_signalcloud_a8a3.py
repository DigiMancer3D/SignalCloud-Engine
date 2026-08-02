from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.signalcloud_tupd.analysis import (
    PART_CATALOG,
    analyze_recipe_graph,
    apply_suggested_connections,
    bump_recipe_revision,
    duplicate_recipe,
)
from tools.signalcloud_tupd.catalog import scan_catalog
from tools.signalcloud_tupd.codec import load_recipe, save_recipe_atomic

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA8A3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = {entry.key: entry for entry in scan_catalog(ROOT)}

    def recipe(self, key: str):
        return load_recipe(self.catalog[key].path)

    def test_all_starters_pass_deterministic_graph_analysis(self) -> None:
        self.assertEqual(len(self.catalog), 5)
        signatures: dict[str, str] = {}
        for key, entry in self.catalog.items():
            recipe = load_recipe(entry.path)
            first = analyze_recipe_graph(recipe)
            second = analyze_recipe_graph(recipe)
            self.assertTrue(first.valid, (key, first.issues))
            self.assertEqual(first.signature, second.signature)
            signatures[key] = first.signature
        self.assertEqual(len(set(signatures.values())), 5)
        forced = analyze_recipe_graph(self.recipe("starter.forced-office-bracket"))
        self.assertTrue(any(issue.code == "connection.forced" for issue in forced.issues))

    def test_graph_analyzer_catches_orphan_cycle_and_incompatible_socket(self) -> None:
        recipe = self.recipe("starter.compatible-signal-grip")
        recipe.inputs.append("part.wall-panel")
        recipe.consumed_inputs.append("part.wall-panel")
        recipe.connections.append("part.signal-grip>weapon.service-pistol@anchor")
        recipe.connections.append("weapon.service-pistol>part.signal-grip@body")
        report = analyze_recipe_graph(recipe)
        codes = {issue.code for issue in report.issues}
        self.assertFalse(report.valid)
        self.assertIn("graph.orphan", codes)
        self.assertIn("connection.incompatible", codes)
        self.assertIn("graph.cycle", codes)

    def test_forced_connection_requires_rule_and_penalty(self) -> None:
        recipe = self.recipe("starter.forced-office-bracket")
        recipe.validation_rules = [value for value in recipe.validation_rules if value != "allow_forced_connection"]
        recipe.stability_penalty = 0.0
        recipe.weight_penalty = 0.0
        report = analyze_recipe_graph(recipe)
        codes = {issue.code for issue in report.issues}
        self.assertFalse(report.valid)
        self.assertIn("forced.rule-missing", codes)
        self.assertIn("forced.penalty-missing", codes)

    def test_auto_connect_is_compatible_deterministic_and_never_forced(self) -> None:
        recipe = self.recipe("starter.compatible-signal-grip")
        recipe.connections.clear()
        recipe.inputs.append("part.mount-bracket")
        recipe.consumed_inputs.append("part.mount-bracket")
        first, first_report = apply_suggested_connections(recipe)
        second, second_report = apply_suggested_connections(recipe)
        self.assertEqual(first.connections, second.connections)
        self.assertEqual(first_report.signature, second_report.signature)
        self.assertTrue(first_report.valid)
        self.assertFalse(first.forced_connections)
        self.assertTrue(any("part.signal-grip" in edge for edge in first.connections))
        self.assertTrue(any("part.mount-bracket" in edge for edge in first.connections))

    def test_duplicate_and_revision_helpers_preserve_history(self) -> None:
        source = self.recipe("starter.compatible-signal-grip")
        duplicate = duplicate_recipe(source, "user.signal-grip-copy", "Signal Grip Copy")
        self.assertEqual(duplicate.recipe_revision, 1)
        self.assertEqual(duplicate.extensions["authoring_parent_recipe"], source.recipe_id)
        self.assertNotEqual(duplicate.recipe_id, source.recipe_id)
        self.assertTrue(duplicate.result.result_id.startswith("user.signal-grip-copy"))
        revised = bump_recipe_revision(duplicate)
        self.assertEqual(revised.recipe_revision, 2)
        self.assertEqual(revised.extensions["authoring_previous_revision"], 1)
        with tempfile.TemporaryDirectory() as directory:
            path = save_recipe_atomic(Path(directory) / "copy.tupd", revised)
            reloaded = load_recipe(path)
        self.assertEqual(reloaded.extensions["authoring_parent_recipe"], source.recipe_id)
        self.assertEqual(reloaded.recipe_revision, 2)

    def test_part_palette_is_bounded_unique_and_guided(self) -> None:
        self.assertGreaterEqual(len(PART_CATALOG), 9)
        self.assertEqual(len({entry.item_id for entry in PART_CATALOG}), len(PART_CATALOG))
        self.assertTrue(any(entry.forceable for entry in PART_CATALOG))
        self.assertTrue(all(entry.interface_id for entry in PART_CATALOG))

    def test_workbench_exposes_graph_check_versioning_and_drafts(self) -> None:
        app = (ROOT / "tools/signalcloud_tupd/app.py").read_text(encoding="utf-8")
        for token in (
            "Duplicate Recipe", "Bump Revision", "Save Draft", "Validate Graph",
            "Auto Connect", "Graph Check", "authoring_graph_signature",
            "TUPD_A8_AUTHORING_GUIDE.md",
        ):
            self.assertIn(token, app)
        self.assertIn("user_data", app)
        self.assertIn("tupd_drafts", app)

    def test_native_and_ingame_surfaces_expose_exploded_four_view_inspection(self) -> None:
        native = (ROOT / "app/tupd_main.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        panel = (ROOT / "content/core/ui/tupd_workbench.scui").read_text(encoding="utf-8")
        header = (ROOT / "engine/ui/tupd_ghost_preview.hpp").read_text(encoding="utf-8")
        for token in ("SDL_SCANCODE_G", "SDL_SCANCODE_V", "GHOST EXPLODED", "A8a3"):
            self.assertIn(token, native)
        for token in ("tupd.ghost.view", "tupd.ghost.toggle"):
            self.assertIn(token, game)
            self.assertIn(token, panel)
        self.assertIn("tupd_ghost_exploded", game)
        self.assertIn("ghost_exploded", panel)
        for token in ("result", "interfaces", "sockets", "penalties", "exploded"):
            self.assertIn(token, header.lower())

    def test_a8_closure_docs_rule_and_native_gate_exist(self) -> None:
        alpha = ROOT / "docs/alpha/A8A3_TUPD_GRAPH_AUTHORING_CLOSURE.md"
        guide = ROOT / "docs/help/TUPD_A8_AUTHORING_GUIDE.md"
        rule = ROOT / "content/core/rules/a8a3_tupd_graph_authoring_closure.udata"
        for path in (alpha, guide, rule, Path(str(rule) + ".asset.udata")):
            self.assertTrue(path.is_file(), path)
        text = (alpha.read_text() + guide.read_text()).lower()
        for phrase in (
            "a8 authoring track", "graph", "exploded", "normal save",
            "machine stress tester", "automatic profile promotion",
        ):
            self.assertIn(phrase, text)
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("signalcloud_tupd_graph_inspection_tests", cmake)

    def test_content_tree_remains_asset_doctor_clean(self) -> None:
        report = scan_content(ROOT / "content")
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)


if __name__ == "__main__":
    unittest.main()
