from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.pcp3.brushes import BrushLayer, BrushPreset, discover_brushes, ensure_default_brushes, load_brush, save_brush


class Branch2R3FeatureTests(unittest.TestCase):
    def test_brush_roundtrip_and_layer_composite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pixels = [[0.0] * 5 for _ in range(5)]
            pixels[2][2] = 0.5
            brush = BrushPreset("Layered", 5, 5, [BrushLayer("A", 0.5, pixels), BrushLayer("B", 1.0, pixels)])
            path = save_brush(root / "Layered.3dbrush", brush)
            loaded = load_brush(path)
            self.assertEqual(loaded.name, "Layered")
            self.assertEqual(loaded.width, 5)
            self.assertAlmostEqual(loaded.composite()[2][2], 0.625)
            self.assertEqual(len(loaded.active_pixels()), 1)

    def test_default_brush_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            created = ensure_default_brushes(root)
            self.assertEqual(len(created), 3)
            self.assertEqual(len(discover_brushes(root)), 3)
            for path in created:
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(value["schema"], "pcp3_3dbrush_v1")

    def test_active_pixel_limit_is_bounded(self) -> None:
        brush = BrushPreset.square(size=65)
        self.assertEqual(len(brush.active_pixels(limit=512)), 512)


if __name__ == "__main__":
    unittest.main()
