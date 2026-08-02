from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.machine_profile_manager import status_text

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A1R1Tests(unittest.TestCase):
    def test_phase_marker_and_repair_document_exist(self) -> None:
        document = ROOT / "docs/alpha/A9A1R1_STRESS_FONT_AND_PROFILE_PROMOTION_REPAIR.md"
        self.assertTrue(document.is_file())
        combined = document.read_text(encoding="utf-8").lower()
        for phrase in (
            "stress scfont", "recovered signal void", "official + promote",
            "target-specific", "active profile target", "a9a2",
        ):
            self.assertIn(phrase, combined)

    def test_native_stress_loads_the_same_terminal_scfont_as_the_game(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn('engine/scfont/font_service.hpp', source)
        self.assertIn('content/core/fonts/terminal_00/Terminal_00.scfont', source)
        self.assertIn('stress_font_service.set_default("core.fonts.terminal_00")', source)
        self.assertIn('ar.set_font(stress_font_service.default_font())', source)
        self.assertIn('Stress SCFONT runtime:', source)

    def test_recovered_route_guard_event_does_not_reject_candidate(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn("recovered_void_entries", source)
        self.assertIn("result.signal_void_entries <= result.route_containment_corrections", source)
        self.assertNotIn(
            'result.failure == "ROUTE_DID_NOT_PROGRESS" || result.signal_void_entries > 0U',
            source,
        )
        self.assertIn("Validation gates: completed", source)
        self.assertIn("candidate.validation.route_pass", source)

    def test_game_bootstraps_window_target_from_active_profile(self) -> None:
        header = (ROOT / "engine/benchmark/machine_profile.hpp").read_text(encoding="utf-8")
        kernel = (ROOT / "engine/benchmark/machine_profile.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("MachineProfileTargetHint", header)
        self.assertIn("read_active_profile_target_hint", header + kernel + game)
        self.assertIn("profile_target_hint.width, profile_target_hint.height", game)
        self.assertIn("Machine profile target:", game)
        self.assertIn("bootstrapped from active profile", game)

    def test_profile_ui_exposes_clear_official_promotion_path(self) -> None:
        launcher = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        self.assertIn("A9a1r1 Machine Profile", launcher)
        self.assertIn('text="Official + Promote"', launcher)
        self.assertIn("def official_promote", launcher)
        self.assertIn('self.run_class.set("official")', launcher)
        self.assertIn('self.mode.set("all")', launcher)
        self.assertIn("Profiles are target-specific", launcher)

    def test_status_distinguishes_candidate_from_active_and_lists_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profiles = root / "user_data/machine_profiles"
            profiles.mkdir(parents=True)
            (profiles / "candidate.udata").write_text(
                '''@udata 1
[header]
schema_name: "signalcloud_machine_profile";
schema_major: 1;
ruleset_id: "signalcloud-alpha-a9-ruleset-1";
status: "candidate";
[fingerprint]
privacy_hash: "0123456789abcdef";
content_hash: "content";
resolution_width: 1920;
resolution_height: 1080;
target_fps: 90;
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
            text = status_text(root)
            self.assertIn("candidate.udata: CANDIDATE", text)
            self.assertIn("target 1920x1080 @ 90 FPS", text)
            self.assertIn("route PASS", text)
            self.assertIn("A candidate was found, but it has not been promoted", text)


if __name__ == "__main__":
    unittest.main()
