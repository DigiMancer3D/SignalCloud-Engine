from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.machine_profile_manager import export_privacy_bundle, parse_udata
from tools.stress_workload_registry import build_registry

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A1Tests(unittest.TestCase):
    def test_phase_marker_policy_defaults_docs_and_envelopes_exist(self) -> None:
        paths = (
            ROOT / "docs/alpha/A9A1_MACHINE_PROFILE_FOUNDATION.md",
            ROOT / "config/machine_profile_policy.udata",
            ROOT / "config/stress_tiers.udata",
            ROOT / "content/core/benchmark/machine_profile_defaults.udata",
            ROOT / "content/core/benchmark/machine_profile_defaults.udata.asset.udata",
            ROOT / "content/core/rules/a9a1_machine_profile_foundation.udata",
            ROOT / "content/core/rules/a9a1_machine_profile_foundation.udata.asset.udata",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:6]).lower()
        for phrase in (
            "previous-known-good", "privacy", "conservative", "atomic", "stale",
            "quick", "standard", "official", "developer", "a9a2",
        ):
            self.assertIn(phrase, combined)

    def test_machine_profile_kernel_is_shared_by_game_and_native_stress(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        header = (ROOT / "engine/benchmark/machine_profile.hpp").read_text(encoding="utf-8")
        source = (ROOT / "engine/benchmark/machine_profile.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        stress = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn("engine/benchmark/machine_profile.cpp", cmake)
        self.assertIn("signalcloud_machine_profile_tests", cmake)
        for token in (
            "load_active_or_conservative", "promote_candidate_atomic",
            "previous_known_good", "make_machine_fingerprint",
        ):
            self.assertIn(token, header + source)
        self.assertIn("load_active_or_conservative", game)
        self.assertIn("--run-class=", stress)
        self.assertIn("promote_candidate_atomic", stress)
        self.assertIn("MACHINE_PROFILE_CANDIDATE.md", stress)

    def test_launchers_expose_run_classes_status_and_privacy_export(self) -> None:
        native = (ROOT / "tools/native_stress_launcher.py").read_text(encoding="utf-8")
        session = (ROOT / "tools/signalcloud_launcher.py").read_text(encoding="utf-8")
        for token in (
            "quick", "standard", "official", "developer", "Machine Profile",
            "Export Privacy-Safe Bundle", "Build Workload Registry", "--run-class",
        ):
            self.assertIn(token, native)
        self.assertIn('"profile"', session)
        self.assertIn("status_text", session)

    def test_workload_registry_is_dynamic_deterministic_and_private(self) -> None:
        first = build_registry(ROOT)
        second = build_registry(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first["project_root"], "<PROJECT_ROOT>")
        self.assertGreater(first["enabled_asset_count"], 0)
        self.assertFalse(first["warnings"])
        channels = first["feature_channels"]
        for name in (
            "lights", "materials", "sound_ripples", "playbook_evaluations",
            "tupd_test_objects", "scui_panels", "showcase_objects", "pcp3_assets",
            "font_glyph_workloads",
        ):
            self.assertIn(name, channels)
            self.assertGreater(channels[name], 0)
        serialized = json.dumps(first, sort_keys=True)
        self.assertNotIn(str(ROOT), serialized)
        self.assertNotIn("/home/", serialized)

    def test_privacy_bundle_whitelists_profile_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_dir = root / "user_data/machine_profiles"
            profile_dir.mkdir(parents=True)
            private_path = str(Path("/home") / "exampleuser" / "secret")
            (profile_dir / "active.udata").write_text(
                f"""@udata 1

[header]
schema_name: \"signalcloud_machine_profile\";
schema_major: 1;
ruleset_id: \"signalcloud-alpha-a9-ruleset-1\";
status: \"active\";
source_kind: \"native-stress\";
run_class: \"standard\";

[fingerprint]
privacy_hash: \"0123456789abcdef\";
content_hash: \"content-safe\";
gpu_class: \"integrated\";
resolution_width: 1280;
resolution_height: 720;
target_fps: 60;

[recommended]
environment_points: 8000000;
protected_fallback_points: 4000000;

[private_future]
ignored_path: \"{private_path}\";
""",
                encoding="utf-8",
            )
            output = export_privacy_bundle(root)
            self.assertTrue(output.is_file())
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertEqual(names, {"machine_profiles.json", "PROFILE_SUMMARY.txt", "PRIVACY_README.txt"})
                contents = "\n".join(archive.read(name).decode("utf-8") for name in names)
            self.assertNotIn("${HOME}", contents)
            self.assertNotIn(str(root), contents)
            payload = json.loads(zipfile.ZipFile(output).read("machine_profiles.json"))
            self.assertEqual(payload["project_root"], "<PROJECT_ROOT>")
            self.assertEqual(payload["profiles"]["active.udata"]["recommended"]["environment_points"], 8000000)

    def test_profile_parser_accepts_direct_and_wrapped_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.udata"
            path.write_text(
                '@udata 1\n[header]\nschema_name: {"value":"signalcloud_machine_profile"};\nschema_major: 1;\n',
                encoding="utf-8",
            )
            parsed = parse_udata(path)
            self.assertEqual(parsed["header"]["schema_name"], "signalcloud_machine_profile")
            self.assertEqual(parsed["header"]["schema_major"], 1)

    def test_content_tree_remains_asset_doctor_clean(self) -> None:
        report = scan_content(ROOT / "content")
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)


if __name__ == "__main__":
    unittest.main()
