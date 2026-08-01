from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudScuiA2A2R1Tests(unittest.TestCase):
    def test_runtime_reports_backplate_and_wrapped_lines(self) -> None:
        header = (ROOT / "engine" / "ui" / "scui_native_runtime.hpp").read_text(encoding="utf-8")
        self.assertIn("backplate_points", header)
        self.assertIn("wrapped_text_lines", header)
        self.assertIn("last_backplate_points_", header)
        self.assertIn("last_wrapped_text_lines_", header)

    def test_native_renderer_has_dense_point_backplate(self) -> None:
        source = (ROOT / "engine" / "ui" / "scui_native_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("add_filled_rect", source)
        self.assertIn("panel_plate_basis", source)
        self.assertIn("row_plate_basis", source)
        self.assertIn("Two interleaved, depth-separated sheets", source)
        self.assertIn("world signs and room", source)
        self.assertNotIn("glBegin", source)

    def test_native_renderer_uses_word_aware_wrapping(self) -> None:
        source = (ROOT / "engine" / "ui" / "scui_native_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("wrap_text", source)
        self.assertIn("add_wrapped_text", source)
        self.assertIn("maximum_lines", source)
        self.assertIn("kLabelRight", source)

    def test_cpp_runtime_test_requires_legibility_geometry(self) -> None:
        test_source = (ROOT / "tests" / "test_scui_runtime.cpp").read_text(encoding="utf-8")
        self.assertIn("dense readability backplate", test_source)
        self.assertIn("wrapped title, labels, values, and footer text", test_source)
        self.assertIn("40'000U", test_source)

    def test_document_records_visual_acceptance_without_scope_growth(self) -> None:
        document = (
            ROOT / "docs" / "alpha" / "A2A2R1_NATIVE_SCUI_LEGIBILITY.md"
        ).read_text(encoding="utf-8")
        self.assertIn("point backplate", document.lower())
        self.assertIn("word-aware wrapping", document)
        self.assertIn("adaptive 8M", document)
        self.assertIn("Unknown commands remain blocked", document)


if __name__ == "__main__":
    unittest.main()
