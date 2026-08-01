#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
SC_PYCACHE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/signalcloud-pcp3-quick-pycache.XXXXXX")"
export PYTHONPYCACHEPREFIX="$SC_PYCACHE_DIR"
trap 'rm -rf -- "$SC_PYCACHE_DIR"' EXIT
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
cd "$ROOT"
sc_repair_future_timestamps "$ROOT"

sc_prepare_cmake_build_dir "$ROOT" "$ROOT/build-core" Ninja
cmake -S . -B build-core -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DSC_BUILD_GUI=OFF \
  -DBUILD_TESTING=ON
cmake --build build-core --target signalcloud_pivot4_tests signalcloud_native_stress_route_tests signalcloud_pcp3_asset_tests signalcloud_pcp3_interaction_tests signalcloud_pcp3_entity_tests signalcloud_pcp3_world_tests signalcloud_pcp3_encounter_tests signalcloud_pcp3_streaming_tests --parallel
ctest --test-dir build-core -R 'signalcloud_(pivot4|native_stress_route|pcp3_(asset|interaction|entity|world|encounter|streaming))_tests' --output-on-failure

PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
"$PYTHON" -m py_compile tools/pcp3/*.py tools/pcp3_editor.py tools/pcp3_workspace_repair.py tools/signalcloud_launcher.py tools/stress_content_catalog.py
"$PYTHON" -m unittest -v \
  tests.test_pcp3_pipeline \
  tests.test_pcp3_branch2_interaction \
  tests.test_pcp3_branch2r1_safety \
  tests.test_pcp3_branch2r2_multiview \
  tests.test_pcp3_branch2r3_features \
  tests.test_pcp3_branch2r3r1_sync_safety \
  tests.test_pcp3_branch3_mode_studio \
  tests.test_pcp3_branch3r1_architecture \
  tests.test_pcp3_branch4_advanced_authoring \
  tests.test_pcp3_branch5_runtime_preview \
  tests.test_pcp3_branch6_runtime_factory \
  tests.test_pcp3_branch7_guarded_interaction \
  tests.test_pcp3_branch7r1_interaction_authoring \
  tests.test_pcp3_branch8_entity_runtime \
  tests.test_pcp3_branch8r2_route_containment \
  tests.test_pcp3_branch9_world_assembly \
  tests.test_pcp3_branch10_encounter_runtime \
  tests.test_pcp3_branch10r1_sidebar_navigation \
  tests.test_pcp3_branch10r2_sidebar_content \
  tests.test_pcp3_branch11_streaming_runtime \
  tests.test_pcp3_branch12_authoring_help \
  tests.test_pcp3_branch12r1_help_center

if command -v xvfb-run >/dev/null 2>&1; then
  timeout 30s xvfb-run -a "$PYTHON" - "$ROOT" <<'PYX'
from pathlib import Path
import sys
from tkinter import ttk
from tools.pcp3.editor_branch12r1 import PCP3Editor
from tools.pcp3.editor_branch10r1 import REMOVED_TOPBAR_COMMANDS, SIDEBAR_ACTIONS
from tools.pcp3.runtime_factory import compile_runtime_factory, ensure_runtime_factory
from tools.pcp3.runtime_interaction import compile_runtime_interaction, ensure_runtime_interaction
from tools.pcp3.entity_runtime import compile_entity_runtime, ensure_entity_runtime
from tools.pcp3.world_assembly import compile_world_assembly, ensure_world_assembly
from tools.pcp3.encounter_runtime import compile_encounter_runtime, ensure_encounter_runtime
from tools.pcp3.streaming_runtime import compile_streaming_runtime, ensure_streaming_runtime

root = Path(sys.argv[1])
app = PCP3Editor(root)
app.geometry("1600x900")
app.update_idletasks()
app.update()
assert app.authoring_notebook.index("end") == 12
assert app.authoring_notebook.tab(5, "text") == "Playback"
assert app.authoring_notebook.tab(6, "text") == "Factory"
assert app.authoring_notebook.tab(7, "text") == "Interaction"
assert app.authoring_notebook.tab(8, "text") == "Entity"
assert app.authoring_notebook.tab(9, "text") == "World"
assert app.authoring_notebook.tab(10, "text") == "Encounter"
assert app.authoring_notebook.tab(11, "text") == "Streaming"
assert len(app.pane_canvases) in {1, 3, 4}
factory = ensure_runtime_factory(app.document)
factory.update({"enabled": True, "game_enabled": True, "stress_enabled": True, "scanner_gate": True})
app.refresh_factory_panel()
compiled = compile_runtime_factory(app.document)
assert compiled["enabled"] and compiled["targets"]["game"] and compiled["targets"]["stress"]
assert compiled["limits"]["max_nesting_depth"] == 1
command_row = next(child for child in app.command_toolbar.winfo_children() if int(child.grid_info().get("row", -1)) == 0)
def widget_texts(widget):
    values = []
    for child in widget.winfo_children():
        try:
            text = str(child.cget("text"))
        except Exception:
            text = ""
        if text:
            values.append(text)
        values.extend(widget_texts(child))
    return values
row_text = widget_texts(command_row)
assert "Native Preview" in row_text
assert "Brush Editor" in row_text
assert "Tools Help" in row_text
assert not set(REMOVED_TOPBAR_COMMANDS).intersection(row_text)
action_text = []
for group in app.sidebar_action_header.items:
    action_text.extend(widget_texts(group))
assert tuple(action_text) == SIDEBAR_ACTIONS
assert [app.right_notebook.tab(i, "text") for i in range(app.right_notebook.index("end"))] == [
    "Layers", "Depth", "Mode", "Authoring", "Properties", "Certificate", "History"
]
assert [app.authoring_notebook.tab(i, "text") for i in range(app.authoring_notebook.index("end"))] == [
    "Rig", "Timeline", "Gameplay", "Placement", "Flow/Theme", "Playback",
    "Factory", "Interaction", "Entity", "World", "Encounter", "Streaming"
]
# Regression: the active page must occupy the sidebar viewport rather than
# being covered by the later-created viewport frame.
app.show_authoring_studio()
app.update_idletasks()
app.update()
viewport = app.sidebar_content_viewport
notebook = app.right_notebook
sample_x = viewport.winfo_rootx() + min(24, max(1, viewport.winfo_width() - 1))
sample_y = viewport.winfo_rooty() + min(24, max(1, viewport.winfo_height() - 1))
visible_widget = app.winfo_containing(sample_x, sample_y)
assert visible_widget is not None
assert visible_widget != viewport
assert notebook.winfo_width() >= viewport.winfo_width()
assert notebook.winfo_height() >= viewport.winfo_height()
assert app.status_bar_frame is not None and app.status_bar_frame.winfo_height() >= 20
assert app.status_bar_frame.winfo_y() + app.status_bar_frame.winfo_height() <= app.winfo_height()
style = ttk.Style(app)
assert style.layout("PCP3SidebarContent.TNotebook.Tab") == [("null", {"sticky": "nswe"})]
assert style.layout("PCP3AuthoringContent.TNotebook.Tab") == [("null", {"sticky": "nswe"})]
app.sidebar_subtab_locked.set(True)
app._sidebar_subtab_changed()
app.update_idletasks()
assert app.right_notebook.tab(app.right_notebook.select(), "text") == "Authoring"
assert app.sidebar_scroll_target_text.get() == "Authoring sub-tabs"
app.sidebar_scroll_axis.set("y")
app._sidebar_axis_changed()
assert app.layer_scroll_axis.get() == "y"
app.update_idletasks()
before_subtab = app.authoring_wrapped_tabs.canvas.yview()
app._sidebar_shared_scroll_command("moveto", "1.0")
after_subtab = app.authoring_wrapped_tabs.canvas.yview()
assert after_subtab[0] >= before_subtab[0]
app.sidebar_subtab_locked.set(False)
app._sidebar_subtab_changed()
assert app.sidebar_scroll_target_text.get() == "Active tab content"
interaction = ensure_runtime_interaction(app.document)
interaction.update({"enabled": True, "game_enabled": True, "stress_enabled": True})
app.refresh_interaction_panel()
compiled_interaction = compile_runtime_interaction(app.document)
assert compiled_interaction["enabled"] and compiled_interaction["targets"]["game"]
# Reproduce the user callback path that failed in Branch 7.
app.document.dirty = False
app.interaction_vars["enabled"].set(True)
app.interaction_changed()
assert app.document.dirty
app.document.dirty = False
app.factory_vars["enabled"].set(True)
app.factory_changed()
assert app.document.dirty
# The bridge must expose Gameplay and enable both guarded layers explicitly.
app.open_gameplay_trigger_authoring()
assert app.authoring_notebook.tab(app.authoring_notebook.select(), "text") == "Gameplay"
app.show_interaction_runtime()
app.enable_safe_runtime_chain()
assert ensure_runtime_factory(app.document)["enabled"]
assert ensure_runtime_interaction(app.document)["enabled"]
# Entity Runtime must be independently guarded and compile without game mutation.
entity = ensure_entity_runtime(app.document)
entity.update({"enabled": True, "game_enabled": True, "stress_enabled": True})
app.refresh_entity_panel()
compiled_entity = compile_entity_runtime(app.document)
assert compiled_entity["schema"] == "pcp3_entity_runtime_v1"
app.document.dirty = False
app.entity_vars["enabled"].set(True)
app.entity_changed()
assert app.document.dirty
world = ensure_world_assembly(app.document)
world.update({"enabled": True, "game_enabled": True, "stress_enabled": True, "host_zone": "Reception Tape"})
app.refresh_world_panel()
compiled_world = compile_world_assembly(app.document, root)
assert compiled_world["schema"] == "pcp3_world_assembly_v1"
app.document.dirty = False
app.world_vars["enabled"].set(True)
app.world_changed()
assert app.document.dirty
encounter = ensure_encounter_runtime(app.document)
encounter.update({"enabled": True, "game_enabled": False, "stress_enabled": True, "host_zone": "Reception Tape"})
app.refresh_encounter_panel()
compiled_encounter = compile_encounter_runtime(app.document, root)
assert compiled_encounter["schema"] == "pcp3_encounter_runtime_v1"
app.document.dirty = False
app.encounter_vars["enabled"].set(True)
app.encounter_changed()
assert app.document.dirty
streaming = ensure_streaming_runtime(app.document)
streaming.update({"enabled": True, "game_enabled": False, "stress_enabled": True, "profile": "adaptive_8m"})
app.refresh_streaming_panel()
compiled_streaming = compile_streaming_runtime(app.document)
assert compiled_streaming["schema"] == "pcp3_streaming_runtime_v1"
assert compiled_streaming["targets"]["stress"]
assert len(compiled_streaming["lod_samples"]) == 4
app.document.dirty = False
app.streaming_vars["enabled"].set(True)
app.streaming_changed()
assert app.document.dirty
app.show_streaming_runtime()
assert app.authoring_notebook.tab(app.authoring_notebook.select(), "text") == "Streaming"
# Branch 12 searchable Help must replace the placeholder, match context,
# open as a real desktop window, and navigate to related UI.
menu = app.nametowidget(app.cget("menu"))
help_menu = None
for i in range(menu.index("end") + 1):
    try:
        label = menu.entrycget(i, "label")
    except Exception:
        continue
    if label == "Help":
        help_menu = app.nametowidget(menu.entrycget(i, "menu"))
        break
assert help_menu is not None
labels = []
for i in range(help_menu.index("end") + 1):
    try:
        labels.append(help_menu.entrycget(i, "label"))
    except Exception:
        pass
assert "Editor Help Center" in labels
assert "Complete Authoring Guide" in labels
assert "Complete Mode Guide" in labels
assert "Detailed Tools Guide" in labels
assert "Help for Current Context" in labels
assert not any(str(label).startswith("Authoring Help Guide — Documentation Phase") for label in labels)
app.show_help_center("editor_overview", "editor")
app.update_idletasks(); app.update()
assert app.help_window is not None and app.help_window.winfo_exists()
assert app.help_current_topic is not None and app.help_current_topic.key == "editor_overview"
assert app.help_scope_key == "editor"
app._set_help_scope("all", refresh=True)
app.help_search_var.set("Signal Void")
app._refresh_help_results()
assert app.help_current_topic is not None and app.help_current_topic.key == "full_map_stability"
app._select_help_topic("encounter")
app._go_to_help_ui()
assert app.right_notebook.tab(app.right_notebook.select(), "text") == "Authoring"
assert app.authoring_notebook.tab(app.authoring_notebook.select(), "text") == "Encounter"
app.tool.set("brush")
app.show_tools_help()
app.update_idletasks(); app.update()
assert app.help_scope_key == "tools"
assert app.help_current_topic is not None and app.help_current_topic.key == "tool_brush"
app.show_mode_help_guide()
assert app.help_scope_key == "mode"
app._closing = True
app.destroy()
print("PASS: PCP3 Branch 12 R1 complete Editor, Mode, Tools and Authoring Help Center GUI startup")
PYX
fi

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/pcp3-sealed.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
"$PYTHON" - "$SCRATCH" <<'PY'
from pathlib import Path
import sys
from tools.pcp3.io import save_project
from tools.pcp3.model import PCPDocument, primitive_sphere
root = Path(sys.argv[1])
doc = PCPDocument.new("environment_object")
doc.asset_id = "sealed_validation_orb"
doc.display_name = "Sealed Validation Orb"
doc.author.creator_name = "PCP3 Quick Validation"
doc.points.extend(primitive_sphere((0,0,0), 1.0, 0.25, 1, (0.3,0.8,1.0,1.0), 2.0, "light"))
paths = save_project(doc, root / "sealed_validation_orb.pcp3")
print(paths["cloud"])
PY
"$ROOT/build-core/signalcloud_pcp3_asset_tests" "$ROOT" "$SCRATCH/sealed_validation_orb.pcp3cloud"

for script in scripts/*.sh; do
  bash -n "$script"
done

printf 'PASS: Point Cloud Paint++ Branch 12 R1 complete Editor, Mode, Tools and Authoring Help Center, nine mode tutorials, Streaming/LOD, responsive sidebar, bounded encounters, World Assembly, entity behavior, interaction, factory bridge, pipeline, C++ loaders, and launcher validation\n'
