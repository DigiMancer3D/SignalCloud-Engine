from __future__ import annotations

import unittest
from pathlib import Path

from tools.signalcloud_studio.scui.codec import load_scui
from tools.signalcloud_studio.scui.registry import ScuiPanelRegistry

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA4A3R1Tests(unittest.TestCase):
    def test_light_registry_allows_every_shipped_panel_command(self) -> None:
        registry = ScuiPanelRegistry.load(ROOT)
        self.assertTrue(registry.valid, registry.issues)
        entry = registry.get("light-lab")
        panel = load_scui(ROOT / entry.relative_path)
        panel_commands = {
            control.command_id
            for control in panel.controls
            if control.enabled and control.visible and control.command_id
        }
        self.assertEqual(set(entry.commands), panel_commands)

    def test_new_page_actions_are_explicitly_trusted(self) -> None:
        commands = set(ScuiPanelRegistry.load(ROOT).get("light-lab").commands)
        self.assertTrue(
            {
                "light.timeline.play",
                "light.timeline.pause",
                "light.timeline.stop",
                "light.probe.sample",
                "light.diagnostics.bake",
            }.issubset(commands)
        )

    def test_game_has_visible_notice_for_every_new_action(self) -> None:
        source = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        for notice in (
            "TIMELINE PLAYING",
            "TIMELINE PAUSED",
            "TIMELINE STOPPED",
            "DIAGNOSTICS BAKED",
        ):
            self.assertIn(notice, source)
        self.assertIn("probe.quality_band", source)


if __name__ == "__main__":
    unittest.main()
