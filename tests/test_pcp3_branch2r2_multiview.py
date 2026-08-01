from __future__ import annotations

import unittest

from tools.pcp3.editor_branch2r2 import (
    FAST_ACTIVE_BUDGET,
    FOUR_PANE_BUDGET,
    SINGLE_POINT_BUDGET,
    THREE_PANE_BUDGET,
    PaneState,
)


class PCP3Branch2R2MultiViewTests(unittest.TestCase):
    def test_pane_state_round_trip(self) -> None:
        state = PaneState(depth=4.5, zoom=63.0, pan_x=12.0, pan_y=-8.0)
        restored = PaneState.from_json(state.to_json())
        self.assertEqual(restored, state)

    def test_viewport_budgets_are_bounded(self) -> None:
        self.assertLessEqual(FOUR_PANE_BUDGET, 3_200)
        self.assertLessEqual(THREE_PANE_BUDGET, 3_600)
        self.assertLessEqual(FAST_ACTIVE_BUDGET, 600)
        self.assertGreater(SINGLE_POINT_BUDGET, FOUR_PANE_BUDGET)


if __name__ == "__main__":
    unittest.main()
