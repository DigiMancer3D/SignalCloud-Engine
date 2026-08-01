from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.scfs.color_dialog import ColorSlots, DEFAULT_C1, DEFAULT_C2
from tools.scfs.model import (
    FontDocument,
    Glyph,
    Layer,
    Point,
    copy_glyph_snapshot,
    paste_glyph_snapshot,
)
from tools.signalcloud_studio.app import build_catalog


class IntegratedScfsA6A2Tests(unittest.TestCase):
    def test_rich_layout_assigns_independent_depth_around_base(self) -> None:
        font = FontDocument("Integrated rich layers")
        font.glyphs[ord("A")] = Glyph(
            ord("A"),
            6.0,
            [
                Layer("Behind", points=[Point(0, 0)]),
                Layer("Base", points=[Point(0, 0)]),
                Layer("Front", points=[Point(0, 0)]),
            ],
        )
        positioned = font.layout("A")
        self.assertEqual(
            [round(point.z, 3) for _, _, point, _, _ in positioned],
            [-0.5, 0.0, 0.5],
        )

    def test_copy_glyph_has_cross_glyph_and_same_glyph_states(self) -> None:
        font = FontDocument("Integrated clipboard")
        source = Glyph(
            ord("A"),
            8.0,
            [
                Layer("Base", points=[Point(1, 1)]),
                Layer("Copied", 0.55, False, [Point(2, 3, color=DEFAULT_C2)]),
                Layer("Destination", points=[Point(9, 9)]),
            ],
        )
        font.glyphs[ord("A")] = source
        clipboard = copy_glyph_snapshot(source, ord("A"), 1)

        mode, active = paste_glyph_snapshot(font, ord("B"), 0, clipboard)
        self.assertEqual((mode, active), ("glyph", 1))
        self.assertEqual(len(font.glyphs[ord("B")].layers), 3)
        self.assertEqual(font.glyphs[ord("B")].layers[1].points[0].color, DEFAULT_C2)

        mode, active = paste_glyph_snapshot(font, ord("A"), 2, clipboard)
        self.assertEqual((mode, active), ("layer", 2))
        pasted = font.glyphs[ord("A")].layers[2]
        self.assertEqual(pasted.name, "Destination")
        self.assertAlmostEqual(pasted.opacity, 0.55)
        self.assertFalse(pasted.visible)
        self.assertEqual(pasted.points[0].color, DEFAULT_C2)

    def test_color_slots_use_requested_defaults_and_persist(self) -> None:
        self.assertEqual((DEFAULT_C1, DEFAULT_C2), ("#45d8ef", "#45c824"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "color_slots.json"
            ColorSlots(DEFAULT_C1, DEFAULT_C2).save(path)
            self.assertEqual(ColorSlots.load(path), ColorSlots(DEFAULT_C1, DEFAULT_C2))

    def test_studio_and_launcher_expose_integrated_font_studio(self) -> None:
        root = Path(__file__).resolve().parents[1]
        catalog = {item.key: item for item in build_catalog().infos()}
        self.assertIn("font-studio", catalog)
        self.assertTrue((root / "scripts" / "launch_scfs.sh").is_file())
        launcher = (root / "tools" / "signalcloud_launcher.py").read_text(encoding="utf-8")
        self.assertIn("def launch_font_studio", launcher)
        self.assertIn("SignalCloud Font Studio", launcher)


if __name__ == "__main__":
    unittest.main()
