from __future__ import annotations

import unittest
from pathlib import Path

from tools.pcp3.help_guide import (
    HELP_SCHEMA,
    MODE_WORKFLOWS,
    TOPICS,
    HelpContext,
    categories,
    resolve_resource,
    search_topics,
    topic_markdown,
    topics_for_context,
)
from tools.pcp3.io import load_project
from tools.pcp3.model import ENVIRONMENT_TYPES


class Branch12AuthoringHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]

    def test_topic_database_is_comprehensive_and_unique(self) -> None:
        self.assertEqual(HELP_SCHEMA, "pcp3_authoring_help_v1")
        self.assertGreaterEqual(len(TOPICS), 30)
        self.assertEqual(len({topic.key for topic in TOPICS}), len(TOPICS))
        self.assertIn("Troubleshooting", categories())
        self.assertIn("Nine Environment Modes", categories())
        for label in ("Rig", "Timeline", "Gameplay", "Playback", "Factory", "Interaction", "Entity", "World", "Encounter", "Streaming"):
            self.assertTrue(any(topic.authoring_tab == label for topic in TOPICS), label)

    def test_search_finds_runtime_and_failure_language(self) -> None:
        self.assertEqual(search_topics("Signal Void")[0].key, "full_map_stability")
        self.assertTrue(any(topic.key == "blocked_actions" for topic in search_topics("blocked damage")))
        self.assertTrue(any(topic.key == "streaming" for topic in search_topics("semantic reserve")))
        self.assertTrue(any(topic.key == "certificate_export" for topic in search_topics("certificate sidecar")))
        self.assertEqual(search_topics("words that cannot possibly match"), [])

    def test_current_context_prefers_exact_authoring_tab(self) -> None:
        matches = topics_for_context(HelpContext(main_tab="Authoring", authoring_tab="Encounter", mode_key="raid"))
        self.assertEqual(matches[0].key, "encounter")
        matches = topics_for_context(HelpContext(main_tab="Authoring", authoring_tab="Streaming", mode_key="room"))
        self.assertEqual(matches[0].key, "streaming")
        matches = topics_for_context(HelpContext(main_tab="Mode", mode_key="liquid"))
        self.assertEqual(matches[0].key, "mode_liquid")

    def test_all_nine_modes_have_docs_and_starters(self) -> None:
        self.assertEqual(set(MODE_WORKFLOWS), set(ENVIRONMENT_TYPES))
        for key in ENVIRONMENT_TYPES:
            topic = next(topic for topic in TOPICS if topic.key == f"mode_{key}")
            tutorial = resolve_resource(self.root, topic.document)
            starter = resolve_resource(self.root, topic.example)
            self.assertIsNotNone(tutorial, key)
            self.assertIsNotNone(starter, key)
            document = load_project(starter)
            self.assertEqual(document.environment_type, key)
            self.assertFalse(document.runtime["enabled"])
            self.assertTrue(document.metadata["tutorial_starter"])
            self.assertGreaterEqual(len(document.layers), 1)

    def test_resources_cannot_escape_project_root(self) -> None:
        self.assertIsNone(resolve_resource(self.root, "../../etc/passwd"))
        self.assertIsNotNone(resolve_resource(self.root, "docs/PCP3_AUTHORING_HELP_GUIDE.md"))

    def test_topic_markdown_contains_checklist_and_resources(self) -> None:
        quick = next(topic for topic in TOPICS if topic.key == "quick_start")
        text = topic_markdown(quick)
        self.assertIn("# Quick Start", text)
        self.assertIn("- [ ] Template applied", text)
        world = next(topic for topic in TOPICS if topic.key == "world")
        self.assertIn("world_assembly_demo.pcp3", topic_markdown(world))


if __name__ == "__main__":
    unittest.main()
