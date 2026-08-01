from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.machine_profile_manager import machine_profile_content_hash, status_text
from tools.native_stress_watchdog import (
    FINAL_REPORT_NAME,
    JOURNAL_NAME,
    RECOVERY_NAME,
    STATE_NAME,
    recover_partial_report,
)

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A2R1Tests(unittest.TestCase):
    def test_phase_marker_rule_and_repair_document_exist(self) -> None:
        paths = (
            ROOT / "ALPHA_A9A2R1_INSTALLED.txt",
            ROOT / "docs/alpha/A9A2R1_BUILD_HYGIENE_PROFILE_SIGNATURE_REPAIR.md",
            ROOT / "content/core/rules/a9a2r1_build_hygiene_profile_signature_repair.udata",
            ROOT / "content/core/rules/a9a2r1_build_hygiene_profile_signature_repair.udata.asset.udata",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:3]).lower()
        for phrase in (
            "python", "stage journal", "hard abort", "machine-profile",
            "modified_ns", "official + promote", "a9a3",
        ):
            self.assertIn(phrase, combined)

    def test_explicit_python_compile_uses_external_cache(self) -> None:
        for relative in (
            "scripts/run_selftests.sh",
            "scripts/run_native_stress_quick_tests.sh",
            "scripts/run_pcp3_quick_tests.sh",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("PYTHONPYCACHEPREFIX", text, relative)
            self.assertIn("mktemp -d", text, relative)
            self.assertIn("rm -rf", text, relative)
        full = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        self.assertIn("find \"$ROOT\" -type d -name __pycache__", full)

    def test_machine_profile_hash_is_stable_and_used_by_both_consumers(self) -> None:
        header = (ROOT / "engine/benchmark/machine_profile.hpp").read_text(encoding="utf-8")
        kernel = (ROOT / "engine/benchmark/machine_profile.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        stress = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        token = "hash_machine_profile_content_manifest"
        self.assertIn(token, header)
        self.assertIn(token, kernel)
        self.assertIn('lower(fields[*asset_type]) == "rules"', kernel)
        self.assertIn(token, game)
        self.assertIn(token, stress)
        self.assertNotIn('hash_file_privacy_safe(options.root / "content/manifest.csv")', game + stress)

    def test_status_marks_legacy_profile_for_revalidation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A9a2r1 profile status ") as directory:
            root = Path(directory)
            (root / "content").mkdir(parents=True)
            (root / "content/manifest.csv").write_text(
                "asset_id,asset_type,family,pack,relative_path,size_bytes,sha256,modified_ns,enabled\n"
                "surface,materials,wall,core,core/materials/wall.jmap,10,aaa,100,true\n"
                "phase,rules,phase,core,core/rules/phase.udata,20,bbb,100,true\n",
                encoding="utf-8",
            )
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
content_hash: "legacy-raw-hash";
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
passed_stages: 5;
failed_stages: 0;
''',
                encoding="utf-8",
            )
            self.assertEqual(len(machine_profile_content_hash(root)), 16)
            text = status_text(root)
            self.assertIn("ACTIVE (REVALIDATION REQUIRED)", text)
            self.assertIn("will be rejected by the game", text)
            self.assertIn("Official + Promote", text)

    def test_release_machine_profile_test_has_no_assert_only_checks(self) -> None:
        test = (ROOT / "tests/test_machine_profile.cpp").read_text(encoding="utf-8")
        self.assertIn("#define CHECK", test)
        self.assertNotIn("assert(", test)
        self.assertIn("hash_machine_profile_content_manifest", test)

    def test_stage_journal_is_initialized_before_running_state(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        reset = source.index("reset_stage_journal(options);")
        starting = source.index('write_run_state(options, "starting"')
        self.assertLess(reset, starting)
        self.assertEqual(source.count("reset_stage_journal(options);"), 1)

    def test_existing_hard_abort_report_is_reconciled_and_all_rows_survive(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A9a2r1 hard abort ") as directory:
            root = Path(directory)
            session = root / "reports/native_stress_runs/native_hard_abort"
            session.mkdir(parents=True)
            (session / STATE_NAME).write_text(
                json.dumps({"state": "running", "current_stage": "Systems 2"}), encoding="utf-8"
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
                writer.writerow({"mode": "game", "stage": "Systems 1", "points": "8000000", "entities": "1", "avg_fps": "90", "route_distance_delta": "30", "passed": "1"})
                writer.writerow({"mode": "game", "stage": "Systems 2", "points": "8000000", "entities": "2", "avg_fps": "80", "route_distance_delta": "30", "passed": "1"})
            report = session / FINAL_REPORT_NAME
            report.write_text(
                "# SignalCloud Engine-Native Stress Report\n\n"
                "- Run status: **INTERRUPTED — NOT ELIGIBLE FOR PROFILE PROMOTION**\n"
                "- Completion reason: `WINDOW_CLOSE_CLEAN_STOP`\n",
                encoding="utf-8",
            )

            recover_partial_report(root, session, "USER_HARD_ABORT", child_exit_code=11)
            text = report.read_text(encoding="utf-8")
            self.assertIn("Completion reason: `USER_HARD_ABORT`", text)
            self.assertIn("Watchdog recovery reason: `USER_HARD_ABORT`", text)
            receipt = json.loads((session / RECOVERY_NAME).read_text(encoding="utf-8"))
            self.assertEqual(receipt["completed_stage_rows"], 2)
            self.assertFalse(receipt["profile_promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
