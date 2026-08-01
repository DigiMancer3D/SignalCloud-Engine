from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from native_stress_hud import (  # noqa: E402
    floor_text,
    format_hms,
    read_hud_preferences,
    status_alert,
    valid_window_geometry,
    write_hud_preferences,
)


class NativeStressHudTests(unittest.TestCase):
    def test_timer_format(self) -> None:
        self.assertEqual(format_hms(0), "00:00:00")
        self.assertEqual(format_hms(3661.9), "01:01:01")

    def test_alert_priority(self) -> None:
        self.assertEqual(status_alert({"scanner": True}), "SCANNER RECONSTRUCTION ACTIVE")
        self.assertEqual(status_alert({"alert": "AR TEST"}), "AR TEST")
        self.assertEqual(status_alert({"death_cause": "COMBAT"}), "LIVE TAPE COLLAPSE — COMBAT")

    def test_floor_text(self) -> None:
        self.assertEqual(floor_text({"floor_level": 2, "camera_y": 3.52}), "FLOOR 2 · Y 3.52m")

    def test_geometry_validation(self) -> None:
        self.assertTrue(valid_window_geometry("860x215+100+24"))
        self.assertTrue(valid_window_geometry("720x180-20+80"))
        self.assertFalse(valid_window_geometry("860x215"))
        self.assertFalse(valid_window_geometry("bad"))

    def test_preferences_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "native_stress_hud.json"
            payload = {"geometry": "860x215+100+24", "always_on_top": False}
            write_hud_preferences(path, payload)
            self.assertEqual(read_hud_preferences(path), payload)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)


if __name__ == "__main__":
    unittest.main()
