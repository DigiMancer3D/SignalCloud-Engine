from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.pcp3.io import load_project, read_cloud
from tools.signalcloud_showcase.exporter import export_managed_asset
from tools.signalcloud_showcase.importers import import_source
from tools.signalcloud_showcase.model import PhysicsProfile
from tools.signalcloud_showcase.simulation import run_test
from tools.signalcloud_studio.app import build_catalog


ROOT = Path(__file__).resolve().parents[1]


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _write_png(path: Path) -> None:
    width, height = 2, 2
    rows = b"".join([
        b"\x00" + bytes((255, 0, 0, 255, 0, 255, 0, 255)),
        b"\x00" + bytes((0, 0, 255, 255, 255, 255, 255, 255)),
    ])
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    payload += _png_chunk(b"IDAT", zlib.compress(rows))
    payload += _png_chunk(b"IEND", b"")
    path.write_bytes(payload)


def _write_bmp(path: Path) -> None:
    width, height, bits = 2, 2, 24
    row_size = ((width * bits + 31) // 32) * 4
    pixels = (
        bytes((255, 0, 0, 0, 255, 0)) + b"\x00\x00" +
        bytes((0, 0, 255, 255, 255, 255)) + b"\x00\x00"
    )
    offset = 54
    header = b"BM" + struct.pack("<IHHI", offset + row_size * height, 0, 0, offset)
    dib = struct.pack("<IiiHHIIiiII", 40, width, height, 1, bits, 0, row_size * height, 2835, 2835, 0, 0)
    path.write_bytes(header + dib + pixels)


class SignalCloudA7A1Tests(unittest.TestCase):
    def test_physics_profile_is_bounded_and_preserves_extensions(self) -> None:
        profile = PhysicsProfile.from_dict({
            "shape": "unsafe-mesh",
            "mass": -9,
            "friction": 99,
            "restitution": 7,
            "gravity_scale": 99,
            "future_solver": {"mode": "jolt-adapter"},
        })
        self.assertEqual(profile.shape, "box")
        self.assertEqual(profile.mass, 0.001)
        self.assertEqual(profile.friction, 4.0)
        self.assertEqual(profile.restitution, 1.0)
        self.assertEqual(profile.gravity_scale, 8.0)
        self.assertEqual(profile.extensions["future_solver"]["mode"], "jolt-adapter")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.scphysics"
            profile.save(path)
            loaded = PhysicsProfile.load(path)
            self.assertEqual(loaded.to_dict(), profile.to_dict())

    def test_physics_tests_are_deterministic_and_distinct(self) -> None:
        profile = PhysicsProfile(mass=7.5, restitution=0.35, break_threshold=45.0)
        first = run_test(profile, "throw")
        second = run_test(profile, "throw")
        broken = run_test(profile, "break")
        self.assertEqual(first.signature, second.signature)
        self.assertEqual(first.end_position, second.end_position)
        self.assertNotEqual(first.signature, broken.signature)
        self.assertTrue(broken.broken)

    def test_ascii_ply_and_obj_import_are_bounded_data_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ply = root / "triangle.ply"
            ply.write_text(
                "ply\nformat ascii 1.0\nelement vertex 3\n"
                "property float x\nproperty float y\nproperty float z\n"
                "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                "end_header\n0 0 0 255 0 0\n1 0 0 0 255 0\n0 1 0 0 0 255\n",
                encoding="utf-8",
            )
            mtl = root / "shape.mtl"
            mtl.write_text("newmtl blue\nKd 0.1 0.2 0.9\n", encoding="utf-8")
            obj = root / "shape.obj"
            obj.write_text(
                "mtllib shape.mtl\nusemtl blue\n"
                "v 0 0 0\nv 2 0 0\nv 0 2 0\nf 1 2 3\n",
                encoding="utf-8",
            )
            ply_asset = import_source(ply)
            obj_asset = import_source(obj)
            self.assertEqual(ply_asset.source_kind, "ascii-ply")
            self.assertEqual(len(ply_asset.document.points), 3)
            self.assertEqual(obj_asset.source_kind, "obj")
            self.assertGreater(len(obj_asset.document.points), 3)
            self.assertEqual(obj_asset.provenance["execution_policy"], "never_execute_source")

    def test_png_bmp_and_metadata_imports_use_safe_point_cards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "sample.png"
            bmp = root / "sample.bmp"
            script = root / "do_not_run.script"
            marker = root / "executed.txt"
            _write_png(png)
            _write_bmp(bmp)
            script.write_text(f"shell.exec: touch {marker};\n", encoding="utf-8")
            png_asset = import_source(png)
            bmp_asset = import_source(bmp)
            script_asset = import_source(script)
            self.assertEqual(len(png_asset.document.points), 4)
            self.assertEqual(len(bmp_asset.document.points), 4)
            self.assertGreater(len(script_asset.document.points), 100)
            self.assertEqual(script_asset.document.metadata["execution"], "blocked")
            self.assertFalse(marker.exists())

    def test_native_formats_round_trip_through_importer(self) -> None:
        directory = ROOT / "content/starter/showcase/office_shipping_crate"
        project_asset = import_source(directory / "office_shipping_crate.pcp3")
        cloud_asset = import_source(directory / "office_shipping_crate.pcp3cloud")
        self.assertEqual(project_asset.source_kind, "pcp3")
        self.assertEqual(cloud_asset.source_kind, "pcp3cloud")
        self.assertEqual(len(project_asset.document.points), len(cloud_asset.document.points))
        self.assertGreater(len(project_asset.document.points), 100)

    def test_managed_export_is_self_contained_and_reloadable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content").mkdir()
            source = root / "outside.obj"
            source.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
            asset = import_source(source)
            asset.document.asset_id = "managed_triangle"
            destination = export_managed_asset(asset, root)
            source.unlink()
            project = load_project(destination / "managed_triangle.pcp3")
            points, _ = read_cloud(destination / "managed_triangle.pcp3cloud")
            profile = PhysicsProfile.load(destination / "managed_triangle.scphysics")
            self.assertEqual(len(project.points), len(points))
            self.assertEqual(project.metadata["showcase_source_path"], "source/outside.obj")
            self.assertTrue((destination / "source/outside.obj").is_file())
            self.assertEqual(profile.profile_id, "showcase.managed_triangle")
            report = scan_content(root / "content")
            self.assertEqual((report.error_count, report.warning_count), (0, 0))

    def test_shipped_starters_are_original_licensed_and_valid(self) -> None:
        for asset_id in ("office_shipping_crate", "portable_signal_beacon"):
            directory = ROOT / "content/starter/showcase" / asset_id
            provenance = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["license_id"], "CC0-1.0")
            self.assertEqual(provenance["execution_policy"], "no_external_source")
            self.assertTrue((directory / f"{asset_id}.scphysics").is_file())
            self.assertTrue((directory / f"{asset_id}.pcp3cloud").is_file())
        report = scan_content(ROOT / "content" / "starter")
        self.assertGreaterEqual(len(report.records), 12)
        self.assertEqual((report.valid_count, report.error_count, report.warning_count), (len(report.records), 0, 0))

    def test_studio_launcher_and_native_target_expose_showcase(self) -> None:
        catalog = {item.key: item for item in build_catalog().infos()}
        self.assertEqual(len(catalog), 7)
        self.assertIn("showcase-physics", catalog)
        self.assertTrue((ROOT / "scripts/launch_showcase.sh").is_file())
        self.assertTrue((ROOT / "scripts/launch_showcase_native.sh").is_file())
        launcher = (ROOT / "tools/signalcloud_launcher.py").read_text(encoding="utf-8")
        self.assertIn("def launch_showcase", launcher)
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("almond_signal_showcase", cmake)
        self.assertIn("signalcloud_showcase_runtime_tests", cmake)

    def test_build_gates_validate_showcase_and_require_gui_binary(self) -> None:
        setup = (ROOT / "scripts/setup_dev_environment.sh").read_text(encoding="utf-8")
        selftests = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        for text in (setup, selftests):
            self.assertIn("engine/physics/showcase_runtime.cpp", text)
            self.assertIn("app/showcase_main.cpp", text)
        self.assertIn("almond_signal_showcase", setup)
        self.assertIn("validate_showcase_starters.sh", selftests)

    def test_phase_marker_and_documentation_exist(self) -> None:
        self.assertTrue((ROOT / "ALPHA_A7A1_INSTALLED.txt").is_file())
        document = ROOT / "docs/alpha/A7A1_3D_ENVIRONMENT_PHYSICS_SHOWCASE_FOUNDATION.md"
        self.assertTrue(document.is_file())
        text = document.read_text(encoding="utf-8")
        self.assertIn("data-only", text)
        self.assertIn("Jolt adapter boundary", text)
        self.assertIn("native Showcase", text)


if __name__ == "__main__":
    unittest.main()
