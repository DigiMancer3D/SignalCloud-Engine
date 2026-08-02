from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import scan_content
from tools.pcp3.model import PCPPoint
from tools.signalcloud_showcase.catalog import load_catalog_asset, scan_catalog
from tools.signalcloud_showcase.exporter import export_managed_asset
from tools.signalcloud_showcase.importers import import_source
from tools.signalcloud_showcase.model import PhysicsProfile, VisualizationProfile
from tools.signalcloud_showcase.preview import project_points, write_snapshot_ppm


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA7A2Tests(unittest.TestCase):
    def test_visualization_profile_is_bounded_and_preserves_extensions(self) -> None:
        profile = VisualizationProfile.from_dict({
            "view_mode": "invalid",
            "lod_fraction": 0.31,
            "point_scale": 99,
            "animation_rate": -5,
            "snapshot_width": 99,
            "snapshot_height": 99999,
            "future_probe": {"mode": "surface-response"},
        })
        self.assertEqual(profile.view_mode, "source")
        self.assertEqual(profile.lod_fraction, 0.25)
        self.assertEqual(profile.point_scale, 4.0)
        self.assertEqual(profile.animation_rate, 0.1)
        self.assertEqual((profile.snapshot_width, profile.snapshot_height), (320, 4096))
        self.assertEqual(profile.extensions["future_probe"]["mode"], "surface-response")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.scshowcase"
            profile.save(path)
            self.assertEqual(VisualizationProfile.load(path).to_dict(), profile.to_dict())

    def test_collision_auto_fit_uses_real_point_bounds(self) -> None:
        points = [
            PCPPoint(-2.0, -1.0, -0.5),
            PCPPoint(4.0, 3.0, 1.5),
            PCPPoint(0.0, 0.0, 0.0),
        ]
        profile = PhysicsProfile(shape="box").auto_fit(points)
        self.assertAlmostEqual(profile.collision_half_x, 3.0)
        self.assertAlmostEqual(profile.collision_half_y, 2.0)
        self.assertAlmostEqual(profile.collision_half_z, 1.0)
        sphere = PhysicsProfile(shape="sphere").auto_fit(points)
        self.assertAlmostEqual(sphere.collision_radius, 3.0)

    def test_catalog_contains_two_complete_five_asset_starter_sets(self) -> None:
        entries = [entry for entry in scan_catalog(ROOT) if entry.pack == "starter"]
        architecture = [entry for entry in entries if entry.category == "architecture"]
        systems = [entry for entry in entries if entry.category == "systems"]
        self.assertEqual(len(entries), 10)
        self.assertEqual(len(architecture), 5)
        self.assertEqual(len(systems), 5)
        self.assertTrue(all(entry.point_count > 500 for entry in entries))
        self.assertIn("training_actor_block", {entry.asset_id for entry in systems})
        self.assertIn("signal_door_frame", {entry.asset_id for entry in architecture})

    def test_every_starter_has_collision_visualization_and_provenance(self) -> None:
        entries = [entry for entry in scan_catalog(ROOT) if entry.pack == "starter"]
        for entry in entries:
            asset = load_catalog_asset(entry)
            directory = entry.directory
            self.assertTrue((directory / f"{entry.asset_id}.scshowcase").is_file())
            self.assertTrue(asset.visualization.collision_outline)
            self.assertGreater(asset.physics.collision_half_x, 0.01)
            self.assertGreater(asset.physics.collision_half_y, 0.01)
            self.assertGreater(asset.physics.collision_half_z, 0.01)
            self.assertEqual(asset.provenance["license_id"], "CC0-1.0")
        report = scan_content(ROOT / "content" / "starter")
        self.assertEqual((len(report.records), report.valid_count, report.error_count, report.warning_count), (80, 80, 0, 0))

    def test_preview_lod_and_snapshot_are_deterministic_and_portable(self) -> None:
        entry = next(item for item in scan_catalog(ROOT) if item.asset_id == "portable_signal_beacon")
        asset = load_catalog_asset(entry)
        view = VisualizationProfile(view_mode="density", lod_fraction=0.25, snapshot_width=360, snapshot_height=240)
        first = project_points(asset.document.points, 640, 480, view)
        second = project_points(asset.document.points, 640, 480, view)
        self.assertEqual(first, second)
        self.assertEqual(len(first), round(len(asset.document.points) * 0.25))
        with tempfile.TemporaryDirectory() as directory:
            path = write_snapshot_ppm(Path(directory) / "preview.ppm", asset.document.points, asset.physics, view)
            payload = path.read_bytes()
            self.assertTrue(payload.startswith(b"P6\n360 240\n255\n"))
            self.assertEqual(len(payload), len(b"P6\n360 240\n255\n") + 360 * 240 * 3)

    def test_managed_export_writes_reloadable_visualization_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content").mkdir()
            source = root / "shape.obj"
            source.write_text("v -1 0 0\nv 1 0 0\nv 0 2 0\nf 1 2 3\n", encoding="utf-8")
            asset = import_source(source)
            asset.document.asset_id = "visual_triangle"
            asset.visualization = VisualizationProfile(view_mode="material", lod_fraction=0.5, actor_preview=True)
            destination = export_managed_asset(asset, root)
            loaded = VisualizationProfile.load(destination / "visual_triangle.scshowcase")
            self.assertEqual(loaded.view_mode, "material")
            self.assertEqual(loaded.lod_fraction, 0.5)
            self.assertTrue(loaded.actor_preview)
            report = scan_content(root / "content")
            self.assertEqual((report.error_count, report.warning_count), (0, 0))

    def test_native_stage_declares_full_a7a2_visual_controls_and_snapshot(self) -> None:
        source = (ROOT / "app/showcase_main.cpp").read_text(encoding="utf-8")
        for token in (
            "SDL_SCANCODE_C", "SDL_SCANCODE_L", "SDL_SCANCODE_V",
            "SDL_SCANCODE_P", "SDL_SCANCODE_T", "SDL_SCANCODE_S",
            "build_showcase_frame_points", "write_snapshot_ppm", "engine/scfont/scfont.hpp",
        ):
            self.assertIn(token, source)
        launcher = (ROOT / "scripts/launch_showcase_native.sh").read_text(encoding="utf-8")
        self.assertIn("--visualization=", launcher)
        self.assertIn("--snapshot-dir=", launcher)

    def test_native_visualization_runtime_is_shared_and_tested(self) -> None:
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        setup = (ROOT / "scripts/setup_dev_environment.sh").read_text(encoding="utf-8")
        selftests = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        self.assertIn("engine/physics/showcase_visualization.cpp", cmake)
        self.assertIn("signalcloud_showcase_visualization_tests", cmake)
        for text in (setup, selftests):
            self.assertIn("engine/physics/showcase_visualization.cpp", text)

    def test_desktop_showcase_exposes_catalog_preview_modes_and_snapshots(self) -> None:
        source = (ROOT / "tools/signalcloud_showcase/app.py").read_text(encoding="utf-8")
        for token in (
            "Managed Showcase Catalog", "Live Point Preview", "Snapshot PPM",
            "Auto-fit to points", "Actor/Playbook", "scan_catalog",
        ):
            self.assertIn(token, source)
        self.assertIn("A7a2", source)

    def test_phase_marker_and_documentation_exist(self) -> None:
        document = ROOT / "docs/alpha/A7A2_SHOWCASE_VISUALIZATION_CATALOG.md"
        self.assertTrue(document.is_file())
        text = document.read_text(encoding="utf-8")
        for phrase in ("collision outlines", "deterministic LOD", "material and light", "actor/Playbook", "PPM snapshots"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
