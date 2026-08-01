from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.signalcloud_studio.toolbar import ToolbarGroupSpec, plan_toolbar
from tools.signalcloud_studio.ui import wrapped_row_assignments
from tools.signalcloud_studio.workspace import PaneState, WorkspaceLayoutStore


class SignalCloudStudioA1A2Tests(unittest.TestCase):
    def test_pane_state_round_trip_and_zoom_bounds(self) -> None:
        state = PaneState.from_json({"depth": 4.5, "zoom": 9999, "pan_x": 2, "pan_y": -3})
        self.assertEqual(state.zoom, 400.0)
        self.assertEqual(PaneState.from_json(state.to_json()), state)

    def test_invalid_workspace_is_forgiving(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workspace.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(WorkspaceLayoutStore(path).read(), {})

    def test_workspace_write_is_atomic_and_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config" / "workspace.json"
            store = WorkspaceLayoutStore(path)
            store.write({"schema": "studio_workspace_v1", "geometry": "1200x800"})
            self.assertEqual(store.read()["geometry"], "1200x800")
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_workspace_merge_preserves_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workspace.json"
            store = WorkspaceLayoutStore(path)
            store.write({"future_setting": {"kept": True}, "axis": "x"})
            result = store.merge({"axis": "y"})
            self.assertEqual(result["axis"], "y")
            self.assertEqual(result["future_setting"], {"kept": True})

    def test_wrapped_assignments_are_deterministic(self) -> None:
        widths = [80, 80, 80, 80]
        self.assertEqual(wrapped_row_assignments(widths, 170), [(0, 0), (0, 1), (1, 0), (1, 1)])
        self.assertEqual(wrapped_row_assignments(widths, 170), wrapped_row_assignments(widths, 170))

    def test_toolbar_plan_orders_priority_then_key(self) -> None:
        result = plan_toolbar(
            [
                ToolbarGroupSpec("preview", 100, priority=20),
                ToolbarGroupSpec("file", 100, priority=10),
                ToolbarGroupSpec("edit", 100, priority=10),
            ],
            210,
        )
        self.assertEqual([item.key for item in result], ["edit", "file", "preview"])
        self.assertEqual((result[-1].row, result[-1].column), (1, 0))

    def test_pcp3_editor_uses_canonical_tooltip(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "tools" / "pcp3" / "editor.py").read_text(encoding="utf-8")
        self.assertIn("from tools.signalcloud_studio.ui import ToolTip", text)
        self.assertNotIn("class ToolTip:", text)

    def test_multiview_uses_canonical_workspace_and_flow(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "tools" / "pcp3" / "editor_branch2r2.py").read_text(encoding="utf-8")
        self.assertIn("from tools.signalcloud_studio.ui import FlowBar", text)
        self.assertIn("WorkspaceLayoutStore", text)
        self.assertNotIn("class FlowBar", text)
        self.assertNotIn("class PaneState", text)

    def test_sidebar_uses_canonical_wrapped_navigation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "tools" / "pcp3" / "editor_branch10r1.py").read_text(encoding="utf-8")
        self.assertIn("WrappedNotebookBar", text)
        self.assertIn("WorkspaceLayoutStore", text)
        self.assertNotIn("class WrappedNotebookBar", text)
        self.assertNotIn("def wrapped_row_assignments", text)

    def test_cpp_event_names_do_not_shadow_sdl_event(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ("app/game_main.cpp", "app/native_stress_main.cpp"):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("for (const auto& event : pcp3_", text)
            self.assertIn("interaction_event", text)
            self.assertIn("encounter_event", text)


if __name__ == "__main__":
    unittest.main()
