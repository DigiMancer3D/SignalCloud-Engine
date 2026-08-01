from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Branch8R2RouteContainmentTests(unittest.TestCase):
    def test_native_stress_uses_route_guard_and_stable_full_map(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn("NativeStressRouteGuard", source)
        self.assertIn("restore_balanced_full_map_selection", source)
        self.assertIn("native_stress_route_containment_trace.csv", source)
        self.assertIn("FULL_MAP_SUBMISSION_RESTORE", source)
        self.assertNotIn("FULL_MAP_VISIBILITY_RECOVERY", source)
        self.assertNotIn("active_fallback", source)

    def test_full_map_stability_contract_exists(self) -> None:
        header = (ROOT / "engine/render/room_visibility.hpp").read_text(encoding="utf-8")
        implementation = (ROOT / "engine/render/room_visibility.cpp").read_text(encoding="utf-8")
        self.assertIn("full_map_selection_is_stable", header)
        self.assertIn("restore_balanced_full_map_selection", header)
        self.assertIn("for (const PointRange& resident : cloud.ranges())", implementation)
        self.assertIn("if (!represented) return false", implementation)
        self.assertIn("enforce_submitted_point_cap_balanced", implementation)

    def test_route_containment_coalesces_signal_void(self) -> None:
        header = (ROOT / "engine/benchmark/native_stress_route.hpp").read_text(encoding="utf-8")
        implementation = (ROOT / "engine/benchmark/native_stress_route.cpp").read_text(encoding="utf-8")
        self.assertIn("RouteContainmentResult", header)
        self.assertIn("NativeStressRouteGuard", header)
        self.assertIn("entered_void", implementation)
        self.assertIn("exited_void", implementation)
        self.assertIn("safe_position_in_area", implementation)

    def test_hud_reports_map_restore_and_route_guard(self) -> None:
        hud = (ROOT / "tools/native_stress_hud.py").read_text(encoding="utf-8")
        launcher = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        self.assertIn("MAP RESTORE", hud)
        self.assertIn("ROUTE GUARD", hud)
        self.assertIn("VOID ENTRY", hud)
        self.assertIn("route guard", launcher)


if __name__ == "__main__":
    unittest.main()
