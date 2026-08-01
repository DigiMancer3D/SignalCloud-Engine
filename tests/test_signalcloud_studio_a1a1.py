from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_studio.app import build_catalog
from tools.signalcloud_studio.commands import CommandDispatchError, CommandRegistry
from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.shell import DEFAULT_LAYOUT


class SignalCloudStudioA1A1Tests(unittest.TestCase):
    def test_context_derives_managed_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = ToolContext(root)
            self.assertEqual(context.content_root, root / "content")
            self.assertEqual(context.user_data_root, root / "user_data")

    def test_context_copy_changes_only_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context = ToolContext(Path(temp_dir), selected_asset_id="asset.demo")
            changed = context.with_tool("light_lab")
            self.assertEqual(changed.active_tool_key, "light_lab")
            self.assertEqual(changed.selected_asset_id, "asset.demo")
            self.assertEqual(changed.project_root, context.project_root)

    def test_command_registry_is_allowlist_only(self) -> None:
        registry = CommandRegistry()
        registry.register("project.validate", lambda value: value + 1)
        self.assertEqual(registry.dispatch("project.validate", 4), 5)
        with self.assertRaises(CommandDispatchError):
            registry.dispatch("shell.exec", "rm -rf")

    def test_catalog_contains_pcp3_plugin(self) -> None:
        catalog = build_catalog()
        plugin = catalog.get("pcp3")
        self.assertEqual(plugin.display_name, "Point Cloud Paint++")

    def test_canonical_layout_names_all_regions(self) -> None:
        self.assertEqual(DEFAULT_LAYOUT.context_action_bar, "context_action_bar")
        self.assertEqual(DEFAULT_LAYOUT.quick_action_toolbar, "quick_action_toolbar")
        self.assertEqual(DEFAULT_LAYOUT.work_area, "work_area")
        self.assertEqual(DEFAULT_LAYOUT.inspector, "inspector")
        self.assertEqual(DEFAULT_LAYOUT.status_bar, "status_bar")

    def test_public_pcp3_entrypoint_uses_canonical_studio(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "tools" / "pcp3_editor.py").read_text(encoding="utf-8")
        self.assertIn("tools.signalcloud_studio.app", text)
        self.assertNotIn("editor_branch12r1", text)


if __name__ == "__main__":
    unittest.main()
