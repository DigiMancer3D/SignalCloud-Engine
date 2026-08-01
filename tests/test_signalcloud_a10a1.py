from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.public_release_audit import (
    build_deterministic_archive,
    build_deterministic_zip,
    prepare_public_stage,
)

ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA10ReleaseTests(unittest.TestCase):
    def _write_required_docs(self, source: Path, *, include_license: bool = True) -> None:
        for name in (
            "README.md", "INSTALL.md", "CHANGELOG.md", "RELEASE_NOTES_v0.1.0-alpha.1.md",
            "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "THIRD_PARTY_NOTICES.md",
            "PUBLIC_RELEASE_LICENSE_DECISION.md",
        ):
            (source / name).write_text(f"# {name}\n", encoding="utf-8")
        if include_license:
            (source / "LICENSE").write_text("MIT License\n", encoding="utf-8")
            (source / "LICENSES").mkdir(exist_ok=True)
            (source / "LICENSES/CC0-1.0.txt").write_text("CC0\n", encoding="utf-8")

    def test_phase_markers_policy_documents_and_scripts_exist(self) -> None:
        paths = (
            ROOT / "ALPHA_A10A1_INSTALLED.txt",
            ROOT / "ALPHA_A10A2_INSTALLED.txt",
            ROOT / "docs/alpha/A10A1_PUBLIC_SOURCE_AUDIT_RELEASE_STAGING.md",
            ROOT / "docs/alpha/A10A2_PUBLIC_ALPHA_RELEASE_CLOSURE.md",
            ROOT / "docs/developer/PUBLIC_RELEASE_AUDIT_TOOL.md",
            ROOT / "docs/public/PUBLIC_SOURCE_RELEASE_CHECKLIST.md",
            ROOT / "docs/public/GITHUB_PUBLICATION_GUIDE.md",
            ROOT / "config/public_release_policy.json",
            ROOT / "tools/public_release_audit.py",
            ROOT / "scripts/audit_public_source.sh",
            ROOT / "scripts/build_public_alpha_release.sh",
            ROOT / "scripts/publish_github_alpha.sh",
            ROOT / "LICENSE",
            ROOT / "LICENSES/CC0-1.0.txt",
            ROOT / "RELEASE_NOTES_v0.1.0-alpha.1.md",
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths[:9]).lower()
        for phrase in ("a10a1", "a10a2", "public", "deterministic", "license", "v0.1.0-alpha.1"):
            self.assertIn(phrase, combined)

    def test_policy_excludes_generated_private_and_conversation_state(self) -> None:
        policy = json.loads((ROOT / "config/public_release_policy.json").read_text(encoding="utf-8"))
        directories = set(policy["excluded_directories"])
        files = set(policy["excluded_files"])
        for required in (
            "build", "build-core", "reports", "user_data", "__pycache__",
            ".signalcloud_shared_deps", ".signalcloud_envs", "content/quarantine", "phase reports",
        ):
            self.assertIn(required, directories)
        for required in (
            "prompt_history*", "Pasted text*", "active.udata", "candidate.udata",
            "previous_known_good.udata", "promotion_receipt.udata", "workload_registry.udata",
            "*.pyc", "*.o", "*.a", "*.tar.gz", "*.zip",
        ):
            self.assertIn(required, files)
        self.assertEqual(set(policy["strict_required_documents"]), {"LICENSE", "LICENSES/CC0-1.0.txt"})
        self.assertEqual(policy["public_version"], "v0.1.0-alpha.1")

    def test_staging_excludes_private_state_and_redacts_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A10 source ") as source_name, tempfile.TemporaryDirectory(
            prefix="SignalCloud A10 stage "
        ) as output_name:
            source = Path(source_name)
            (source / "config").mkdir()
            (source / "tools").mkdir()
            (source / "reports").mkdir()
            (source / "user_data/machine_profiles").mkdir(parents=True)
            (source / "build/CMakeFiles").mkdir(parents=True)
            (source / "CMakeLists.txt").write_text("project(signalcloud)\n", encoding="utf-8")
            self._write_required_docs(source)
            (source / "config/public_release_policy.json").write_text(
                (ROOT / "config/public_release_policy.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            private_root = str(source.resolve())
            (source / "tools/example.py").write_text(
                f"ROOT = {private_root!r}\nHOME = '${HOME}/work'\n",
                encoding="utf-8",
            )
            (source / "reports/private.log").write_text("private\n", encoding="utf-8")
            (source / "user_data/machine_profiles/active.udata").write_text("private\n", encoding="utf-8")
            (source / "build/CMakeFiles/object.o").write_bytes(b"object")
            (source / "prompt_history.txt").write_text("private conversation\n", encoding="utf-8")

            report = prepare_public_stage(source, Path(output_name))
            stage = Path(output_name) / "SignalCloud-Engine"
            text = (stage / "tools/example.py").read_text(encoding="utf-8")
            self.assertNotIn(private_root, text)
            self.assertNotIn("${HOME}", text)
            self.assertIn("<PROJECT_ROOT>", text)
            self.assertIn("${HOME}", text)
            self.assertFalse((stage / "reports").exists())
            self.assertFalse((stage / "user_data").exists())
            self.assertFalse((stage / "build").exists())
            self.assertFalse((stage / "prompt_history.txt").exists())
            self.assertTrue((stage / "PUBLIC_SOURCE_MANIFEST.sha256").is_file())
            self.assertTrue(report.release_ready, report.findings)

    def test_high_confidence_secret_is_withheld_and_blocks_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A10 secret source ") as source_name, tempfile.TemporaryDirectory(
            prefix="SignalCloud A10 secret stage "
        ) as output_name:
            source = Path(source_name)
            (source / "config").mkdir()
            (source / "CMakeLists.txt").write_text("project(signalcloud)\n", encoding="utf-8")
            self._write_required_docs(source)
            (source / "config/public_release_policy.json").write_text(
                (ROOT / "config/public_release_policy.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            marker = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"
            (source / "secret.txt").write_text(marker + "\nnot-real-fixture\n", encoding="utf-8")
            report = prepare_public_stage(source, Path(output_name))
            stage = Path(output_name) / "SignalCloud-Engine"
            self.assertFalse((stage / "secret.txt").exists())
            self.assertTrue(any(item.code == "secret-source-file-blocked" for item in report.blockers))

    def test_tar_and_zip_are_deterministic_for_identical_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A10 deterministic ") as directory:
            root = Path(directory)
            stage = root / "SignalCloud-Engine"
            (stage / "scripts").mkdir(parents=True)
            (stage / "README.md").write_text("SignalCloud\n", encoding="utf-8")
            script = stage / "scripts/run.sh"
            script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            script.chmod(0o755)
            one_tgz, two_tgz = root / "one.tar.gz", root / "two.tar.gz"
            one_zip, two_zip = root / "one.zip", root / "two.zip"
            self.assertEqual(build_deterministic_archive(stage, one_tgz), build_deterministic_archive(stage, two_tgz))
            self.assertEqual(one_tgz.read_bytes(), two_tgz.read_bytes())
            self.assertEqual(build_deterministic_zip(stage, one_zip), build_deterministic_zip(stage, two_zip))
            self.assertEqual(one_zip.read_bytes(), two_zip.read_bytes())

    def test_strict_release_gate_passes_current_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A10 strict ") as directory:
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools/public_release_audit.py"), str(ROOT),
                 "--output", str(Path(directory) / "stage"), "--strict-release"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Release ready: YES", result.stdout)

    def test_current_tree_builds_a_clean_public_release_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="SignalCloud A10 current stage ") as directory:
            report = prepare_public_stage(ROOT, Path(directory))
            stage = Path(directory) / "SignalCloud-Engine"
            self.assertEqual(report.blockers, [], report.findings)
            self.assertEqual(report.warnings, [], report.findings)
            self.assertTrue(report.release_ready)
            self.assertFalse(any(stage.rglob("__pycache__")))
            for excluded in ("reports", "user_data", "build", "build-core", "phase reports", "legacy"):
                self.assertFalse((stage / excluded).exists(), excluded)
            self.assertTrue((stage / "LICENSE").is_file())
            self.assertTrue((stage / "engine/ui/tactical_map_prototype.cpp").is_file())
            manifest = stage / "PUBLIC_SOURCE_MANIFEST.sha256"
            self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(), report.manifest_sha256)


if __name__ == "__main__":
    unittest.main()
