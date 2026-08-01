from __future__ import annotations

import unittest

from tools.pcp3.editor_branch2r3r1 import SYNC_DELAY_MS, clamp_sync_target, sanitize_workspace_data


class Branch2R3R1SyncSafetyTests(unittest.TestCase):
    def test_feedback_loop_workspace_is_repaired(self) -> None:
        value = {
            "schema": "pcp3_workspace_v2",
            "view_type": "4-Square",
            "projection": "All X/Y/Z/NP",
            "pane_states": {
                "Top X/Z": {"depth": -5589.0, "zoom": 2.0, "pan_x": -7720.0, "pan_y": -11034.0},
                "Front X/Y": {"depth": 10.29, "zoom": 2.0, "pan_x": -7720.0, "pan_y": -11034.0},
                "Side Z/Y": {"depth": 3845.25, "zoom": 2.0, "pan_x": -7720.0, "pan_y": -11034.0},
                "Perspective 3D": {"depth": 0.0, "zoom": 2.0, "pan_x": 0.0, "pan_y": 0.0},
            },
            "np_target": [3860.0, -5517.0, 3845.25],
            "perspective_distance": 210.0,
        }
        repaired, reasons = sanitize_workspace_data(value)
        self.assertTrue(reasons)
        self.assertEqual(repaired["schema"], "pcp3_workspace_v3")
        self.assertEqual(repaired["window_sync_delay_ms"], 1300)
        for state in repaired["pane_states"].values():
            self.assertEqual(state["depth"], 0.0)
            self.assertEqual(state["pan_x"], 0.0)
            self.assertEqual(state["pan_y"], 0.0)
        self.assertEqual(repaired["np_target"], [0.0, 0.0, 0.0])

    def test_valid_workspace_is_preserved(self) -> None:
        value = {
            "pane_states": {
                "Top X/Z": {"depth": 2.0, "zoom": 30.0, "pan_x": 20.0, "pan_y": -30.0},
                "Front X/Y": {"depth": 3.0, "zoom": 30.0, "pan_x": 10.0, "pan_y": 15.0},
                "Side Z/Y": {"depth": 4.0, "zoom": 30.0, "pan_x": -5.0, "pan_y": 12.0},
                "Perspective 3D": {"depth": 0.0, "zoom": 28.0, "pan_x": 50.0, "pan_y": -20.0},
            },
            "np_target": [1.0, 2.0, 3.0],
            "perspective_distance": 14.0,
        }
        repaired, reasons = sanitize_workspace_data(value)
        self.assertFalse(reasons)
        self.assertEqual(repaired["pane_states"]["Top X/Z"]["depth"], 2.0)
        self.assertEqual(repaired["np_target"], [1.0, 2.0, 3.0])

    def test_sync_target_is_clamped_to_document_envelope(self) -> None:
        target, changed = clamp_sync_target((3860.0, -5517.0, 3845.25), (-2.0, -2.0, -2.0), (2.0, 2.0, 2.0))
        self.assertTrue(changed)
        self.assertTrue(all(abs(component) <= 26.0 for component in target))

    def test_buffer_is_exactly_requested_delay(self) -> None:
        self.assertEqual(SYNC_DELAY_MS, 1300)


if __name__ == "__main__":
    unittest.main()
