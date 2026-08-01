from __future__ import annotations

import math
import unittest

from tools.pcp3.interaction import (
    Pane,
    catmull_rom_points,
    inverse_rotate_xyz,
    perspective_project,
    perspective_ray_to_target_plane,
    resample_polyline,
    rotate_xyz,
)


class PCP3Branch2InteractionTests(unittest.TestCase):
    def test_rotation_inverse_round_trip(self) -> None:
        point = (2.5, -1.25, 8.0)
        rotated = rotate_xyz(point, 31.0, -48.0, 17.0)
        restored = inverse_rotate_xyz(rotated, 31.0, -48.0, 17.0)
        for expected, actual in zip(point, restored):
            self.assertAlmostEqual(expected, actual, places=6)

    def test_catmull_curve_and_resampling(self) -> None:
        anchors = [(0.0, 0.0, 0.0), (1.0, 2.0, 0.0), (3.0, 2.0, 1.0), (4.0, 0.0, 2.0)]
        curve = catmull_rom_points(anchors, 12)
        sampled = resample_polyline(curve, 0.2)
        self.assertEqual(curve[0], anchors[0])
        self.assertEqual(curve[-1], anchors[-1])
        self.assertGreater(len(sampled), len(anchors))

    def test_perspective_center_round_trip(self) -> None:
        pane = Pane("NP", "Perspective 3D", 0.0, 0.0, 640.0, 480.0)
        target = (0.0, 1.0, 0.0)
        projected = perspective_project(target, pane, target, -45.0, 24.0, 0.0, 12.0)
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertAlmostEqual(projected[0], 320.0, places=5)
        self.assertAlmostEqual(projected[1], 240.0, places=5)
        restored = perspective_ray_to_target_plane(320.0, 240.0, pane, target, -45.0, 24.0, 0.0, 12.0)
        for expected, actual in zip(target, restored):
            self.assertAlmostEqual(expected, actual, places=5)


if __name__ == "__main__":
    unittest.main()
