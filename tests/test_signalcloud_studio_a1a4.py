from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.signalcloud_launcher import Launcher
from tools.signalcloud_studio.app import build_catalog, main
from tools.signalcloud_studio.documents import StudioDocumentContext
from tools.signalcloud_studio.host import StudioHostModel


class SignalCloudStudioA1A4Tests(unittest.TestCase):
    def test_launcher_opens_pcp3_without_native_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "scripts" / "launch_pcp3.sh"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/sh\n", encoding="utf-8")
            launcher = object.__new__(Launcher)
            launcher.root_path = root
            messages: list[str] = []
            launcher.write = messages.append
            with patch("tools.signalcloud_launcher.subprocess.Popen") as popen:
                Launcher.launch_pcp3(launcher)
            popen.assert_called_once_with([str(script)], cwd=root)
            self.assertIn("authoring-only mode", "".join(messages))

    def test_launcher_method_has_no_preview_build_gate(self) -> None:
        source = inspect.getsource(Launcher.launch_pcp3)
        self.assertNotIn("if not preview.exists", source)
        self.assertIn("authoring-only mode", source)

    def test_pcp3_shell_launcher_has_no_native_build_precondition(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "scripts" / "launch_pcp3.sh").read_text(encoding="utf-8")
        self.assertNotIn("exit 3", text)
        self.assertIn("authoring-only mode", text)
        self.assertIn("--tool pcp3", text)

    def test_default_cli_opens_studio_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("tools.signalcloud_studio.app.launch_host", return_value=0) as launch:
                self.assertEqual(main(argv=["--root", temp_dir]), 0)
            launch.assert_called_once_with(Path(temp_dir))

    def test_explicit_tool_still_bypasses_host(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("tools.signalcloud_studio.app.launch_tool", return_value=0) as launch:
                self.assertEqual(main(argv=["--root", temp_dir, "--tool", "pcp3"]), 0)
            launch.assert_called_once_with(Path(temp_dir), "pcp3", document=None)

    def test_catalog_exposes_dock_readiness_metadata(self) -> None:
        infos = build_catalog().infos()
        self.assertEqual({item.key for item in infos}, {"pcp3", "light-lab", "jitter-texture-lab", "universal-playbook-lab", "font-studio", "showcase-physics", "tupd-workbench"})
        self.assertTrue(all(item.category == "Authoring" for item in infos))
        self.assertTrue(all(item.standalone_ready for item in infos))
        self.assertTrue(all(not item.can_embed for item in infos))

    def test_host_model_lists_both_tools_and_shared_context(self) -> None:
        model = StudioHostModel(build_catalog())
        rows = model.rows()
        self.assertEqual({item.key for item in rows}, {"pcp3", "light-lab", "jitter-texture-lab", "universal-playbook-lab", "font-studio", "showcase-physics", "tupd-workbench"})
        self.assertTrue(all(item.state_text == "Standalone bridge" for item in rows))
        context = StudioDocumentContext(
            active_document="content/user/lights/hall.slight",
            owner_tool="light-lab",
            revision=4,
            dirty=True,
        )
        summary = model.context_summary(context)
        self.assertIn("hall.slight", summary)
        self.assertIn("revision 4", summary)
        self.assertIn("unsaved changes", summary)

    def test_control_panel_exposes_studio_and_native_repair(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "tools" / "signalcloud_launcher.py").read_text(encoding="utf-8")
        self.assertIn("SignalCloud Studio Hub", text)
        self.assertIn("Build / Repair Native", text)
        self.assertIn("def launch_studio", text)
        self.assertIn("def build_native_targets", text)


if __name__ == "__main__":
    unittest.main()
