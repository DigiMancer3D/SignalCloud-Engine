from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A3R1Tests(unittest.TestCase):
    def test_phase_marker_rule_and_repair_documents_exist(self) -> None:
        paths = (
            ROOT / "ALPHA_A9A3R1_INSTALLED.txt",
            ROOT / "docs/alpha/A9A3R1_THERMAL_AUTHORITY_BENCHMARK_CONTINUITY.md",
            ROOT / "content/core/rules/a9a3r1_thermal_authority_benchmark_continuity.udata",
            ROOT / "content/core/rules/a9a3r1_thermal_authority_benchmark_continuity.udata.asset.udata",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:4]).lower()
        for phrase in ("processor-gpu", "sensor doctor", "88%", "91%", "97%", "wall timer"):
            self.assertIn(phrase, combined)

    def test_official_promote_respects_user_thermal_authority(self) -> None:
        source = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        start = source.index("    def official_promote")
        end = source.index("    def quick_validation", start)
        method = source[start:end]
        self.assertIn("thermal fail/force-stop authority remains exactly as selected", method)
        self.assertNotIn("self.thermal_profile_fail.set(True)", method)
        self.assertNotIn("self.thermal_force_stop.set(True)", method)
        for token in (
            "--thermal-profile-fail", "--thermal-force-stop",
            "--thermal-sensor-policy", "--thermal-safe-c", "--thermal-fail-c",
            "--thermal-force-stop-c", "--thermal-force-hold-seconds",
        ):
            self.assertIn(token, source)

    def test_launcher_exposes_requested_resource_envelope_and_sensor_doctor(self) -> None:
        source = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        for token in (
            'self.max_ram = tk.StringVar(value="88")',
            'self.cpu_advisory = tk.StringVar(value="91")',
            'self.gpu_advisory = tk.StringVar(value="97")',
            'self.thermal_profile_fail = tk.BooleanVar(value=False)',
            'self.thermal_force_stop = tk.BooleanVar(value=False)',
            "Thermal Sensor Doctor", "SELECTED", "OBSERVED",
        ):
            self.assertIn(token, source)

    def test_wall_timer_is_frozen_when_process_finishes(self) -> None:
        source = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        for token in (
            "self.hud_wall_elapsed", "self.hud_wall_finished",
            "def _hud_wall_seconds", "def _finish_hud_run",
            'self.last_live_data["wall_timer_stopped"] = True',
        ):
            self.assertIn(token, source)
        completion = source[source.index("        if self.process and self.process.poll() is not None:"):]
        self.assertIn("self._finish_hud_run", completion)

    def test_native_thermal_policy_filters_non_processor_sensors(self) -> None:
        source = (ROOT / "engine/benchmark/stress_safety.cpp").read_text(encoding="utf-8")
        for token in (
            '"nvme"', '"battery"', '"pch"', '"coretemp"', '"amdgpu"',
            "selected_sensor_count", "observed_maximum_celsius",
        ):
            self.assertIn(token, source)
        native = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn("A9a3r1 never refuses a stage from a single starting temperature sample", native)
        self.assertIn("thermal_force_hold_seconds", native)
        self.assertIn("read_linux_cpu_times", native)
        self.assertIn("gpu_frame_budget_peak_percent", native)

    def test_default_config_is_observational_not_force_stopping(self) -> None:
        import json
        payload = json.loads((ROOT / "config/native_stress_gui.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["max_ram"], "88")
        self.assertEqual(payload["cpu_advisory"], "91")
        self.assertEqual(payload["gpu_advisory"], "97")
        self.assertEqual(payload["thermal_sensor_policy"], "processor-gpu")
        self.assertTrue(payload["thermal_read"])
        self.assertFalse(payload["thermal_profile_fail"])
        self.assertFalse(payload["thermal_force_stop"])


if __name__ == "__main__":
    unittest.main()
