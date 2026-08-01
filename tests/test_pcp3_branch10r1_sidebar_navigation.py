from __future__ import annotations

import unittest

from tools.pcp3.editor_branch10r1 import (
    AUTHORING_SUBTAB_LABELS,
    REMOVED_TOPBAR_COMMANDS,
    SIDEBAR_ACTIONS,
    wrapped_row_assignments,
)


class Branch10R1SidebarNavigationTests(unittest.TestCase):
    def test_sidebar_actions_are_short_and_stable(self) -> None:
        self.assertEqual(SIDEBAR_ACTIONS, ("Template", "Validate", "Studio"))
        self.assertNotIn("Authoring Studio", SIDEBAR_ACTIONS)
        self.assertNotIn("Mode Template", SIDEBAR_ACTIONS)

    def test_redundant_runtime_toolbar_commands_are_declared_removed(self) -> None:
        expected = {
            "Runtime Playback",
            "Runtime Factory",
            "Interaction Runtime",
            "Entity Runtime",
            "World Assembly",
            "Encounter Runtime",
        }
        self.assertTrue(expected.issubset(set(REMOVED_TOPBAR_COMMANDS)))

    def test_authoring_subtabs_keep_full_names(self) -> None:
        self.assertEqual(len(AUTHORING_SUBTAB_LABELS), 11)
        self.assertIn("Flow/Theme", AUTHORING_SUBTAB_LABELS)
        self.assertIn("Encounter", AUTHORING_SUBTAB_LABELS)

    def test_wrapping_uses_more_rows_as_width_shrinks(self) -> None:
        widths = [72, 86, 92, 94, 104, 88, 82, 96, 75, 70, 92]
        wide = wrapped_row_assignments(widths, 520)
        narrow = wrapped_row_assignments(widths, 300)
        wide_rows = max(row for row, _column in wide) + 1
        narrow_rows = max(row for row, _column in narrow) + 1
        self.assertGreaterEqual(wide_rows, 2)
        self.assertGreater(narrow_rows, wide_rows)

    def test_first_item_in_each_wrapped_row_uses_column_zero(self) -> None:
        positions = wrapped_row_assignments([80, 80, 80, 80, 80], 170)
        seen_rows: set[int] = set()
        for row, column in positions:
            if row not in seen_rows:
                self.assertEqual(column, 0)
                seen_rows.add(row)


if __name__ == "__main__":
    unittest.main()
