from __future__ import annotations

import json
import math
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from tools.pcp3 import editor as base_editor
from tools.pcp3 import editor_branch2 as branch2
from tools.pcp3 import editor_branch2r2 as repair2
from tools.pcp3.brushes import BrushEditorWindow, BrushPreset, ensure_default_brushes, load_brush
from tools.pcp3.interaction import Pane, add, camera_basis, mul, perspective_project, perspective_ray_to_target_plane
from tools.pcp3.model import PCPPoint

TOOLS_R3 = tuple(item for item in branch2.TOOLS if item[0] != "window_sync") + (("window_sync", "Window Sync"),)
branch2.TOOLS = TOOLS_R3
branch2.TOOLS_DICT = dict(TOOLS_R3)
base_editor.TOOLS = TOOLS_R3
base_editor.TOOLS_DICT = dict(TOOLS_R3)

DEFAULT_VIEW = "3-Square"
DEFAULT_PROJECTION = "All X/Y/Z"
DEFAULT_GEOMETRY = "1420x900"
DEFAULT_LEFT_SASH = 170
DEFAULT_RIGHT_WIDTH = 330
DEPTH_SCAN_CHUNK = 20_000
MAX_DEPTH_MARKERS_PER_AXIS = 420


class PCP3Editor(repair2.PCP3Editor):
    """Branch 2 R3: persistent startup layout, depth navigation, sync, brush presets, and NP pan."""

    def __init__(self, root_path: Path) -> None:
        root_path = Path(root_path).resolve()
        initial_layout = repair2.PCP3Editor._read_layout_file(root_path)
        self._r3_initial_layout = initial_layout
        self._workspace_ready = False
        self._startup_rebuild_count = 0
        self._window_config_after: str | None = None
        self._depth_scan_after: str | None = None
        self._depth_scan_cursor = 0
        self._depth_scan_started = 0.0
        self._depth_scan_counts: dict[str, dict[float, int]] = {}
        self._depth_scan_steps: dict[str, float] = {}
        self._depth_scan_points: list[PCPPoint] = []
        self._depth_row_values: dict[str, tuple[str, float]] = {}
        self._depth_apply_after: str | None = None
        self.np_target = tuple(float(value) for value in initial_layout.get("np_target", [0.0, 0.0, 0.0])[:3])
        if len(self.np_target) != 3:
            self.np_target = (0.0, 0.0, 0.0)
        self.current_brush: BrushPreset = BrushPreset.round_soft()
        self.current_brush_path: Path | None = None
        self.brush_editor_window: BrushEditorWindow | None = None
        super().__init__(root_path)

        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 2 R3 Viewport Studio")
        self.document.metadata["editor_branch"] = "ISL_plus_branch2_R3"
        self.minsize(1180, 720)

        ensure_default_brushes(self.root_path)
        saved_brush = str(self.layout_data.get("current_brush", ""))
        if saved_brush:
            candidate = Path(saved_brush)
            if not candidate.is_absolute():
                candidate = self.root_path / candidate
            if candidate.is_file():
                try:
                    self.current_brush = load_brush(candidate)
                    self.current_brush_path = candidate
                except (OSError, ValueError, json.JSONDecodeError):
                    pass

        if not self.layout_data.get("np_target"):
            self.np_target = self._document_center()
        try:
            self.perspective_distance.set(float(self.layout_data.get("perspective_distance", self.perspective_distance.get())))
            self.rotate_x_degrees.set(float(self.layout_data.get("rotate_x", self.rotate_x_degrees.get())))
            self.rotate_y_degrees.set(float(self.layout_data.get("rotate_y", self.rotate_y_degrees.get())))
            self.roll_degrees.set(float(self.layout_data.get("roll_z", self.roll_degrees.get())))
        except (TypeError, ValueError, tk.TclError):
            pass

        default_view = str(self.layout_data.get("view_type", DEFAULT_VIEW))
        default_projection = str(self.layout_data.get("projection", DEFAULT_PROJECTION))
        if default_view not in branch2.VIEW_TYPES:
            default_view = DEFAULT_VIEW
        if default_projection not in branch2.PROJECTIONS:
            default_projection = DEFAULT_PROJECTION
        if not self.layout_data:
            default_view, default_projection = DEFAULT_VIEW, DEFAULT_PROJECTION
        self.view_type.set(default_view)
        self.projection.set(default_projection)

        self.bind("<Configure>", self._root_configured, add=True)
        for delay in (40, 180, 500):
            self.after(delay, self._finalize_startup_layout)
        self.after(250, self.schedule_depth_scan)
        self.update_status("R3 active · persistent three-pane startup · Depth navigation · custom .3dbrush masks")

    # ---------- top toolbar ----------
    def _build_toolbar(self) -> None:
        # Build the inherited Active Tool HUD, then replace only the command row.
        branch2.PCP3Editor._build_toolbar(self)
        children = self.winfo_children()
        if len(children) < 2:
            return
        active_toolbar = children[-1]
        old_bar = children[-2]
        old_bar.destroy()

        shell = ttk.Frame(self, padding=(8, 4))
        shell.pack(fill="x", before=active_toolbar)
        shell.columnconfigure(0, weight=1)

        command_center = ttk.Frame(shell)
        command_center.grid(row=0, column=0, pady=(0, 4))
        for text, command in (
            ("New", self.new_document),
            ("Open", self.open_project),
            ("Save", self.save),
            ("Export Asset", self.export_to_database),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Native Preview", self.launch_native_preview),
            ("Brush Editor", self.open_brush_editor),
            ("Tools Help", self.show_tools_help),
        ):
            ttk.Button(command_center, text=text, command=command).pack(side="left", padx=2)

        option_center = ttk.Frame(shell)
        option_center.grid(row=1, column=0, pady=(1, 0))

        def add_pair(label: str, variable: tk.Variable, values: tuple[str, ...], width: int, command: Any) -> None:
            group = ttk.Frame(option_center)
            group.pack(side="left", padx=5)
            ttk.Label(group, text=label).pack(side="left")
            box = ttk.Combobox(group, textvariable=variable, values=values, state="readonly", width=width)
            box.pack(side="left", padx=(3, 0))
            box.bind("<<ComboboxSelected>>", lambda _event: command())

        add_pair("Environment:", self.environment_type, branch2.ENVIRONMENT_TYPES, 18, self.change_environment_type)
        add_pair("View:", self.view_type, branch2.VIEW_TYPES, 10, self.view_type_changed)
        add_pair("Projection:", self.projection, branch2.PROJECTIONS, 15, self.projection_changed)
        add_pair("Display:", self.display_mode, branch2.DISPLAY_MODES, 9, self.redraw)
        if not hasattr(self, "viewport_quality"):
            self.viewport_quality = tk.StringVar(master=self, value=getattr(self, "_initial_viewport_quality", "Balanced"))
        add_pair("Viewport:", self.viewport_quality, ("Fast", "Balanced", "Detailed"), 9, self.viewport_quality_changed)
        ttk.Checkbutton(option_center, text="Live native refresh", variable=self.auto_live_preview).pack(side="left", padx=6)
        self.command_toolbar = shell

    # ---------- workspace additions ----------
    def _build_workspace(self) -> None:
        super()._build_workspace()
        self._insert_depth_tab()

    def _find_notebook(self, widget: tk.Misc) -> ttk.Notebook | None:
        for child in widget.winfo_children():
            if isinstance(child, ttk.Notebook):
                return child
            found = self._find_notebook(child)
            if found is not None:
                return found
        return None

    def _insert_depth_tab(self) -> None:
        notebook = self._find_notebook(self)
        if notebook is None:
            return
        self.right_notebook = notebook
        depth_tab = ttk.Frame(notebook, padding=6)
        notebook.insert(1, depth_tab, text="Depth")

        ttk.Label(
            depth_tab,
            text="Depth markers are generated from occupied X, Y, and Z slices. Select which windows move, then click a marker.",
            wraplength=290,
        ).pack(fill="x", pady=(0, 5))

        targets = ttk.LabelFrame(depth_tab, text="Move these windows", padding=4)
        targets.pack(fill="x")
        self.depth_target_vars = {
            "Top X/Z": tk.BooleanVar(value=True),
            "Front X/Y": tk.BooleanVar(value=False),
            "Side Z/Y": tk.BooleanVar(value=False),
            "Perspective 3D": tk.BooleanVar(value=False),
        }
        for text, key in (("Top", "Top X/Z"), ("Front", "Front X/Y"), ("Side", "Side Z/Y"), ("NP", "Perspective 3D")):
            ttk.Checkbutton(targets, text=text, variable=self.depth_target_vars[key], command=self._depth_target_changed).pack(side="left", padx=2)
        self.depth_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(targets, text="All", variable=self.depth_all, command=self._toggle_all_depth_targets).pack(side="right", padx=2)

        self.depth_tree = ttk.Treeview(depth_tab, columns=("depth", "points"), show="tree headings", height=18)
        self.depth_tree.heading("#0", text="Axis")
        self.depth_tree.heading("depth", text="Depth")
        self.depth_tree.heading("points", text="Points")
        self.depth_tree.column("#0", width=88, stretch=False)
        self.depth_tree.column("depth", width=100, anchor="e")
        self.depth_tree.column("points", width=90, anchor="e")
        self.depth_tree.pack(fill="both", expand=True, pady=5)
        self.depth_tree.bind("<<TreeviewSelect>>", self._depth_marker_selected)
        self.depth_tree.bind("<Double-Button-1>", lambda _event: self.go_to_selected_depth())

        row = ttk.Frame(depth_tab)
        row.pack(fill="x")
        ttk.Button(row, text="Go to selected depth", command=self.go_to_selected_depth).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Refresh", command=self.schedule_depth_scan).pack(side="left", padx=(4, 0))
        self.depth_status = tk.StringVar(value="Depth scan pending")
        ttk.Label(depth_tab, textvariable=self.depth_status, wraplength=290).pack(fill="x", pady=(5, 0))

    # ---------- robust startup and layout memory ----------
    def _root_configured(self, event: tk.Event) -> None:
        if event.widget is self and self._workspace_ready:
            self.schedule_layout_save()

    def _finalize_startup_layout(self) -> None:
        if self._closing or not self.winfo_exists():
            return
        self._startup_rebuild_count += 1
        expected = 3 if self.view_type.get() == "3-Square" else 4 if self.view_type.get() == "4-Square" else 1
        if len(self.pane_canvases) != expected:
            self.rebuild_viewport_layout()
        self.update_idletasks()
        self._restore_main_sashes()
        self._workspace_ready = True
        if self._startup_rebuild_count == 1:
            self.schedule_layout_save()

    def _restore_main_sashes(self) -> None:
        try:
            self.update_idletasks()
            width = max(900, int(self.main_paned.winfo_width()))
            left = int(self.layout_data.get("main_left_sash", DEFAULT_LEFT_SASH))
            right_width = int(self.layout_data.get("main_right_width", DEFAULT_RIGHT_WIDTH))
            left = max(135, min(width - 650, left))
            right = max(left + 520, min(width - 245, width - max(245, right_width)))
            self.main_paned.sashpos(0, left)
            self.main_paned.sashpos(1, right)
        except (AttributeError, tk.TclError, TypeError, ValueError):
            pass

    def save_workspace_layout(self) -> None:
        self._layout_save_after = None
        if self._closing or not self.winfo_exists() or not self._workspace_ready:
            return
        left_sash = DEFAULT_LEFT_SASH
        right_width = DEFAULT_RIGHT_WIDTH
        right_sash = 0
        try:
            left_sash = int(self.main_paned.sashpos(0))
            right_sash = int(self.main_paned.sashpos(1))
            right_width = max(220, self.winfo_width() - right_sash)
        except (AttributeError, tk.TclError):
            pass
        brush_value = ""
        if self.current_brush_path is not None:
            try:
                brush_value = str(self.current_brush_path.relative_to(self.root_path))
            except ValueError:
                brush_value = str(self.current_brush_path)
        data = {
            "schema": "pcp3_workspace_v2",
            "geometry": self.geometry(),
            "view_type": self.view_type.get(),
            "projection": self.projection.get(),
            "active_projection": self.active_projection,
            "main_left_sash": left_sash,
            "main_right_sash": right_sash,
            "main_right_width": right_width,
            "layer_scroll_axis": self.layer_scroll_axis.get(),
            "viewport_quality": self.viewport_quality.get(),
            "pane_states": {key: value.to_json() for key, value in self.pane_states.items()},
            "np_target": list(self.np_target),
            "perspective_distance": float(self.perspective_distance.get()),
            "rotate_x": float(self.rotate_x_degrees.get()),
            "rotate_y": float(self.rotate_y_degrees.get()),
            "roll_z": float(self.roll_degrees.get()),
            "current_brush": brush_value,
        }
        path = self.layout_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(path)
            self.layout_data = data
        except OSError:
            pass

    # ---------- NP perspective target and pan ----------
    def _document_center(self) -> tuple[float, float, float]:
        lower, upper = self.document.bounds()
        return tuple((lower[index] + upper[index]) * 0.5 for index in range(3))  # type: ignore[return-value]

    def view_target(self) -> tuple[float, float, float]:
        return self.np_target

    def world_to_screen(self, point: PCPPoint, pane: Pane | None = None) -> tuple[float, float]:
        pane = pane or self.pane_for_canvas(self.active_canvas)
        if pane.projection != "Perspective 3D":
            return super().world_to_screen(point, pane)
        state = self.state_for_pane(pane)
        projected = perspective_project(
            (point.x, point.y, point.z), pane, self.np_target,
            -45.0 + self.rotate_y_degrees.get(), 24.0 + self.rotate_x_degrees.get(),
            self.roll_degrees.get(), self.perspective_distance.get(),
        )
        if projected is None:
            return -100000.0, -100000.0
        return projected[0] + state.pan_x, projected[1] + state.pan_y

    def screen_to_world(self, sx: float, sy: float, pane: Pane | None = None) -> tuple[float, float, float]:
        pane = pane or self.pane_for_canvas(self.active_canvas)
        if pane.projection != "Perspective 3D":
            return super().screen_to_world(sx, sy, pane)
        state = self.state_for_pane(pane)
        return perspective_ray_to_target_plane(
            sx - state.pan_x, sy - state.pan_y, pane, self.np_target,
            -45.0 + self.rotate_y_degrees.get(), 24.0 + self.rotate_x_degrees.get(),
            self.roll_degrees.get(), self.perspective_distance.get(),
        )

    def point_depth(self, point: PCPPoint, pane: Pane | None = None) -> float:
        pane = pane or self.pane_for_canvas(self.active_canvas)
        if pane.projection != "Perspective 3D":
            return super().point_depth(point, pane)
        projected = perspective_project(
            (point.x, point.y, point.z), pane, self.np_target,
            -45.0 + self.rotate_y_degrees.get(), 24.0 + self.rotate_x_degrees.get(),
            self.roll_degrees.get(), self.perspective_distance.get(),
        )
        return projected[2] if projected else 1e9

    def frame_all(self) -> None:
        self.np_target = self._document_center()
        super().frame_all()

    # ---------- Window Sync tool ----------
    def canvas_press(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        if self.tool.get() == "window_sync":
            self.sync_windows_from_event(event)
            return
        super().canvas_press(event)

    def canvas_drag(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        if self.tool.get() == "window_sync":
            self.sync_windows_from_event(event)
            return
        super().canvas_drag(event)

    def canvas_release(self, event: tk.Event) -> None:
        if self.tool.get() == "window_sync":
            self.schedule_layout_save()
            return
        super().canvas_release(event)

    def sync_windows_from_event(self, event: tk.Event) -> None:
        canvas = event.widget if isinstance(event.widget, tk.Canvas) else self.active_canvas
        if canvas is None:
            return
        source_pane = self.pane_for_canvas(canvas)
        source_world = self.screen_to_world(event.x, event.y, source_pane)
        source_state = self.state_for_pane(source_pane)
        if source_pane.projection == "Perspective 3D":
            common_zoom = max(2.0, min(400.0, 420.0 / max(1.0, self.perspective_distance.get())))
        else:
            common_zoom = source_state.zoom
            self.perspective_distance.set(max(1.0, min(5000.0, 420.0 / max(2.0, common_zoom))))
        x, y, z = source_world
        for projection, state in self.pane_states.items():
            state.zoom = common_zoom
            if projection == "Top X/Z":
                state.depth = y
                state.pan_x = -x * common_zoom
                state.pan_y = z * common_zoom
            elif projection == "Front X/Y":
                state.depth = z
                state.pan_x = -x * common_zoom
                state.pan_y = y * common_zoom
            elif projection == "Side Z/Y":
                state.depth = x
                state.pan_x = -z * common_zoom
                state.pan_y = y * common_zoom
            else:
                state.pan_x = 0.0
                state.pan_y = 0.0
        self.np_target = source_world
        active = self.pane_states[self.active_projection]
        self._syncing_depth = True
        self.depth_value.set(active.depth)
        self.zoom.set(active.zoom)
        self._syncing_depth = False
        self.redraw()
        self.schedule_layout_save()
        self.update_status(f"Window Sync centered every pane on x {x:.2f}, y {y:.2f}, z {z:.2f}")

    # ---------- Depth index ----------
    def _toggle_all_depth_targets(self) -> None:
        value = self.depth_all.get()
        for variable in self.depth_target_vars.values():
            variable.set(value)

    def _depth_target_changed(self) -> None:
        self.depth_all.set(all(variable.get() for variable in self.depth_target_vars.values()))

    def schedule_depth_scan(self, delay: int = 250) -> None:
        if not hasattr(self, "depth_tree"):
            return
        if self._depth_scan_after is not None:
            try:
                self.after_cancel(self._depth_scan_after)
            except tk.TclError:
                pass
        self._depth_scan_after = self.after(delay, self._start_depth_scan)

    def _start_depth_scan(self) -> None:
        self._depth_scan_after = None
        self._depth_scan_points = list(self.document.points)
        self._depth_scan_cursor = 0
        self._depth_scan_started = time.monotonic()
        lower, upper = self.document.bounds()
        base = max(0.05, float(self.document.settings.grid_spacing), float(self.brush_spacing.get()))
        self._depth_scan_steps = {
            "X": max(base, (upper[0] - lower[0]) / MAX_DEPTH_MARKERS_PER_AXIS if upper[0] > lower[0] else base),
            "Y": max(base, (upper[1] - lower[1]) / MAX_DEPTH_MARKERS_PER_AXIS if upper[1] > lower[1] else base),
            "Z": max(base, (upper[2] - lower[2]) / MAX_DEPTH_MARKERS_PER_AXIS if upper[2] > lower[2] else base),
        }
        self._depth_scan_counts = {"X": {}, "Y": {}, "Z": {}}
        self.depth_status.set(f"Scanning {len(self._depth_scan_points):,} points…")
        self._depth_scan_chunk()

    def _depth_scan_chunk(self) -> None:
        end = min(len(self._depth_scan_points), self._depth_scan_cursor + DEPTH_SCAN_CHUNK)
        for point in self._depth_scan_points[self._depth_scan_cursor:end]:
            for axis, value in (("X", point.x), ("Y", point.y), ("Z", point.z)):
                step = self._depth_scan_steps[axis]
                marker = round(value / step) * step
                marker = round(marker, 6)
                self._depth_scan_counts[axis][marker] = self._depth_scan_counts[axis].get(marker, 0) + 1
        self._depth_scan_cursor = end
        if end < len(self._depth_scan_points):
            percent = 100.0 * end / max(1, len(self._depth_scan_points))
            elapsed = time.monotonic() - self._depth_scan_started
            self.depth_status.set(f"Scanning depths · {percent:.0f}% · {elapsed:.1f}s")
            self._depth_scan_after = self.after(1, self._depth_scan_chunk)
            return
        self._populate_depth_tree()

    def _populate_depth_tree(self) -> None:
        self.depth_tree.delete(*self.depth_tree.get_children())
        self._depth_row_values.clear()
        for axis in ("X", "Y", "Z"):
            parent = self.depth_tree.insert("", "end", text=f"{axis} depth", values=("", sum(self._depth_scan_counts[axis].values())), open=axis == "Y")
            for depth, count in sorted(self._depth_scan_counts[axis].items()):
                item = self.depth_tree.insert(parent, "end", text=axis, values=(f"{depth:.4f}", f"{count:,}"))
                self._depth_row_values[item] = (axis, depth)
        elapsed = time.monotonic() - self._depth_scan_started
        marker_count = sum(len(values) for values in self._depth_scan_counts.values())
        self.depth_status.set(f"{marker_count:,} occupied depth markers · scan {elapsed:.2f}s")
        self._depth_scan_points = []
        self._depth_scan_after = None

    def _depth_marker_selected(self, _event: tk.Event) -> None:
        if self._depth_apply_after is not None:
            try:
                self.after_cancel(self._depth_apply_after)
            except tk.TclError:
                pass
        self._depth_apply_after = self.after(120, self.go_to_selected_depth)

    def go_to_selected_depth(self) -> None:
        self._depth_apply_after = None
        selection = self.depth_tree.selection()
        if not selection or selection[0] not in self._depth_row_values:
            return
        axis, depth = self._depth_row_values[selection[0]]
        selected_targets = [key for key, variable in self.depth_target_vars.items() if variable.get()]
        if not selected_targets:
            selected_targets = {"X": ["Side Z/Y"], "Y": ["Top X/Z"], "Z": ["Front X/Y"]}[axis]
        for projection in selected_targets:
            if projection == "Perspective 3D":
                target = list(self.np_target)
                target[{"X": 0, "Y": 1, "Z": 2}[axis]] = depth
                self.np_target = tuple(target)  # type: ignore[assignment]
            else:
                self.pane_states[projection].depth = depth
        if self.active_projection in self.pane_states:
            self._syncing_depth = True
            self.depth_value.set(self.pane_states[self.active_projection].depth)
            self._syncing_depth = False
        self.redraw()
        self.schedule_layout_save()
        self.update_status(f"Depth {axis} {depth:.4f} applied to {', '.join(selected_targets)}")

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        if hasattr(self, "depth_tree"):
            self.schedule_depth_scan()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if hasattr(self, "depth_tree"):
            self.schedule_depth_scan(500)

    # ---------- 3D Brush Editor ----------
    def open_brush_editor(self) -> None:
        if self.brush_editor_window is None or not self.brush_editor_window.winfo_exists():
            self.brush_editor_window = BrushEditorWindow(self, self.root_path, self.current_brush, self.apply_3d_brush)
        else:
            self.brush_editor_window.deiconify()
            self.brush_editor_window.lift()
            self.brush_editor_window.focus_force()

    def apply_3d_brush(self, brush: BrushPreset, path: Path | None) -> None:
        self.current_brush = brush.normalized()
        self.current_brush_path = path
        self.tool.set("brush")
        self.update_tool_hud()
        self.schedule_layout_save()
        self.update_status(f"3D Brush active: {self.current_brush.name} · {len(self.current_brush.active_pixels()):,} mask dots")

    def _mask_points(self) -> list[tuple[int, int, float]]:
        return self.current_brush.active_pixels(limit=512)

    def brush_points(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        pane = self.active_event_pane or self.pane_for_canvas(self.active_canvas)
        if pane.projection == "Perspective 3D":
            return self.brush_points_3d(world)
        active = self._mask_points()
        if not active:
            return []
        radius = max(0.02, self.brush_size.get())
        width = max(1, self.current_brush.width - 1)
        height = max(1, self.current_brush.height - 1)
        hardness = max(0.0, min(1.0, self.brush_hardness.get()))
        points: list[PCPPoint] = []
        for column, row, mask_alpha in active:
            da = ((column / width) - 0.5) * 2.0 * radius
            db = ((row / height) - 0.5) * -2.0 * radius
            x, y, z = world
            if pane.projection.startswith("Top"):
                x += da
                z += db
            elif pane.projection.startswith("Front"):
                x += da
                y += db
            else:
                z += da
                y += db
            alpha = max(0.01, min(1.0, mask_alpha * (0.35 + 0.65 * hardness)))
            point = self.make_point(x, y, z, density=alpha)
            point.a *= alpha
            points.append(point)
        return points

    def brush_points_3d(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        active = self._mask_points()
        if not active:
            return []
        _forward, right, up = camera_basis(
            -45.0 + self.rotate_y_degrees.get(), 24.0 + self.rotate_x_degrees.get(), self.roll_degrees.get()
        )
        radius = max(0.02, self.brush_size.get())
        width = max(1, self.current_brush.width - 1)
        height = max(1, self.current_brush.height - 1)
        hardness = max(0.0, min(1.0, self.brush_hardness.get()))
        points: list[PCPPoint] = []
        for column, row, mask_alpha in active:
            da = ((column / width) - 0.5) * 2.0 * radius
            db = ((row / height) - 0.5) * -2.0 * radius
            offset = add(mul(right, da), mul(up, db))
            alpha = max(0.01, min(1.0, mask_alpha * (0.35 + 0.65 * hardness)))
            point = self.make_point(world[0] + offset[0], world[1] + offset[1], world[2] + offset[2], density=alpha)
            point.a *= alpha
            points.append(point)
        return points

    # ---------- tools help/status ----------
    def tool_help(self, key: str) -> str:
        if key == "window_sync":
            return "Click or drag in any pane to align Top, Front, Side, and NP on the same 3D point, depth, and zoom."
        return super().tool_help(key)

    def show_tools_help(self) -> None:
        before = set(self.winfo_children())
        super().show_tools_help()
        created = [child for child in self.winfo_children() if child not in before and isinstance(child, tk.Toplevel)]
        if not created:
            return
        def find_text(widget: tk.Misc) -> tk.Text | None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Text):
                    return child
                found = find_text(child)
                if found is not None:
                    return found
            return None
        text = find_text(created[-1])
        if text is None:
            return
        text.configure(state="normal")
        text.insert("end", "Window Sync\n", "heading")
        text.insert("end", self.tool_help("window_sync") + " Select another tool after the views are aligned.\n\n")
        text.insert("end", "Depth Tab\n", "heading")
        text.insert("end", "Lists occupied X, Y, and Z slices. Choose Top, Front, Side, NP, or All and click a marker to move those windows.\n\n")
        text.insert("end", "3D Brush Editor\n", "heading")
        text.insert("end", "Use the top Brush Editor button to create layered .3dbrush pixel-dot masks. Apply swaps the active 3D brush without changing the PCP3 asset format.\n\n")
        text.configure(state="disabled")

    def _activate_canvas(self, widget: tk.Misc, *, redraw: bool = True) -> None:
        previous = getattr(self, "active_projection", "")
        super()._activate_canvas(widget, redraw=redraw)
        if self._workspace_ready and previous != self.active_projection:
            self.schedule_layout_save()

    def update_tool_hud(self) -> None:
        super().update_tool_hud()
        if self.tool.get() == "window_sync":
            self.update_status("Window Sync: click or drag in any pane to align every pane to the same 3D point")

    def on_close(self) -> None:
        if self._closing:
            return
        self.save_workspace_layout()
        try:
            if not self.confirm_discard():
                return
        except tk.TclError:
            pass
        self._closing = True
        self._cancel_render_jobs()
        for after_id in (
            self.preview_poll_after,
            self.preview_write_after,
            self._busy_tick_after,
            self._layout_save_after,
            self._window_config_after,
            self._depth_scan_after,
            self._depth_apply_after,
        ):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        if self.brush_editor_window is not None and self.brush_editor_window.winfo_exists():
            try:
                self.brush_editor_window.destroy()
            except tk.TclError:
                pass
        try:
            self.unbind("<Configure>")
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
