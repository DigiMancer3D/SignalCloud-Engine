from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.asset_doctor.content_abi import (
    list_quarantine_receipts,
    quarantine_invalid,
    repair_machine_paths,
    restore_quarantine_receipt,
    scan_content,
    write_hot_reload_index,
)
from tools.asset_doctor.hot_reload_bridge import read_status_summary, stage_preview_reload
from tools.asset_doctor.pack_builder import build_pack


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA3A2Tests(unittest.TestCase):
    def test_current_content_paths_are_portable(self) -> None:
        report = scan_content(ROOT / "content")
        path_warnings = [issue for issue in report.issues if issue.code == "asset.absolute-path"]
        self.assertEqual(path_warnings, [])
        project = ROOT / "content/pcp3_assets/environment_object/a3_preview_marker/a3_preview_marker.pcp3"
        payload = json.loads(project.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["metadata"]["last_project_path"],
            "content/pcp3_assets/environment_object/a3_preview_marker/a3_preview_marker.pcp3",
        )
        self.assertTrue(project.with_suffix(project.suffix + ".asset.udata").is_file())
        self.assertTrue(project.with_suffix(".pcp3cloud").is_file())

    def test_portable_repair_handles_json_and_embedded_udata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            content = Path(temp) / "content"
            content.mkdir()
            json_path = content / "user/demo.slight"
            json_path.parent.mkdir(parents=True)
            synthetic_home = Path("/home") / "exampleuser" / "SignalCloud"
            json_path.write_text(
                json.dumps({"path": str(synthetic_home / "content/user/demo.slight")}),
                encoding="utf-8",
            )
            udata = content / "user/demo.udata"
            udata.write_text(
                '@udata 1\n\n[future]\nmetadata: '
                + json.dumps({"path": str(synthetic_home / "user_data/demo.udata")})
                + ';\n',
                encoding="utf-8",
            )
            repaired = repair_machine_paths(content)
            self.assertEqual(set(repaired), {"user/demo.slight", "user/demo.udata"})
            self.assertIn("content/user/demo.slight", json_path.read_text(encoding="utf-8"))
            self.assertIn("user_data/demo.udata", udata.read_text(encoding="utf-8"))
            self.assertFalse(any(issue.code == "asset.absolute-path" for issue in scan_content(content).issues))

    def test_pack_builder_is_deterministic_and_data_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "content/user/demo"
            source.mkdir(parents=True)
            (source / "key.slight").write_text(
                json.dumps({"schema": "signalcloud_light_set_v1", "lights": [], "future": {"keep": True}}),
                encoding="utf-8",
            )
            first = build_pack(
                root, "content/user/demo", pack_id="demo.light-pack", display_name="Demo",
                version="1.0.0", license_id="CC0-1.0",
            )
            second = build_pack(
                root, "content/user/demo", pack_id="demo.light-pack", display_name="Demo",
                version="1.0.0", license_id="CC0-1.0",
            )
            self.assertEqual(first.sha256, second.sha256)
            with zipfile.ZipFile(first.output_path) as archive:
                names = set(archive.namelist())
                self.assertIn("PACK_MANIFEST.json", names)
                self.assertIn("PACK_SHA256SUMS.txt", names)
                self.assertIn("content/user/demo/key.slight", names)
                self.assertIn("content/user/demo/key.slight.asset.udata", names)
                self.assertFalse(any(name.endswith((".py", ".sh", ".exe")) for name in names))
                manifest = json.loads(archive.read("PACK_MANIFEST.json"))
                self.assertTrue(manifest["data_only"])
                self.assertEqual(manifest["asset_count"], 1)

    def test_pack_builder_rejects_executable_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "content/mods/demo"
            source.mkdir(parents=True)
            script = source / "payload.py"
            script.write_text("print('no')\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "executable content"):
                build_pack(
                    root, "content/mods/demo", pack_id="demo.bad-pack", display_name="Bad",
                    version="1.0.0", license_id="MIT",
                )

    def test_protected_stage_detects_changed_slight_and_scui(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            light = root / "content/user/lights/demo.slight"
            panel = root / "content/user/ui/demo.scui"
            light.parent.mkdir(parents=True)
            panel.parent.mkdir(parents=True)
            light.write_text(json.dumps({
                "lights": [{"scope": "local", "illuminosity_percent": 72, "radius": 10}],
                "day_night": {"day_illuminosity_percent": 95, "night_illuminosity_percent": 18, "time_of_day": 0.35},
            }), encoding="utf-8")
            panel.write_text(
                '@udata 1\n\n[panel]\nschema_name: "signalcloud.scui";\nschema_major: 1;\npanel_id: "demo.panel";\ntitle: "Demo";\n',
                encoding="utf-8",
            )
            report = scan_content(root / "content")
            write_hot_reload_index(report, root, root / "user_data/studio/hot_reload_candidates.udata")
            light.write_text(light.read_text(encoding="utf-8").replace('72', '84'), encoding="utf-8")
            panel.write_text(panel.read_text(encoding="utf-8") + '\n[state]\nvalue: 1;\n', encoding="utf-8")
            result = stage_preview_reload(root)
            self.assertEqual(result.changed_count, 2)
            self.assertEqual(result.invalid_count, 0)
            summary = read_status_summary(root)
            self.assertEqual(summary["changed_count"], 2)
            overlay = root / "user_data/studio/hot_reload/light_lab_preview_state.udata"
            self.assertIn("light_i: 84.0;", overlay.read_text(encoding="utf-8"))

    def test_quarantine_receipt_can_restore_user_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            content = Path(temp) / "content"
            asset = content / "user/broken.slight"
            asset.parent.mkdir(parents=True)
            asset.write_text("{broken", encoding="utf-8")
            report = scan_content(content)
            moved = quarantine_invalid(report, content)
            self.assertEqual(moved, ["user/broken.slight"])
            self.assertFalse(asset.exists())
            receipts = list_quarantine_receipts(content)
            self.assertEqual(len(receipts), 1)
            restored = restore_quarantine_receipt(content, receipts[0].receipt_path)
            self.assertEqual(restored, ["user/broken.slight"])
            self.assertTrue(asset.exists())
            self.assertTrue(list_quarantine_receipts(content)[0].restored)

    def test_export_and_managed_saves_emit_envelopes(self) -> None:
        io_source = (ROOT / "tools/pcp3/io.py").read_text(encoding="utf-8")
        binding_source = (ROOT / "tools/signalcloud_studio/scui/bindings.py").read_text(encoding="utf-8")
        codec_source = (ROOT / "tools/signalcloud_studio/scui/codec.py").read_text(encoding="utf-8")
        self.assertIn("portable_metadata", io_source)
        self.assertIn("write_asset_envelope", io_source)
        self.assertIn("write_asset_envelope", binding_source)
        self.assertIn("write_asset_envelope", codec_source)

    def test_studio_exposes_pack_builder_and_recovery_actions(self) -> None:
        host = (ROOT / "tools/signalcloud_studio/host.py").read_text(encoding="utf-8")
        doctor = (ROOT / "tools/signalcloud_studio/asset_doctor_panel.py").read_text(encoding="utf-8")
        self.assertIn("Open Pack Builder", host)
        self.assertIn("Repair portable paths", doctor)
        self.assertIn("Stage preview reload", doctor)
        self.assertIn("Restore newest", doctor)

    def test_native_game_exposes_f9_protected_reload(self) -> None:
        source = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("SDL_SCANCODE_F9", source)
        self.assertIn("HotReloadStatus::load", source)
        self.assertIn("PREVIEW RELOADED", source)
        self.assertIn("Protected preview reload is limited to safe rooms", source)


if __name__ == "__main__":
    unittest.main()
