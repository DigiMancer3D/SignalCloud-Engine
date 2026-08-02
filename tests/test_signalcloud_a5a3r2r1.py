from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup_dev_environment.sh"
CHECKER = ROOT / "tools" / "check_embedded_glsl.py"
RENDERER = ROOT / "engine" / "render" / "point_renderer.cpp"


class SignalCloudA5A3R2R1Tests(unittest.TestCase):
    def test_phase_marker_and_documentation_exist(self) -> None:
        self.assertTrue(
            (ROOT / "docs" / "alpha" / "A5A3R2R1_AUTOMATIC_GLSL_PREFLIGHT_REPAIR.md").is_file()
        )

    def test_setup_script_is_valid_bash(self) -> None:
        subprocess.run(["bash", "-n", str(SETUP)], cwd=ROOT, check=True)

    def test_setup_uses_single_path_glsl_checker_contract(self) -> None:
        text = SETUP.read_text(encoding="utf-8")
        expected = (
            '"$PYTHON" tools/check_embedded_glsl.py '
            'engine/render/point_renderer.cpp'
        )
        self.assertIn(expected, text)
        invocation_lines = [
            line.strip()
            for line in text.splitlines()
            if "tools/check_embedded_glsl.py" in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(invocation_lines, [expected])
        self.assertNotIn(
            "tools/check_embedded_glsl.py engine/render/point_renderer.cpp engine/render/room_visibility.cpp",
            text,
        )

    def test_real_checker_accepts_the_setup_invocation(self) -> None:
        if not CHECKER.is_file() or not RENDERER.is_file():
            self.skipTest("full installed project tree is required")
        completed = subprocess.run(
            [sys.executable, str(CHECKER), str(RENDERER.relative_to(ROOT))],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
