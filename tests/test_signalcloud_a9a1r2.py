from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.machine_profile_manager import status_text
from tools.native_stress_launcher import (
    _decode_latest_result_pointer,
    _latest_result_directory,
)

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA9A1R2Tests(unittest.TestCase):
    def test_phase_marker_and_results_path_repair_document_exist(self) -> None:
        document = ROOT / "docs/alpha/A9A1R2_STRESS_RESULTS_PATH_AND_RECEIPT_REPAIR.md"
        self.assertTrue(document.is_file())
        combined = document.read_text(encoding="utf-8").lower()
        for phrase in (
            "quoted path", "latest-result pointer", "result folder", "promotion receipt", "a9a2",
        ):
            self.assertIn(phrase, combined)

    def test_native_writer_uses_plain_path_text_not_filesystem_quoted_streaming(self) -> None:
        source = (ROOT / "app/native_stress_main.cpp").read_text(encoding="utf-8")
        self.assertIn("latest << dir.string()", source)
        self.assertIn('"Engine-native stress results: " << dir.string()', source)
        self.assertNotIn("latest << dir <<", source)

    def test_legacy_quoted_pointer_with_spaces_is_decoded_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud path with spaces ") as directory:
            root = Path(directory)
            run = root / "reports/native_stress_runs/native_123"
            run.mkdir(parents=True)
            (run / "NATIVE_STRESS_REPORT.md").write_text("# report\n", encoding="utf-8")
            pointer = root / "reports/native_stress_latest_path.txt"
            pointer.write_text(f'"{run}"\n', encoding="utf-8")

            resolved, note = _latest_result_directory(root)
            self.assertEqual(resolved, run.resolve())
            self.assertIsNone(note)
            self.assertEqual(pointer.read_text(encoding="utf-8"), str(run.resolve()) + "\n")

    def test_stale_pointer_recovers_newest_valid_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "reports/native_stress_runs"
            older = runs / "native_100"
            newer = runs / "native_200"
            older.mkdir(parents=True)
            newer.mkdir(parents=True)
            (older / "NATIVE_STRESS_REPORT.md").write_text("old", encoding="utf-8")
            (newer / "NATIVE_STRESS_REPORT.md").write_text("new", encoding="utf-8")
            # Name is a deterministic tie-breaker if temporary-filesystem mtimes match.
            pointer = root / "reports/native_stress_latest_path.txt"
            pointer.write_text('"/missing/native_999"\n', encoding="utf-8")

            resolved, note = _latest_result_directory(root)
            self.assertEqual(resolved.name, "native_200")
            self.assertIn("repaired", note or "")
            self.assertEqual(pointer.read_text(encoding="utf-8"), str(resolved) + "\n")

    def test_pointer_cannot_escape_native_stress_report_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                _decode_latest_result_pointer(root, str(root / "user_data/machine_profiles"))

    def test_promotion_receipt_is_reported_as_receipt_not_unknown_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profiles = root / "user_data/machine_profiles"
            profiles.mkdir(parents=True)
            (profiles / "promotion_receipt.udata").write_text(
                '''@udata 1
[promotion]
status: "active";
ruleset_id: "signalcloud-alpha-a9-ruleset-1";
fingerprint: "aba75f8090daf856";
content_hash: "27c42af10f19e95f";
environment_points: 8000000;
previous_known_good_preserved: true;
[privacy]
contains_private_paths: false;
''',
                encoding="utf-8",
            )
            text = status_text(root)
            self.assertIn("promotion_receipt.udata: ACTIVE PROMOTION RECEIPT", text)
            self.assertIn("previous known good preserved: yes", text)
            self.assertNotIn("promotion_receipt.udata: UNKNOWN", text)


if __name__ == "__main__":
    unittest.main()
