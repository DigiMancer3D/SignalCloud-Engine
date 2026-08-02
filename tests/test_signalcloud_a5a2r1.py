from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class SignalCloudA5A2R1Tests(unittest.TestCase):
    def test_setup_resolves_python_before_first_use(self) -> None:
        script = (ROOT / "scripts/setup_dev_environment.sh").read_text()
        assignment = script.index('PYTHON="$SC_PYTHON"')
        first_use = script.index('"$PYTHON" tools/check_cpp_literals.py')
        self.assertLess(assignment, first_use)
        self.assertIn('PYTHON="$(command -v python3)"', script)
        self.assertNotIn('"$SC_PYTHON" tools/asset_doctor', script)

    def test_setup_runs_with_python_unset_under_nounset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            signalcloud_root = base / "SignalCloud Engine"
            project = (
                signalcloud_root
                / "Almond Signal: Live Tape"
                / "SignalCloud_Test_Alpha_A5a2r1"
            )
            scripts = project / "scripts"
            scripts.mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/setup_dev_environment.sh", scripts)
            shutil.copy2(ROOT / "scripts/common_paths.sh", scripts)
            shutil.copy2(ROOT / "scripts/build_core.sh", scripts)

            for name in (
                "compile_illuminosity_runtime.sh",
                "compile_material_runtime.sh",
                "compile_audio_interference_runtime.sh",
                "compile_playbook_runtime.sh",
                "repair_user_light_envelopes.sh",
            ):
                _write_executable(scripts / name, "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")

            stub_bin = base / "stub-bin"
            log = base / "python-calls.log"
            _write_executable(
                stub_bin / "dpkg-query",
                "#!/usr/bin/env bash\nprintf 'install ok installed'\n",
            )
            _write_executable(
                stub_bin / "cmake",
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "--build" ]]; then
  dir="${2:-build}"
  mkdir -p "$dir"
  for exe in almond_signal_live_tape almond_signal_native_stress almond_signal_pcp_preview almond_signal_showcase almond_signal_tupd_preview; do
    : > "$dir/$exe"
    chmod +x "$dir/$exe"
  done
fi
exit 0
""",
            )
            for name in ("python3", "c++", "tar", "ninja"):
                _write_executable(stub_bin / name, "#!/usr/bin/env bash\nexit 0\n")

            shared_python = signalcloud_root / ".signalcloud_envs/tools-py3/bin/python"
            _write_executable(
                shared_python,
                f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {str(log)!r}\nexit 0\n",
            )
            sdl_config = signalcloud_root / ".signalcloud_shared_deps/sdl3-install/lib/cmake/SDL3/SDL3Config.cmake"
            sdl_config.parent.mkdir(parents=True)
            sdl_config.write_text("# test SDL config\n")

            env = os.environ.copy()
            env.pop("PYTHON", None)
            env["PATH"] = f"{stub_bin}:{env.get('PATH', '')}"
            env["HOME"] = str(base / "home")
            env["XDG_DATA_HOME"] = str(base / "xdg")
            result = subprocess.run(
                ["bash", str(scripts / "setup_dev_environment.sh")],
                cwd=project,
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("environment is ready", result.stdout)
            calls = log.read_text()
            self.assertIn("tools/check_cpp_literals.py", calls)
            self.assertIn("tools/check_embedded_glsl.py", calls)
            self.assertIn("tools/asset_doctor/asset_doctor.py", calls)


if __name__ == "__main__":
    unittest.main()
