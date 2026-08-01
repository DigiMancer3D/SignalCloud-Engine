from __future__ import annotations

import unittest

from tools.pcp3.advanced_authoring import add_trigger, ensure_authoring
from tools.pcp3.model import PCPDocument
from tools.pcp3.runtime_factory import ensure_runtime_factory
from tools.pcp3.runtime_interaction import (
    compile_runtime_interaction,
    ensure_runtime_interaction,
    normalize_action,
    validate_runtime_interaction,
)


class Branch7R1InteractionAuthoringTests(unittest.TestCase):
    def document(self) -> PCPDocument:
        doc = PCPDocument.new("environment_object")
        doc.asset_id = "interaction_authoring_test"
        return doc

    def test_legacy_scanner_reveal_is_normalized(self) -> None:
        doc = self.document()
        add_trigger(ensure_authoring(doc), "scanner", (0, 0, 0), 2.0, "scanner_reveal")
        payload = compile_runtime_interaction(doc)
        self.assertEqual(normalize_action("scanner_reveal"), "reveal")
        self.assertEqual(payload["triggers"][0]["action"], "reveal")
        self.assertEqual(payload["triggers"][0]["runtime_status"], "approved")

    def test_per_trigger_cooldown_is_authored(self) -> None:
        doc = self.document()
        record = add_trigger(
            ensure_authoring(doc),
            "interaction",
            (1, 2, 3),
            4.0,
            "pulse_light",
            "",
            0.25,
            True,
            2.75,
        )
        self.assertEqual(record["cooldown"], 2.75)
        self.assertEqual(compile_runtime_interaction(doc)["triggers"][0]["cooldown"], 2.75)

    def test_enabled_without_triggers_is_warning(self) -> None:
        doc = self.document()
        ensure_runtime_interaction(doc)["enabled"] = True
        ensure_runtime_factory(doc)["enabled"] = True
        issues = validate_runtime_interaction(doc)
        no_actions = next(issue for issue in issues if issue.code == "no_approved_actions")
        self.assertEqual(no_actions.severity, "warning")

    def test_factory_and_interaction_metadata_are_independent(self) -> None:
        doc = self.document()
        interaction = ensure_runtime_interaction(doc)
        factory = ensure_runtime_factory(doc)
        interaction.update({"enabled": True, "stress_enabled": True})
        factory.update({"enabled": True, "stress_enabled": True})
        self.assertTrue(doc.metadata["runtime_interaction"]["enabled"])
        self.assertTrue(doc.metadata["runtime_factory"]["enabled"])
        self.assertIsNot(doc.metadata["runtime_interaction"], doc.metadata["runtime_factory"])


if __name__ == "__main__":
    unittest.main()
