from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON_PATHS = ROOT / "scripts" / "common_paths.sh"


class SignalCloudA6A2R1Tests(unittest.TestCase):
    def run_helper(self, source_root: Path, build_dir: Path) -> subprocess.CompletedProcess[str]:
        command = (
            f'source "{COMMON_PATHS}"; '
            f'sc_prepare_cmake_build_dir "{source_root}" "{build_dir}" Ninja'
        )
        return subprocess.run(
            ["bash", "-c", command],
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def write_cache(build_dir: Path, source_root: Path, binary_dir: Path, generator: str = "Ninja") -> None:
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "CMakeCache.txt").write_text(
            "\n".join(
                [
                    f"CMAKE_HOME_DIRECTORY:INTERNAL={source_root}",
                    f"CMAKE_CACHEFILE_DIR:INTERNAL={binary_dir}",
                    f"CMAKE_GENERATOR:INTERNAL={generator}",
                    "",
                ]
            )
        )
        (build_dir / "keep.marker").write_text("generated")

    def test_relocated_source_cache_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            current_root = base / "current source"
            old_root = base / "old source"
            build_dir = current_root / "build"
            current_root.mkdir(parents=True)
            self.write_cache(build_dir, old_root, old_root / "build")

            result = self.run_helper(current_root, build_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(build_dir.exists())
            self.assertIn("source moved from", result.stdout)

    def test_relocated_binary_cache_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            current_root = base / "project"
            build_dir = current_root / "build"
            current_root.mkdir(parents=True)
            self.write_cache(build_dir, current_root, base / "former" / "build")

            result = self.run_helper(current_root, build_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(build_dir.exists())
            self.assertIn("build directory moved from", result.stdout)

    def test_matching_ninja_cache_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            current_root = Path(temp) / "project"
            build_dir = current_root / "build"
            current_root.mkdir(parents=True)
            self.write_cache(build_dir, current_root, build_dir)

            result = self.run_helper(current_root, build_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((build_dir / "keep.marker").is_file())
            self.assertEqual(result.stdout, "")

    def test_setup_and_build_entrypoints_use_shared_relocation_guard(self) -> None:
        scripts = [
            "setup_dev_environment.sh",
            "run_selftests.sh",
            "run_native_stress_quick_tests.sh",
            "run_pcp3_quick_tests.sh",
            "bake_illuminosity_diagnostics.sh",
        ]
        for script_name in scripts:
            content = (ROOT / "scripts" / script_name).read_text()
            self.assertIn("sc_prepare_cmake_build_dir", content, script_name)


if __name__ == "__main__":
    unittest.main()
