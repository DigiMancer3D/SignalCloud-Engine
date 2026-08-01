from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.check_cpp_literals import scan_cpp_literals
from tools.signalcloud_studio.ui.flow import wrapped_row_assignments


ROOT = Path(__file__).resolve().parents[1]


class SignalCloudA3A2R1Tests(unittest.TestCase):
    def test_native_game_source_has_no_physical_literal_newlines(self) -> None:
        self.assertEqual(scan_cpp_literals(ROOT / "app/game_main.cpp"), [])
        self.assertEqual(scan_cpp_literals(ROOT / "app/main.cpp"), [])

    def test_literal_gate_catches_a3a2_failure_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "broken.cpp"
            source.write_text('std::cout << "broken\n";\n', encoding="utf-8")
            issues = scan_cpp_literals(source)
            self.assertTrue(issues)
            self.assertIn("physical newline", issues[0].message)

    def test_game_launcher_prepares_missing_native_binary_automatically(self) -> None:
        launcher = (ROOT / "scripts/launch_game.sh").read_text(encoding="utf-8")
        self.assertIn('"$ROOT/scripts/setup_dev_environment.sh"', launcher)
        self.assertIn("preparing the SignalCloud runtime automatically", launcher)
        self.assertNotIn("Run ./scripts/setup_dev_environment.sh first", launcher)

    def test_host_uses_dynamic_action_tabs_axis_viewport_and_fixed_footer(self) -> None:
        host = (ROOT / "tools/signalcloud_studio/host.py").read_text(encoding="utf-8")
        self.assertIn("ACTION_GROUPS", host)
        self.assertIn("AxisSwitchViewport", host)
        self.assertIn("Studio action tabs", host)
        self.assertIn("self.footer", host)
        self.assertNotIn('text="Choose a tool"', host)
        self.assertIn("Open Asset Doctor", host)
        self.assertIn("Open Pack Builder", host)

    def test_axis_viewport_contract_is_exclusive_and_single_bar(self) -> None:
        source = (ROOT / "tools/signalcloud_studio/ui/axis_scroll.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('orient="horizontal"'), 1)
        self.assertNotIn('ttk.Scrollbar(control, orient="vertical"', source)
        self.assertIn('self.axis_x.set(axis == "x")', source)
        self.assertIn('self.axis_y.set(axis == "y")', source)
        self.assertIn('self._active_axis = "x"', source)

    def test_asset_doctor_relies_on_shared_axis_viewport(self) -> None:
        source = (ROOT / "tools/signalcloud_studio/asset_doctor_panel.py").read_text(encoding="utf-8")
        self.assertNotIn('ttk.Scrollbar(control, orient="vertical"', source)
        self.assertIn("FlowBar", source)
        self.assertIn("tree.configure(height=", source)

    def test_dynamic_rows_expand_as_width_shrinks(self) -> None:
        widths = [140, 160, 155, 175]
        wide = wrapped_row_assignments(widths, 800)
        narrow = wrapped_row_assignments(widths, 310)
        self.assertGreater(max(row for row, _column in narrow), max(row for row, _column in wide))

    def test_hot_reload_package_is_lazy_to_avoid_runpy_warning(self) -> None:
        source = (ROOT / "tools/asset_doctor/__init__.py").read_text(encoding="utf-8")
        self.assertIn("def __getattr__", source)
        self.assertNotIn("from .hot_reload_bridge import HotReloadStageResult, stage_preview_reload\n", source.split("def __getattr__", 1)[0])

    def test_selftests_include_native_literal_preflight(self) -> None:
        script = (ROOT / "scripts/run_selftests.sh").read_text(encoding="utf-8")
        self.assertIn("tools/check_cpp_literals.py", script)
        self.assertIn("app/game_main.cpp", script)
        self.assertIn("app/main.cpp", script)


if __name__ == "__main__":
    unittest.main()
