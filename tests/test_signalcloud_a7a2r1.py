from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.asset_doctor.content_abi import repair_machine_paths, scan_content, write_asset_envelope
from tools.pcp3.model import PCPPoint
from tools.signalcloud_showcase.exporter import export_managed_asset
from tools.signalcloud_showcase.importers import import_source
from tools.signalcloud_showcase.model import PhysicsProfile, VisualizationProfile
from tools.signalcloud_showcase.preview import collision_wire_points, project_points
from tools.signalcloud_showcase.simulation import LOOP_SECONDS, sample_test


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA7A2R1Tests(unittest.TestCase):
    def test_all_five_tests_have_visible_bounded_motion(self) -> None:
        profile = PhysicsProfile(shape="box", collision_half_x=0.8, collision_half_y=0.6, collision_half_z=0.5)
        positions: set[tuple[float, float, float]] = set()
        for name in ("drop", "bounce", "slide", "throw", "break"):
            early = sample_test(profile, name, 0.15, loop=False)
            later = sample_test(profile, name, min(2.2, LOOP_SECONDS[name] - 0.1), loop=False)
            self.assertNotEqual((round(early.x, 3), round(early.y, 3), round(early.z, 3)),
                                (round(later.x, 3), round(later.y, 3), round(later.z, 3)))
            self.assertLessEqual(abs(later.x), 7.5)
            self.assertLessEqual(abs(later.z), 7.5)
            positions.add((round(later.x, 2), round(later.y, 2), round(later.z, 2)))
        self.assertGreaterEqual(len(positions), 4)

    def test_collision_wire_shares_translation_and_rotation(self) -> None:
        profile = PhysicsProfile(shape="box", collision_half_x=1.0, collision_half_y=0.5, collision_half_z=0.25)
        base = collision_wire_points(profile)
        moved = collision_wire_points(profile, translation=(3.0, 2.0, -1.0), object_yaw=1.1)
        self.assertEqual(len(base), len(moved))
        self.assertNotAlmostEqual(base[0].x, moved[0].x)
        self.assertNotAlmostEqual(base[0].z, moved[0].z)
        self.assertGreater(min(point.y for point in moved), 1.0)

    def test_actor_preview_visibly_changes_projected_geometry(self) -> None:
        points = [
            PCPPoint(-0.5, 0.0, 0.0), PCPPoint(0.5, 0.0, 0.0),
            PCPPoint(-0.5, 2.0, 0.0), PCPPoint(0.5, 2.0, 0.0),
        ]
        view = VisualizationProfile(actor_preview=True)
        first = project_points(points, 640, 480, view, time_seconds=0.0)
        second = project_points(points, 640, 480, view, time_seconds=0.75)
        self.assertEqual(len(first), len(second))
        displacement = max(abs(a.x - b.x) + abs(a.y - b.y) for a, b in zip(first, second))
        self.assertGreater(displacement, 2.0)

    def test_export_removes_machine_paths_and_reloads_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "content").mkdir()
            source = root / "source.obj"
            source.write_text("v -1 0 0\nv 1 0 0\nv 0 2 0\nf 1 2 3\n", encoding="utf-8")
            asset = import_source(source)
            asset.document.asset_id = "portable_motion_asset"
            private_root = Path("/home") / "exampleuser" / "secret"
            asset.document.metadata["last_project_path"] = str(private_root / "project.pcp3")
            asset.provenance["original_path"] = str(private_root / "source.obj")
            destination = export_managed_asset(asset, root)
            text = (destination / "portable_motion_asset.pcp3").read_text(encoding="utf-8")
            self.assertNotIn("${HOME}", text)
            self.assertIn("content/user/showcase/portable_motion_asset", text)
            report = scan_content(root / "content")
            self.assertEqual((report.error_count, report.warning_count), (0, 0))

    def test_portable_repair_refreshes_existing_envelope_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory) / "content"
            asset = content / "user" / "sample" / "sample.json"
            asset.parent.mkdir(parents=True)
            asset.write_text(json.dumps({"path": str(Path("/home") / "exampleuser" / "private/item.dat")}), encoding="utf-8")
            write_asset_envelope(content, asset, asset_id="sample.portable", asset_type="json_sidecar",
                                 family="metadata", pack="user", license_id="LicenseRef-Test")
            repaired = repair_machine_paths(content)
            self.assertEqual(repaired, ["user/sample/sample.json"])
            report = scan_content(content)
            self.assertEqual((report.error_count, report.warning_count), (0, 0))

    def test_desktop_surface_animates_and_exports_then_reloads(self) -> None:
        source = (ROOT / "tools/signalcloud_showcase/app.py").read_text(encoding="utf-8")
        for token in (
            'f"Animate {name.title()}"', "Stop Motion", "sample_test", "collision_wire_points",
            "Export & Reload", "Managed export complete; reloading self-contained copy",
        ):
            self.assertIn(token, source)
        self.assertIn("self._redraw_after = self.after(33, self.redraw_preview)", source)

    def test_native_stage_uses_shared_transform_loop_and_stage_camera(self) -> None:
        source = (ROOT / "app/showcase_main.cpp").read_text(encoding="utf-8")
        for token in (
            "bool follow_camera = false", "bool auto_loop = true",
            "SDL_SCANCODE_O", "SDL_SCANCODE_HOME", "loop_seconds(active_test)",
            "reset_showcase_state", "CAMERA RESET",
        ):
            self.assertIn(token, source)
        visualization = (ROOT / "engine/physics/showcase_visualization.cpp").read_text(encoding="utf-8")
        self.assertIn("rotate_y(local, state.yaw_radians)", visualization)
        self.assertIn("append_collision(output, profile, state)", visualization)

    def test_native_point_radii_are_normalized_for_real_renderer(self) -> None:
        source = (ROOT / "engine/physics/showcase_visualization.cpp").read_text(encoding="utf-8")
        self.assertIn("point.radius * 0.012F", source)
        self.assertIn("0.008F", source)
        self.assertNotIn("point.radius * options.point_scale", source)

    def test_selftests_repair_user_portability_before_asset_gate(self) -> None:
        source = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        self.assertIn('tools/asset_doctor/asset_doctor.py "$ROOT" --repair-paths', source)

    def test_phase_marker_and_completion_document_exist(self) -> None:
        self.assertTrue((ROOT / "ALPHA_A7A2R1_INSTALLED.txt").is_file())
        document = ROOT / "docs/alpha/A7A2R1_SHOWCASE_MOTION_COMPLETION.md"
        self.assertTrue(document.is_file())
        text = document.read_text(encoding="utf-8").lower()
        for phrase in (
            "shared object transform", "visible motion", "portable managed export",
            "stage-space camera", "a7 completion",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
