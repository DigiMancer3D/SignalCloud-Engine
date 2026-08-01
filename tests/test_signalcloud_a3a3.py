from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.asset_doctor.content_abi import (
    scan_content,
    write_asset_envelope,
    write_hot_reload_index,
)
from tools.asset_doctor.hot_reload_bridge import read_status_summary, stage_preview_reload
from tools.asset_doctor.pack_builder import build_pack
from tools.asset_doctor.pack_manager import inspect_pack, install_pack
from tools.asset_doctor.pcp3_reload_probe import MARKER_RELATIVE, toggle_marker
from tools.pcp3.io import encode_cloud
from tools.pcp3.model import PCPPoint


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA3A3Tests(unittest.TestCase):
    def test_current_content_is_clean_and_incomplete_placeholder_is_removed(self) -> None:
        report = scan_content(ROOT / "content")
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)
        self.assertFalse((ROOT / "content/pcp3_assets/environment_object/untitled_asset").exists())
        marker = ROOT / "content/pcp3_assets/environment_object/a3_preview_marker/a3_preview_marker.pcp3cloud"
        self.assertTrue(marker.is_file())

    def test_asset_doctor_rejects_missing_pcp3_cloud_companion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp) / "content"
            folder = content / "pcp3_assets/environment_object/missing"
            folder.mkdir(parents=True)
            project = folder / "missing.pcp3"
            project.write_text(json.dumps({
                "asset_id": "missing",
                "cloud_file": "missing.pcp3cloud",
                "cloud_sha256": "0" * 64,
                "point_count": 1,
            }), encoding="utf-8")
            write_asset_envelope(
                content, project,
                asset_id="pcp3.environment_object.missing",
                asset_type="pcp3_project",
                family="point_cloud",
                pack="legacy",
                hot_reload="authoring-only",
            )
            report = scan_content(content)
            self.assertTrue(any(issue.code == "pcp3.cloud-missing" for issue in report.issues))
            self.assertGreater(report.error_count, 0)

    def test_pack_inspection_and_atomic_install_preserve_future_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_project = base / "source"
            target_project = base / "target"
            asset_dir = source_project / "content/user/demo"
            asset_dir.mkdir(parents=True)
            source_asset = asset_dir / "future_light.slight"
            payload = {
                "schema_name": "signalcloud.light-set",
                "lights": [],
                "future_vendor_block": {"keep": [1, 2, 3]},
            }
            source_asset.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            write_asset_envelope(
                source_project / "content", source_asset,
                asset_id="user.demo.future-light",
                asset_type="light_set",
                family="lighting",
                pack="user.demo-pack",
                license_id="MIT",
                hot_reload="authoring-only",
            )
            built = build_pack(
                source_project,
                "content/user/demo",
                pack_id="user.demo-pack",
                display_name="Demo Pack",
                version="1.0.0",
                license_id="MIT",
            )
            (target_project / "content").mkdir(parents=True)
            inspected = inspect_pack(target_project, built.output_path)
            self.assertTrue(inspected.installable, inspected.findings)
            self.assertEqual(inspected.asset_count, 1)
            installed = install_pack(target_project, built.output_path)
            self.assertTrue(installed.receipt_path.is_file())
            installed_asset = installed.target_path / "demo/future_light.slight"
            self.assertEqual(json.loads(installed_asset.read_text())["future_vendor_block"], {"keep": [1, 2, 3]})
            report = scan_content(target_project / "content")
            self.assertEqual(report.error_count, 0)

    def test_pack_inspector_rejects_traversal_before_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "content").mkdir()
            archive = root / "bad.scpack.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", b"bad")
                bundle.writestr("PACK_MANIFEST.json", b"{}")
                bundle.writestr("PACK_SHA256SUMS.txt", b"")
            inspected = inspect_pack(root, archive)
            self.assertFalse(inspected.installable)
            self.assertTrue(any(item.code == "pack.unsafe-path" for item in inspected.findings))
            self.assertFalse((root.parent / "escape.txt").exists())

    def test_pcp3_protected_stage_records_companion_and_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "content/pcp3_assets/environment_object/demo"
            folder.mkdir(parents=True)
            cloud_bytes, cloud_hash = encode_cloud([
                PCPPoint(0.0, 0.0, 0.0, r=0.2, g=1.0, b=0.4),
                PCPPoint(0.2, 0.2, 0.0, r=0.2, g=1.0, b=0.4),
            ])
            cloud = folder / "demo.pcp3cloud"
            cloud.write_bytes(cloud_bytes)
            project = folder / "demo.pcp3"
            project_payload = {
                "asset_id": "demo",
                "cloud_file": cloud.name,
                "cloud_sha256": cloud_hash,
                "point_count": 2,
                "future": {"baseline": True},
            }
            project.write_text(json.dumps(project_payload, sort_keys=True) + "\n", encoding="utf-8")
            write_asset_envelope(
                root / "content", project,
                asset_id="pcp3.environment_object.demo",
                asset_type="pcp3_project",
                family="point_cloud",
                pack="legacy",
                hot_reload="authoring-only",
            )
            report = scan_content(root / "content")
            self.assertEqual(report.error_count, 0)
            write_hot_reload_index(
                report, root, root / "user_data/studio/hot_reload_candidates.udata"
            )
            project_payload["future"]["edited"] = "preserved"
            project.write_text(json.dumps(project_payload, sort_keys=True) + "\n", encoding="utf-8")
            result = stage_preview_reload(root)
            self.assertEqual(result.changed_pcp3_count, 1)
            self.assertEqual(result.invalid_count, 0)
            self.assertEqual(len(result.transaction_id), 16)
            summary = read_status_summary(root)
            self.assertEqual(summary.get("transaction_id"), result.transaction_id)
            self.assertEqual(int(summary.get("changed_pcp3_count", 0)), 1)
            staged = list((root / "user_data/studio/hot_reload/pcp3").glob("*.udata"))
            self.assertEqual(len(staged), 1)
            self.assertIn(cloud_hash, staged[0].read_text(encoding="utf-8"))

    def test_pcp3_reload_probe_can_toggle_repeatedly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_folder = ROOT / MARKER_RELATIVE.parent
            target_folder = root / MARKER_RELATIVE.parent
            shutil.copytree(source_folder, target_folder)
            report = scan_content(root / "content")
            self.assertEqual(report.error_count, 0)
            write_hot_reload_index(
                report, root, root / "user_data/studio/hot_reload_candidates.udata"
            )
            first_color, first_tx = toggle_marker(root)
            second_color, second_tx = toggle_marker(root)
            self.assertNotEqual(first_color, second_color)
            self.assertNotEqual(first_tx, second_tx)
            summary = read_status_summary(root)
            self.assertEqual(int(summary.get("changed_pcp3_count", 0)), 1)
            self.assertEqual(int(summary.get("invalid_count", 0)), 0)

    def test_studio_and_scripts_expose_pack_install_workflow(self) -> None:
        host = (ROOT / "tools/signalcloud_studio/host.py").read_text(encoding="utf-8")
        self.assertIn("open_pack_manager", host)
        self.assertIn("Inspect / install pack", host)
        inspect_script = ROOT / "scripts/inspect_content_pack.sh"
        install_script = ROOT / "scripts/install_content_pack.sh"
        self.assertTrue(inspect_script.is_file())
        self.assertTrue(install_script.is_file())
        self.assertIn('cd "$ROOT"', inspect_script.read_text(encoding="utf-8"))
        self.assertIn('PYTHONPATH="$ROOT', install_script.read_text(encoding="utf-8"))

    def test_native_game_declares_pcp3_reload_and_applied_receipt(self) -> None:
        source = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("changed_pcp3_projects", source)
        self.assertIn("hot_reload_applied.udata", source)
        self.assertIn("auto pcp3_assets =", source)
        self.assertIn("pcp3_assets = std::move(refreshed_assets)", source)
        self.assertIn("pcp3_interactions.reset()", source)


if __name__ == "__main__":
    unittest.main()
