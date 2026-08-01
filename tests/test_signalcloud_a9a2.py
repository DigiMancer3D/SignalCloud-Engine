from __future__ import annotations

import csv
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from tools.machine_profile_manager import status_text
from tools.native_stress_watchdog import (
    FINAL_REPORT_NAME,
    HEARTBEAT_NAME,
    JOURNAL_NAME,
    RECOVERY_NAME,
    STATE_NAME,
    _parse_args,
    heartbeat_is_stale,
    recover_orphaned_sessions,
    recover_partial_report,
)

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A2Tests(unittest.TestCase):
    def test_phase_marker_rule_policy_and_document_exist(self) -> None:
        paths = (
            ROOT / "ALPHA_A9A2_INSTALLED.txt",
            ROOT / "docs/alpha/A9A2_WATCHDOG_AND_INTERRUPTED_RUN_RECOVERY.md",
            ROOT / "config/native_stress_watchdog.json",
            ROOT / "content/core/rules/a9a2_watchdog_interrupted_recovery.udata",
            ROOT / "content/core/rules/a9a2_watchdog_interrupted_recovery.udata.asset.udata",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:4]).lower()
        for phrase in (
            "parent watchdog", "heartbeat", "stage journal", "partial report",
            "previous-known-good", "clean stop", "hard abort", "a9a3",
        ):
            self.assertIn(phrase, combined)

    def test_native_child_declares_session_journal_heartbeat_and_nonpromotion_boundary(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        for token in (
            "--session-dir=", "--stop-file=", "--heartbeat-file=",
            "STAGE_JOURNAL.csv", "WATCHDOG_HEARTBEAT.json", "RUN_STATE.json",
            "USER_HARD_ABORT", "USER_CLEAN_STOP_FILE",
            "run_completed && (options.profile_promotion",
            "INTERRUPTED — NOT ELIGIBLE FOR PROFILE PROMOTION",
        ):
            self.assertIn(token, source)
        self.assertIn("append_stage_journal(options, results.back())", source)
        self.assertIn("return hard_abort ? 11 : 10", source)

    def test_launcher_routes_every_native_run_through_watchdog(self) -> None:
        launcher = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        cli = (ROOT / "scripts/launch_native_stress.sh").read_text(encoding="utf-8")
        for token in (
            "native_stress_watchdog.py", "watchdog_command", "Force Abort + Recover",
            "Recover interrupted runs", "CLEAN_REQUEST", "HARD_REQUEST",
        ):
            self.assertIn(token, launcher)
        self.assertIn("native_stress_watchdog.py", cli)
        self.assertNotIn("self.process.terminate()", launcher)

    def test_watchdog_cli_keeps_policy_options_out_of_child_command(self) -> None:
        args = _parse_args([
            "/tmp/SignalCloud Project With Spaces",
            "--heartbeat-timeout=2",
            "--startup-timeout=5",
            "--clean-stop-grace=1",
            "--",
            "python",
            "fake_child.py",
            "--mode=game",
        ])
        self.assertEqual(args.root, Path("/tmp/SignalCloud Project With Spaces"))
        self.assertEqual(args.heartbeat_timeout, 2.0)
        self.assertEqual(args.startup_timeout, 5.0)
        self.assertEqual(args.clean_stop_grace, 1.0)
        self.assertEqual(args.child, ["python", "fake_child.py", "--mode=game"])

    def test_partial_recovery_preserves_profiles_and_stage_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A9a2 recovery ") as directory:
            root = Path(directory)
            session = root / "reports/native_stress_runs/native_100"
            session.mkdir(parents=True)
            profile_dir = root / "user_data/machine_profiles"
            profile_dir.mkdir(parents=True)
            active = profile_dir / "active.udata"
            active.write_text("ACTIVE-SENTINEL\n", encoding="utf-8")
            (session / STATE_NAME).write_text(
                json.dumps({"state": "running", "current_stage": "Cloud 8M"}), encoding="utf-8"
            )
            fieldnames = [
                "mode", "stage", "stage_kind", "points", "entities", "scanner", "seconds",
                "avg_fps", "highest_fps", "lowest_fps", "one_percent_low", "target_seconds",
                "longest_target_seconds", "low_seconds", "longest_low_seconds", "high_seconds",
                "longest_high_seconds", "generation_ms", "peak_gpu_ms", "resident_points",
                "submitted_points_peak", "renderer_submitted_points_peak", "submitted_rooms_peak",
                "preview_rooms_peak", "trimmed_points_peak", "full_map_recoveries",
                "route_containment_corrections", "signal_void_entries", "zones_seen",
                "route_distance_start", "route_distance_end", "route_distance_delta",
                "full_siren_pulses", "death_cause", "passed", "failure",
            ]
            with (session / JOURNAL_NAME).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({
                    "mode": "cloud", "stage": "Real room cloud 8000000", "stage_kind": "benchmark",
                    "points": "8000000", "entities": "0", "avg_fps": "60.2",
                    "route_distance_delta": "12.0", "passed": "1", "failure": "",
                })
                writer.writerow({
                    "mode": "cloud", "stage": "Real room cloud 12000000", "stage_kind": "benchmark",
                    "points": "12000000", "entities": "0", "avg_fps": "41.0",
                    "route_distance_delta": "12.0", "passed": "0", "failure": "FPS_BELOW_80_PERCENT_TARGET",
                })
            (session / "LIVE_SNAPSHOT.json").write_text(
                json.dumps({"stage": "Real room cloud 12000000", "location": "Hum Hall"}), encoding="utf-8"
            )

            report = recover_partial_report(root, session, "WATCHDOG_HEARTBEAT_TIMEOUT", child_exit_code=-15)
            self.assertEqual(active.read_text(encoding="utf-8"), "ACTIVE-SENTINEL\n")
            self.assertTrue(report.is_file())
            text = report.read_text(encoding="utf-8")
            self.assertIn("INTERRUPTED", text)
            self.assertIn("NOT ELIGIBLE FOR PROFILE PROMOTION", text)
            self.assertIn("Real room cloud 8000000", text)
            self.assertIn("WATCHDOG_HEARTBEAT_TIMEOUT", text)
            receipt = json.loads((session / RECOVERY_NAME).read_text(encoding="utf-8"))
            self.assertFalse(receipt["profile_promotion_allowed"])
            self.assertFalse(receipt["profiles_modified"])
            pointer = root / "reports/native_stress_latest_path.txt"
            self.assertEqual(pointer.read_text(encoding="utf-8"), str(session.resolve()) + "\n")

    def test_orphaned_running_session_is_recovered_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = root / "reports/native_stress_runs/native_orphan"
            session.mkdir(parents=True)
            (session / STATE_NAME).write_text(json.dumps({"state": "running"}), encoding="utf-8")
            old = time.time() - 120.0
            os.utime(session / STATE_NAME, (old, old))
            recovered = recover_orphaned_sessions(root, stale_after=30.0)
            self.assertEqual(recovered, [session])
            self.assertTrue((session / FINAL_REPORT_NAME).is_file())
            self.assertEqual(recover_orphaned_sessions(root, stale_after=0.0), [])

    def test_heartbeat_staleness_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / HEARTBEAT_NAME
            heartbeat.write_text("{}", encoding="utf-8")
            stamp = time.time() - 4.0
            os.utime(heartbeat, (stamp, stamp))
            self.assertFalse(heartbeat_is_stale(heartbeat, now=stamp + 7.0, timeout=8.0))
            self.assertTrue(heartbeat_is_stale(heartbeat, now=stamp + 9.0, timeout=8.0))

    def test_successful_profile_lists_exploratory_limits_not_gate_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profiles = root / "user_data/machine_profiles"
            profiles.mkdir(parents=True)
            (profiles / "active.udata").write_text(
                '''@udata 1
[header]
schema_name: "signalcloud_machine_profile";
schema_major: 1;
ruleset_id: "signalcloud-alpha-a9-ruleset-1";
status: "active";
[fingerprint]
privacy_hash: "0123456789abcdef";
content_hash: "content";
resolution_width: 1920;
resolution_height: 1080;
target_fps: 60;
[recommended]
environment_points: 8000000;
protected_fallback_points: 4000000;
[validation]
completed: true;
route_pass: true;
frame_pacing_pass: true;
memory_guard_pass: true;
content_hash_pass: true;
passed_stages: 30;
failed_stages: 2;
''',
                encoding="utf-8",
            )
            text = status_text(root)
            self.assertIn("30 passed / 2 exploratory limits", text)
            self.assertNotIn("30 passed / 2 failed", text)


if __name__ == "__main__":
    unittest.main()
