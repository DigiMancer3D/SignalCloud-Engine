from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.native_stress_hud import status_alert
from tools.native_stress_launcher import MODE_HELP

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A3Tests(unittest.TestCase):
    def test_phase_marker_rule_and_closure_document_exist(self) -> None:
        paths = (
            ROOT / "docs/alpha/A9A3_WORKLOAD_MEMORY_THERMAL_CLOSURE.md",
            ROOT / "content/core/rules/a9a3_workload_memory_thermal_closure.udata",
            ROOT / "content/core/rules/a9a3_workload_memory_thermal_closure.udata.asset.udata",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:3]).lower()
        for phrase in (
            "workload", "memory_guard_refusal", "thermal_data_unavailable",
            "thermal_guard", "official + promote", "a10",
        ):
            self.assertIn(phrase, combined)

    def test_native_stress_declares_workload_memory_and_thermal_contract(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        for token in (
            '--mode=', '--workload-ramps', '--no-workload-ramps',
            '--thermal-read', '--no-thermal-read', '--thermal-profile-fail', '--no-thermal-profile-fail',
            '--thermal-force-stop', '--no-thermal-force-stop',
            '--thermal-safe-c=', '--thermal-fail-c=', '--thermal-force-stop-c=',
            'MEMORY_GUARD_REFUSAL', 'THERMAL_FORCE_STOP',
            'WORKLOAD_RAMP_REPORT.md', 'SAFETY_GUARD_REPORT.md',
            'workload_axis', 'workload_operations', 'memory_safe_point_limit',
        ):
            self.assertIn(token, source)
        self.assertIn('read_linux_memory_snapshot', source)
        self.assertIn('read_linux_thermal_sample', source)
        self.assertIn('build_workload_ramps', source)

    def test_shared_safety_and_ramp_modules_are_built_and_tested(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        for token in (
            "engine/benchmark/stress_safety.cpp",
            "engine/benchmark/workload_ramp.cpp",
            "signalcloud_stress_safety_tests",
            "signalcloud_workload_ramp_tests",
        ):
            self.assertIn(token, cmake)
        for path in (
            ROOT / "engine/benchmark/stress_safety.hpp",
            ROOT / "engine/benchmark/stress_safety.cpp",
            ROOT / "engine/benchmark/workload_ramp.hpp",
            ROOT / "engine/benchmark/workload_ramp.cpp",
            ROOT / "tests/test_stress_safety.cpp",
            ROOT / "tests/test_workload_ramp.cpp",
        ):
            self.assertTrue(path.is_file(), path)

    def test_launcher_exposes_workload_and_optional_thermal_controls(self) -> None:
        source = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        self.assertIn("workload", MODE_HELP)
        for token in (
            "Include registry-driven feature workload ramps",
            "Read Linux thermal sensors (telemetry)",
            "Mark profile failed at the fail temperature",
            "Force stop after sustained force temperature",
            "--workload-ramps", "--thermal-read", "--thermal-profile-fail", "--thermal-force-stop",
            "self.workload_ramps.set(True)",
        ):
            self.assertIn(token, source)

    def test_hud_prioritizes_thermal_and_workload_alerts(self) -> None:
        self.assertIn("THERMAL FORCE THRESHOLD", status_alert({"thermal_state": "force-stop", "thermal_force_hold_seconds": 10}))
        self.assertEqual(status_alert({"thermal_state": "warning"}), "THERMAL ABOVE USER SAFE LEVEL")
        self.assertIn(
            "WORKLOAD RAMP",
            status_alert({"workload_axis": "playbook_evaluations", "workload_level": 16}),
        )

    def test_registry_builder_remains_private_and_deterministic(self) -> None:
        source = (ROOT / "tools/stress_workload_registry.py").read_text(encoding="utf-8")
        for token in ('"<PROJECT_ROOT>"', 'registry_sha256', 'feature_channels'):
            self.assertIn(token, source)
        self.assertNotIn("os.uname", source)

    def test_live_status_schema_includes_a9a3_evidence(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        for key in (
            'workload_axis', 'workload_level', 'workload_operations',
            'memory_available_mib', 'memory_allowed_mib',
            'memory_estimated_mib', 'memory_safe_point_limit',
            'thermal_available', 'thermal_peak_celsius', 'thermal_state',
        ):
            self.assertIn(key, source)


if __name__ == "__main__":
    unittest.main()
