from __future__ import annotations

import unittest
from pathlib import Path

from tools.pcp3.help_center import (
    ALL_TOPICS,
    GUIDE_SCOPES,
    HELP_CENTER_SCHEMA,
    TOPIC_BY_KEY,
    search_topics,
    topics_for_context,
    topics_for_scope,
)
from tools.pcp3.help_guide import HelpContext


class Branch12R1HelpCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_scopes_and_topic_database(self) -> None:
        self.assertEqual(HELP_CENTER_SCHEMA, "pcp3_help_center_v2")
        self.assertEqual(set(GUIDE_SCOPES), {"all", "editor", "authoring", "mode", "tools", "troubleshooting"})
        self.assertGreaterEqual(len(ALL_TOPICS), 60)
        self.assertEqual(len({topic.key for topic in ALL_TOPICS}), len(ALL_TOPICS))
        for scope in GUIDE_SCOPES:
            self.assertGreater(len(topics_for_scope(scope)), 0, scope)

    def test_new_guides_are_detailed_and_searchable(self) -> None:
        self.assertEqual(search_topics("mental model", "editor")[0].key, "editor_overview")
        self.assertEqual(search_topics("template idempotent", "mode")[0].key, "mode_template_behavior")
        self.assertEqual(search_topics("hidden geometry eraser", "tools")[0].key, "tool_eraser")
        self.assertEqual(search_topics("window sync 1.3", "tools")[0].key, "tool_window_sync")
        self.assertTrue(any(topic.key == "mode_room" for topic in search_topics("room portal", "mode")))

    def test_context_prefers_exact_tool_and_mode(self) -> None:
        matches = topics_for_context(HelpContext(main_tab="Layers", tool_key="eraser", mode_key="room"))
        self.assertEqual(matches[0].key, "tool_eraser")
        matches = topics_for_context(HelpContext(main_tab="Mode", mode_key="liquid"))
        self.assertEqual(matches[0].key, "mode_liquid")
        matches = topics_for_context(HelpContext(main_tab="Authoring", authoring_tab="Streaming", mode_key="room"))
        self.assertEqual(matches[0].key, "streaming")

    def test_guide_documents_exist_and_are_substantial(self) -> None:
        expectations = {
            "docs/PCP3_EDITOR_HELP_GUIDE.md": (300, "Complete Editor Guide"),
            "docs/PCP3_MODE_HELP_GUIDE.md": (250, "Mode Guide"),
            "docs/PCP3_TOOLS_HELP.md": (250, "Detailed Tools Guide"),
        }
        for relative, (minimum_lines, phrase) in expectations.items():
            path = self.root / relative
            self.assertTrue(path.is_file(), relative)
            text = path.read_text(encoding="utf-8")
            self.assertGreaterEqual(len(text.splitlines()), minimum_lines, relative)
            self.assertIn(phrase, text)

    def test_direct_guide_topics_reference_new_documents(self) -> None:
        self.assertEqual(TOPIC_BY_KEY["editor_overview"].document, "docs/PCP3_EDITOR_HELP_GUIDE.md")
        self.assertEqual(TOPIC_BY_KEY["mode_overview"].document, "docs/PCP3_MODE_HELP_GUIDE.md")
        self.assertEqual(TOPIC_BY_KEY["tool_hud"].document, "docs/PCP3_TOOLS_HELP.md")


if __name__ == "__main__":
    unittest.main()
