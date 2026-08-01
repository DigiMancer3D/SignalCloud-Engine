from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA10A2Tests(unittest.TestCase):
    def test_standalone_common_paths_use_xdg_owned_locations(self) -> None:
        script = ROOT / "scripts/common_paths.sh"
        text = script.read_text(encoding="utf-8")
        self.assertIn("standalone-public", text)
        self.assertIn("XDG_CACHE_HOME", text)
        self.assertIn("XDG_DATA_HOME", text)
        self.assertIn("signalcloud-engine/deps", text)
        self.assertIn("signalcloud-engine/envs", text)

    def test_release_scripts_and_github_community_files_exist(self) -> None:
        for rel in (
            "scripts/build_public_alpha_release.sh",
            "scripts/publish_github_alpha.sh",
            "docs/public/GITHUB_PUBLICATION_GUIDE.md",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/release.yml",
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_public_version_and_license_are_consistent(self) -> None:
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "v0.1.0-alpha.1")
        policy = json.loads((ROOT / "config/public_release_policy.json").read_text(encoding="utf-8"))
        self.assertEqual(policy["public_version"], "v0.1.0-alpha.1")
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text(encoding="utf-8"))
        self.assertIn("MIT", (ROOT / "PUBLIC_RELEASE_LICENSE_DECISION.md").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / "LICENSES/CC0-1.0.txt").stat().st_size > 5000)

    def test_active_tactical_map_source_is_not_in_legacy(self) -> None:
        self.assertFalse((ROOT / "legacy").exists())
        self.assertTrue((ROOT / "engine/ui/tactical_map_prototype.cpp").is_file())
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("engine/ui/tactical_map_prototype.cpp", cmake)
        self.assertNotIn("legacy/tactical_map_prototype.cpp", cmake)

    def test_release_shell_scripts_are_valid_bash(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts/build_public_alpha_release.sh"),
             str(ROOT / "scripts/publish_github_alpha.sh"),
             str(ROOT / "scripts/common_paths.sh"),
             str(ROOT / "scripts/setup_dev_environment.sh"),
             str(ROOT / "scripts/launch_game.sh")],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_standalone_layout_resolution_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud standalone ") as temp_name:
            temp = Path(temp_name)
            fake_root = temp / "SignalCloud-Engine"
            (fake_root / "scripts").mkdir(parents=True)
            (fake_root / "scripts/common_paths.sh").write_text(
                (ROOT / "scripts/common_paths.sh").read_text(encoding="utf-8"), encoding="utf-8"
            )
            command = (
                'source "$1/scripts/common_paths.sh"; '
                'printf "%s\\n%s\\n%s\\n" "$SC_LAYOUT_MODE" "$SC_SHARED_DEPS" "$SC_SHARED_ENVS"'
            )
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(fake_root)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                env={"HOME": str(temp / "home"), "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = result.stdout.splitlines()
            self.assertEqual(lines[0], "standalone-public")
            self.assertIn("signalcloud-engine/deps", lines[1])
            self.assertIn("signalcloud-engine/envs", lines[2])


if __name__ == "__main__":
    unittest.main()
