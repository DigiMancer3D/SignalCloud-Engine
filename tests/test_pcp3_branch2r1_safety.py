from __future__ import annotations

import unittest

from tools.pcp3.editor_branch2r1 import (
    MAX_NATIVE_COMMANDS_PER_POLL,
    MAX_NATIVE_POINTS_PER_SAMPLE,
    estimate_shape_points,
    safe_spacing_for_limit,
)


class PCP3Branch2R1SafetyTests(unittest.TestCase):
    def test_shape_preflight_increases_spacing(self) -> None:
        values = {
            "size_x": 140.0,
            "size_y": 48.0,
            "size_z": 140.0,
            "radius": 70.0,
            "height": 48.0,
            "spacing": 0.05,
        }
        original = estimate_shape_points("box", values)
        spacing = safe_spacing_for_limit("box", values, 200_000)
        adjusted = dict(values, spacing=spacing)
        self.assertGreater(spacing, values["spacing"])
        self.assertGreater(original, 200_000)
        self.assertLessEqual(estimate_shape_points("box", adjusted), 215_000)

    def test_native_limits_are_bounded(self) -> None:
        self.assertLessEqual(MAX_NATIVE_COMMANDS_PER_POLL, 16)
        self.assertLessEqual(MAX_NATIVE_POINTS_PER_SAMPLE, 256)


if __name__ == "__main__":
    unittest.main()
