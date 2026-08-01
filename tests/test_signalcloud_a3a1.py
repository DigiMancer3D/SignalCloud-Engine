from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import (
    quarantine_invalid,
    scan_content,
    write_hot_reload_index,
)
from tools.asset_doctor.manifest_builder import build_manifest


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA3A1Tests(unittest.TestCase):
    def test_current_content_has_no_asset_doctor_errors(self) -> None:
        report = scan_content(ROOT / "content")
        self.assertEqual(report.error_count, 0)
        self.assertGreaterEqual(report.valid_count, 70)

    def test_invalid_user_asset_is_quarantined_but_core_is_protected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            content = Path(temp) / "content"
            user = content / "user" / "lights" / "broken.slight"
            core = content / "core" / "lights" / "broken.slight"
            user.parent.mkdir(parents=True)
            core.parent.mkdir(parents=True)
            user.write_text("{broken", encoding="utf-8")
            core.write_text("{broken", encoding="utf-8")
            report = scan_content(content)
            self.assertEqual(report.error_count, 2)
            moved = quarantine_invalid(report, content)
            self.assertEqual(moved, ["user/lights/broken.slight"])
            self.assertFalse(user.exists())
            self.assertTrue(core.exists())
            self.assertTrue(any((content / "quarantine").rglob("broken.slight")))

    def test_duplicate_envelope_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            content = Path(temp) / "content"
            for name in ("a.slight", "b.slight"):
                path = content / "user" / "lights" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
                path.with_suffix(path.suffix + ".asset.udata").write_text(
                    '@udata 1\n\n[asset]\nasset_id: "same.asset";\nasset_type: "light_set";\n',
                    encoding="utf-8",
                )
            report = scan_content(content)
            self.assertTrue(any(issue.code == "asset.duplicate-id" for issue in report.issues))

    def test_hot_reload_index_contains_only_valid_authoring_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            light = root / "content" / "user" / "lights" / "demo.slight"
            save = root / "content" / "user" / "saves" / "normal.json"
            light.parent.mkdir(parents=True)
            save.parent.mkdir(parents=True)
            light.write_text("{}\n", encoding="utf-8")
            save.write_text("{}\n", encoding="utf-8")
            report = scan_content(root / "content")
            output = write_hot_reload_index(report, root, root / "user_data/studio/hot_reload_candidates.udata")
            text = output.read_text(encoding="utf-8")
            self.assertIn("demo.slight", text)
            self.assertNotIn("normal.json", text)
            self.assertIn('mode: "protected-authoring-only"', text)

    def test_manifest_excludes_quarantine_and_extended_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            content = Path(temp) / "content"
            good = content / "core" / "data" / "good.udata"
            bad = content / "quarantine" / "old" / "bad.udata"
            good.parent.mkdir(parents=True)
            bad.parent.mkdir(parents=True)
            good.write_text("[body]\nkind = good\n", encoding="utf-8")
            bad.write_text("bad", encoding="utf-8")
            (content / "manifest_v2.json").write_text("{}", encoding="utf-8")
            rows = build_manifest(content)
            self.assertEqual([row.relative_path for row in rows], ["core/data/good.udata"])

    def test_selector_confirm_routes_without_cycling(self) -> None:
        runtime = (ROOT / "engine/ui/scui_native_runtime.cpp").read_text(encoding="utf-8")
        game = (ROOT / "app/game_main.cpp").read_text(encoding="utf-8")
        self.assertIn("Confirm dispatches the current selection", runtime)
        self.assertIn('scui_event.command_id == "authoring.panel.select" ||', game)
        self.assertIn("PROJECT PANEL READY", game)

    def test_studio_exposes_asset_doctor(self) -> None:
        host = (ROOT / "tools/signalcloud_studio/host.py").read_text(encoding="utf-8")
        self.assertIn("Open Asset Doctor", host)
        self.assertIn("mount_asset_doctor_panel", host)

    def test_tk_smoke_is_isolated_from_user_overlay(self) -> None:
        smoke = (ROOT / "tests/scui_tk_smoke.py").read_text(encoding="utf-8")
        self.assertIn("TemporaryDirectory", smoke)
        self.assertIn("isolated_context", smoke)

    def test_selftest_runs_asset_doctor_and_has_failure_trap(self) -> None:
        script = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        self.assertIn("tools/asset_doctor/asset_doctor.py", script)
        self.assertIn("SignalCloud self-tests stopped", script)


if __name__ == "__main__":
    unittest.main()
