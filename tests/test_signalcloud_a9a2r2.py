from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.machine_profile_manager import machine_profile_content_hash, status_text

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A2R2Tests(unittest.TestCase):
    def test_phase_marker_document_rule_and_next_boundary_exist(self) -> None:
        paths = (
            ROOT / "ALPHA_A9A2R2_INSTALLED.txt",
            ROOT / "docs/alpha/A9A2R2_MANIFEST_SIGNATURE_PARITY_REPAIR.md",
            ROOT / "content/core/rules/a9a2r2_manifest_signature_parity_repair.udata",
            ROOT / "content/core/rules/a9a2r2_manifest_signature_parity_repair.udata.asset.udata",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:3]).lower()
        for phrase in ("crlf", "canonical", "official + promote", "a9a3", "thermal"):
            self.assertIn(phrase, combined)

    def test_native_hash_normalizes_record_endings_and_pins_parity(self) -> None:
        source = (ROOT / "engine/benchmark/machine_profile.cpp").read_text(encoding="utf-8")
        test = (ROOT / "tests/test_machine_profile.cpp").read_text(encoding="utf-8")
        self.assertIn("strip_record_ending", source)
        self.assertIn("record.back() == '\\r'", source)
        self.assertEqual(source.count("strip_record_ending("), 2)
        self.assertIn("4dd3bf2665d2d580", test)
        self.assertIn("\\r\\n", test)

    def test_python_hash_is_newline_format_independent(self) -> None:
        header = "asset_id,asset_type,family,pack,relative_path,size_bytes,sha256,modified_ns,enabled"
        rows = (
            "surface,materials,wall,core,core/materials/wall.jmap,10,aaa,100,true",
            "phase,rules,phase,core,core/rules/phase.udata,20,bbb,100,true",
        )
        with tempfile.TemporaryDirectory(prefix="SignalCloud A9a2r2 hash parity ") as directory:
            root = Path(directory)
            (root / "content").mkdir()
            manifest = root / "content/manifest.csv"
            manifest.write_bytes((header + "\n" + "\n".join(rows) + "\n").encode("utf-8"))
            lf_hash = machine_profile_content_hash(root)
            manifest.write_bytes((header + "\r\n" + "\r\n".join(rows) + "\r\n").encode("utf-8"))
            crlf_hash = machine_profile_content_hash(root)
            self.assertEqual(lf_hash, "4dd3bf2665d2d580")
            self.assertEqual(crlf_hash, lf_hash)

    def test_current_profile_status_is_not_marked_for_revalidation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A9a2r2 current status ") as directory:
            root = Path(directory)
            (root / "content").mkdir(parents=True)
            (root / "content/manifest.csv").write_bytes(
                b"asset_id,asset_type,family,pack,relative_path,size_bytes,sha256,modified_ns,enabled\r\n"
                b"surface,materials,wall,core,core/materials/wall.jmap,10,aaa,100,true\r\n"
                b"phase,rules,phase,core,core/rules/phase.udata,20,bbb,100,true\r\n"
            )
            content_hash = machine_profile_content_hash(root)
            profiles = root / "user_data/machine_profiles"
            profiles.mkdir(parents=True)
            (profiles / "active.udata").write_text(
                f'''@udata 1
[header]
schema_name: "signalcloud_machine_profile";
schema_major: 1;
ruleset_id: "signalcloud-alpha-a9-ruleset-1";
status: "active";
[fingerprint]
privacy_hash: "0123456789abcdef";
content_hash: "{content_hash}";
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
            text = status_text(root)
            self.assertIn("active.udata: ACTIVE |", text)
            self.assertNotIn("ACTIVE (REVALIDATION REQUIRED)", text)
            self.assertNotIn("will be rejected by the game", text)


if __name__ == "__main__":
    unittest.main()
