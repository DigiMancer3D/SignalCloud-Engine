from __future__ import annotations

import unittest

from tools.pcp3.guided_shapes import (
    FRAME_STYLES,
    PRESET_GROUPS,
    Region3D,
    default_parameters,
    generate_preset,
    generate_room_shell,
    semantic_for_preset,
)


class Branch3R1ArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.top = Region3D.from_points("Top X/Z", (-2.0, 0.0, -2.0), (2.0, 0.0, 2.0), missing_size=0.25)
        self.front = Region3D.from_points("Front X/Y", (-2.0, 0.0, 0.0), (2.0, 3.0, 0.0), missing_size=0.25)
        self.color = (0.8, 0.72, 0.5, 1.0)

    def test_all_requested_presets_exist_and_generate(self) -> None:
        presets = [key for entries in PRESET_GROUPS.values() for key, _label in entries]
        self.assertEqual(len(presets), 19)
        for index, preset in enumerate(presets, start=1):
            region = self.top if preset.endswith("floor") or preset.endswith("ceiling") or preset == "chandelier" else self.front
            params = default_parameters(preset, region, spacing=0.5, room_height=4.0)
            if preset.endswith("frame"):
                params["frame_style"] = FRAME_STYLES[index % len(FRAME_STYLES)]
            points = generate_preset(preset, region, params, index, self.color, 2.0)
            self.assertTrue(points, preset)
            self.assertTrue(all(point.layer_id == index for point in points), preset)

    def test_camera_has_low_red_status_light_metadata(self) -> None:
        params = default_parameters("corner_camera", self.front, spacing=0.25, room_height=4.0)
        params["scale"] = 0.25
        points = generate_preset("corner_camera", self.front, params, 9, self.color, 2.0)
        self.assertTrue(any(point.r > 0.9 and point.g < 0.2 and point.attribute1 == 1.0 for point in points))
        self.assertTrue(all(point.attribute0 <= 0.02 + 1e-9 for point in points))

    def test_opening_frames_keep_center_clear(self) -> None:
        params = default_parameters("window_frame", self.front, spacing=0.25, room_height=4.0)
        params["frame_style"] = "square"
        points = generate_preset("window_frame", self.front, params, 5, self.color, 2.0)
        # A frame should not fill the opening center.
        self.assertFalse(any(abs(point.x) < 0.25 and abs(point.y - 1.5) < 0.25 and abs(point.z) < 0.15 for point in points))
        self.assertTrue(all(point.attribute0 == 1.0 for point in points))

    def test_room_shell_generates_floor_ceiling_and_four_walls(self) -> None:
        params = {
            "spacing": 0.5,
            "wall_thickness": 1.0,
            "wall_top": 0.25,
            "wall_bottom": 0.2,
            "wall_height": 4.0,
            "floor_thickness": 0.25,
            "ceiling_thickness": 0.25,
        }
        result = generate_room_shell(
            self.top,
            params,
            room_width=8.0,
            room_depth=8.0,
            layer_ids={"walls": 1, "floor": 2, "ceiling": 3},
            color=self.color,
            point_radius=2.0,
        )
        self.assertEqual(set(result), {"walls", "floor", "ceiling"})
        self.assertTrue(result["walls"])
        self.assertTrue(result["floor"])
        self.assertTrue(result["ceiling"])
        self.assertTrue(all(point.layer_id == 1 for point in result["walls"]))
        self.assertTrue(all(point.layer_id == 2 for point in result["floor"]))
        self.assertTrue(all(point.layer_id == 3 for point in result["ceiling"]))

    def test_semantics_match_runtime_categories(self) -> None:
        self.assertEqual(semantic_for_preset("plaster_wall"), "wall")
        self.assertEqual(semantic_for_preset("grass_floor"), "floor")
        self.assertEqual(semantic_for_preset("domed_ceiling"), "ceiling")
        self.assertEqual(semantic_for_preset("chandelier"), "light")
        self.assertEqual(semantic_for_preset("door_frame"), "portal")


if __name__ == "__main__":
    unittest.main()
