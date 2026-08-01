from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_studio.scui.codec import load_scui
from tools.signalcloud_studio.scui.registry import ScuiPanelRegistry


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudScuiA2A4Tests(unittest.TestCase):
    def test_registry_discovers_only_validated_shipped_panels(self) -> None:
        registry = ScuiPanelRegistry.load(ROOT)
        self.assertTrue(registry.valid, registry.issues)
        self.assertEqual(registry.keys(), ("light-lab", "project-selector", "tupd-workbench"))
        self.assertEqual(registry.default_panel, "project-selector")
        self.assertEqual(registry.selector_panel, "authoring_lab.panel_selector")
        light = registry.get("light-lab")
        self.assertTrue(light.safe_room_only)
        self.assertEqual(light.preview_kind, "illuminosity-light")
        self.assertEqual(len(light.commands), 13)

    def test_registry_selector_matches_validated_registry_choices(self) -> None:
        registry = ScuiPanelRegistry.load(ROOT)
        panel = load_scui(ROOT / "content/core/ui/authoring_lab_panel_selector.scui")
        self.assertTrue(panel.valid, panel.issues)
        self.assertEqual(panel.panel_id, "authoring_lab.panel_selector")
        selector = panel.control("panel")
        self.assertIsNotNone(selector)
        self.assertEqual(set(selector.choices), set(registry.keys()))
        self.assertEqual(panel.raw_sections["panel"]["registry_path"], "content/core/ui/scui_panel_registry.udata")

    def test_registry_rejects_project_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "content/core/ui").mkdir(parents=True)
            (root / "content/core/ui/scui_panel_registry.udata").write_text(
                '@udata 1\n\n[registry]\n'
                'schema_name: "signalcloud.scui.registry";\n'
                'schema_major: 1;\n'
                'default_panel: "bad";\n'
                'selector_panel: "authoring_lab.panel_selector";\n\n'
                '[panel.bad]\n'
                'panel_id: "bad.panel";\n'
                'label: "Bad";\n'
                'path: "../outside.scui";\n',
                encoding="utf-8",
            )
            registry = ScuiPanelRegistry.load(root)
            self.assertFalse(registry.valid)
            self.assertEqual(registry.entries, [])
            self.assertTrue(any("escapes project root" in issue.message for issue in registry.issues))

    def test_native_save_notice_and_live_preview_are_integrated(self) -> None:
        runtime_h = (ROOT / "engine/ui/scui_native_runtime.hpp").read_text(encoding="utf-8")
        runtime_cpp = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("ScuiNativeNoticeKind", runtime_h)
        self.assertIn("notice_points", runtime_h)
        self.assertIn('"LIGHT SAVED"', game)
        self.assertIn("ScuiNativeNoticeKind::success", game)
        self.assertIn("add_filled_rect", runtime_cpp)
        self.assertIn("ScuiLightPreview", game)
        self.assertIn("light_preview_points", game)
        self.assertIn("SDL_SCANCODE_F6", game)

    def test_studio_host_exposes_registry_browser(self) -> None:
        host = (ROOT / "tools/signalcloud_studio/host.py").read_text(encoding="utf-8")
        browser = (ROOT / "tools/signalcloud_studio/scui/panel_browser.py").read_text(encoding="utf-8")
        self.assertIn("Open SCUI Registry", host)
        self.assertIn("mount_registry_browser", host)
        self.assertIn("Select a trusted shipped SCUI surface", browser)
        self.assertIn("Reload registry", browser)

    def test_a2a4_document_records_visual_confirmation_and_boundaries(self) -> None:
        document = (ROOT / "docs/alpha/A2A4_SCUI_REGISTRY_SELECTOR_AND_LIGHT_PREVIEW.md").read_text(encoding="utf-8")
        self.assertIn("green check", document.lower())
        self.assertIn("F6", document)
        self.assertIn("live preview", document.lower())
        self.assertIn("adaptive 8M", document)
        self.assertIn("does not", document.lower())


if __name__ == "__main__":
    unittest.main()
