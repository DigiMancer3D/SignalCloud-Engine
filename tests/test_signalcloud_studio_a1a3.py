from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.light_lab_gui import (
    Aperture,
    DayNight,
    LightLabApp,
    LightSource,
    Vec3,
    light_set_from_json,
    read_light_set,
    write_light_set,
)
from tools.signalcloud_studio.app import build_catalog
from tools.signalcloud_studio.compatibility.pcp3_document_bridge import (
    _find_cascade_menu,
    publish_pcp3_document,
)
from tools.signalcloud_studio.context import ToolContext
from tools.signalcloud_studio.documents import (
    DocumentContextBus,
    DocumentContextStore,
    StudioDocumentContext,
    StudioSelection,
)


class SignalCloudStudioA1A3Tests(unittest.TestCase):
    def test_catalog_registers_light_lab_as_second_canonical_tool(self) -> None:
        infos = {item.key: item.display_name for item in build_catalog().infos()}
        self.assertEqual(set(infos), {"pcp3", "light-lab", "jitter-texture-lab", "universal-playbook-lab", "font-studio", "showcase-physics", "tupd-workbench"})
        self.assertIn("Light Lab", infos["light-lab"])
        self.assertIn("Font Studio", infos["font-studio"])

    def test_document_context_round_trip_is_project_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document = root / "content" / "user" / "lights" / "hall.slight"
            document.parent.mkdir(parents=True)
            document.write_text("{}", encoding="utf-8")
            store = DocumentContextStore.for_project(root)
            context = store.publish(
                StudioDocumentContext(),
                active_document=document,
                document_kind="light_set",
                owner_tool="light-lab",
                dirty=False,
                selection=StudioSelection(asset_id="hall_light"),
            )
            self.assertEqual(context.active_document, "content/user/lights/hall.slight")
            raw = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(raw["active_document"], "content/user/lights/hall.slight")
            self.assertNotIn(str(root), store.path.read_text(encoding="utf-8"))
            self.assertEqual(store.resolve_active_path(context), document.resolve())

    def test_document_context_rejects_escape_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            store = DocumentContextStore.for_project(root)
            with self.assertRaises(ValueError):
                store.publish(StudioDocumentContext(), active_document=root.parent / "outside.slight")

    def test_document_context_is_forgiving_and_preserves_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = DocumentContextStore.for_project(root)
            store.path.parent.mkdir(parents=True)
            store.path.write_text(
                json.dumps(
                    {
                        "schema": "future_context_v9",
                        "active_document": None,
                        "future_bus": {"kept": True},
                        "selection": {"node_ids": ["n1"]},
                    }
                ),
                encoding="utf-8",
            )
            context = store.read()
            self.assertEqual(context.selection.node_ids, ("n1",))
            self.assertEqual(context.unknown_fields["future_bus"], {"kept": True})
            store.write(context.updated(owner_tool="pcp3"))
            self.assertEqual(json.loads(store.path.read_text())["future_bus"], {"kept": True})

    def test_document_bus_replays_and_unsubscribes(self) -> None:
        first = StudioDocumentContext(revision=2)
        bus = DocumentContextBus(first)
        seen: list[int] = []
        unsubscribe = bus.subscribe(lambda context: seen.append(context.revision))
        bus.publish(first.updated())
        unsubscribe()
        bus.publish(first.updated(revision=4))
        self.assertEqual(seen, [2, 3])

    def test_pcp3_bridge_publishes_saved_document_for_light_lab(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "user_data" / "pcp3" / "projects" / "hall.pcp3"
            project.parent.mkdir(parents=True)
            project.write_text("{}", encoding="utf-8")
            store = DocumentContextStore.for_project(root)
            context = ToolContext(
                project_root=root,
                document_context=StudioDocumentContext(),
                document_store=store,
                document_bus=DocumentContextBus(),
            )
            document = SimpleNamespace(
                asset_id="long_signal_hall",
                project_id="project-1",
                environment_type="architecture",
                dirty=True,
                selected_indices={7, 2},
                points=[object(), object(), object()],
            )
            publish_pcp3_document(context, project, document)
            shared = store.read()
            self.assertEqual(shared.active_document, "user_data/pcp3/projects/hall.pcp3")
            self.assertEqual(shared.document_kind, "pcp3_project")
            self.assertEqual(shared.selection.asset_id, "long_signal_hall")
            self.assertEqual(shared.selection.node_ids, ("point:2", "point:7"))
            self.assertEqual(shared.metadata["point_count"], 3)

    def test_pcp3_adapter_adds_linked_light_lab_command(self) -> None:
        root = Path(__file__).resolve().parents[1]
        bridge = (
            root
            / "tools"
            / "signalcloud_studio"
            / "compatibility"
            / "pcp3_document_bridge.py"
        ).read_text(encoding="utf-8")
        adapter = (
            root
            / "tools"
            / "signalcloud_studio"
            / "compatibility"
            / "branch12r1_adapter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Open linked Illuminosity Light Lab", bridge)
        self.assertIn("_find_cascade_menu", bridge)
        self.assertIn("launch_bridged_branch12r1", adapter)

    def test_menu_lookup_skips_unlabelled_tearoff_entry(self) -> None:
        child = object()

        class FakeMenu:
            def index(self, value):
                self.assert_value(value, "end")
                return 2

            @staticmethod
            def assert_value(value, expected):
                if value != expected:
                    raise AssertionError((value, expected))

            def type(self, index):
                return ("tearoff", "cascade", "cascade")[index]

            def entrycget(self, index, option):
                if index == 0:
                    raise __import__("tkinter").TclError('unknown option "-label"')
                values = {
                    (1, "label"): "Tools",
                    (1, "menu"): ".tools",
                    (2, "label"): "Help",
                    (2, "menu"): ".help",
                }
                return values[(index, option)]

            def nametowidget(self, name):
                return child if name == ".tools" else object()

        self.assertIs(_find_cascade_menu(FakeMenu(), "Tools"), child)

    def test_daynight_callbacks_are_safe_before_labels_exist(self) -> None:
        app = object.__new__(LightLabApp)
        app.daynight = DayNight()
        app._mark_dirty = lambda: None
        app._on_dn_scale("55")
        app._on_nd_scale("65")
        self.assertEqual(app.daynight.day_to_night_s, 55.0)
        self.assertEqual(app.daynight.night_to_day_s, 65.0)

    def test_light_set_round_trip_is_atomic_and_preserves_future_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "room.slight"
            lights = [
                LightSource(
                    Vec3(1, 2, 3),
                    Vec3(4, 5, 6),
                    88.0,
                    12.0,
                    (0.2, 0.4, 0.6),
                    False,
                    False,
                    "HallLamp",
                )
            ]
            write_light_set(
                path,
                lights,
                Aperture(distance=3.25),
                DayNight(day_to_night_s=52.0),
                unknown_fields={"future_bounces": {"limit": 7}},
                linked_document="content/user/pcp3/hall.pcp3",
            )
            loaded_lights, aperture, daynight, unknown, linked = read_light_set(path)
            self.assertEqual(loaded_lights[0].name, "HallLamp")
            self.assertAlmostEqual(loaded_lights[0].i_pct, 88.0)
            self.assertAlmostEqual(aperture.distance, 3.25)
            self.assertAlmostEqual(daynight.day_to_night_s, 52.0)
            self.assertEqual(unknown["future_bounces"], {"limit": 7})
            self.assertEqual(linked, "content/user/pcp3/hall.pcp3")
            self.assertFalse(path.with_suffix(".slight.tmp").exists())

    def test_light_set_reader_skips_unknown_light_entries(self) -> None:
        lights, aperture, daynight, _unknown, _linked = light_set_from_json(
            {
                "lights": [
                    "bad",
                    {
                        "name": "Valid",
                        "position": [1, 2, 3],
                        "radius": "bad",
                        "illuminosity_percent": None,
                    },
                ],
                "aperture": {"distance": "bad"},
                "day_night": {"time_of_day": "bad"},
            }
        )
        self.assertEqual([item.name for item in lights], ["Valid"])
        self.assertEqual(lights[0].radius, 9.0)
        self.assertEqual(aperture.distance, 2.5)
        self.assertEqual(daynight.time_of_day, 0.35)

    def test_control_panel_and_scripts_expose_light_lab(self) -> None:
        root = Path(__file__).resolve().parents[1]
        launcher = (root / "tools" / "signalcloud_launcher.py").read_text(encoding="utf-8")
        self.assertIn('value="light-lab"', launcher)
        self.assertIn("def launch_light_lab", launcher)
        script = root / "scripts" / "launch_light_lab.sh"
        self.assertTrue(script.exists())
        self.assertIn("--tool light-lab", script.read_text(encoding="utf-8"))

    def test_light_lab_uses_managed_shared_document_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "tools" / "light_lab_gui.py").read_text(encoding="utf-8")
        self.assertIn('"content" / "user" / "lights"', text)
        self.assertIn("document_store.publish", text)
        self.assertIn("linked_document", text)
        self.assertIn("LIGHT_SET_SCHEMA", text)


if __name__ == "__main__":
    unittest.main()
