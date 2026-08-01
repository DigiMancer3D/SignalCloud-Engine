from __future__ import annotations

import math
import random
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from tools.pcp3 import editor_branch2 as branch2
from tools.pcp3 import editor_branch2r1 as repair1
from tools.pcp3.interaction import Pane, inverse_rotate_xyz, perspective_project, perspective_ray_to_target_plane, rotate_xyz
from tools.pcp3.model import PCPPoint
from tools.signalcloud_studio.ui import FlowBar
from tools.signalcloud_studio.workspace import PaneState, WorkspaceLayoutStore


DEFAULT_GEOMETRY = "1420x900"
DEFAULT_LEFT_SASH = 170
DEFAULT_RIGHT_WIDTH = 330
SINGLE_POINT_BUDGET = 6_000
THREE_PANE_BUDGET = 3_000
FOUR_PANE_BUDGET = 2_800
FAST_ACTIVE_BUDGET = 450
RENDER_CHUNK = 180



class PCP3Editor(repair1.PCP3Editor):
    """Branch 2 R2: independent multi-pane planes, async rendering, and remembered layout."""

    def __init__(self, root_path: Path) -> None:
        self.layout_data = self._read_layout_file(Path(root_path))
        self.pane_states: dict[str, PaneState] = {
            projection: PaneState.from_json(self.layout_data.get("pane_states", {}).get(projection))
            for projection in ("Top X/Z", "Front X/Y", "Side Z/Y", "Perspective 3D")
        }
        self.pane_canvases: dict[str, tk.Canvas] = {}
        self.canvas_projection: dict[tk.Canvas, str] = {}
        self.canvas_name: dict[tk.Canvas, str] = {}
        self.active_canvas: tk.Canvas | None = None
        self.active_projection = str(self.layout_data.get("active_projection", "Top X/Z"))
        if self.active_projection not in self.pane_states:
            self.active_projection = "Top X/Z"
        self._syncing_depth = False
        self._event_canvas: tk.Canvas | None = None
        self._render_token = 0
        self._render_jobs: dict[tk.Canvas, dict[str, Any]] = {}
        self._render_after: dict[tk.Canvas, str] = {}
        self._render_started = 0.0
        self._busy_tick_after: str | None = None
        self._layout_save_after: str | None = None
        self._closing = False
        self._stroke_projection: str | None = None
        self._geometry_revision = 0
        self._view_target_cache: tuple[tuple[int, int], tuple[float, float, float]] | None = None
        self._initial_layer_scroll_axis = str(self.layout_data.get("layer_scroll_axis", "x"))
        if self._initial_layer_scroll_axis not in {"x", "y"}:
            self._initial_layer_scroll_axis = "x"
        self._initial_viewport_quality = str(self.layout_data.get("viewport_quality", "Balanced"))
        if self._initial_viewport_quality not in {"Fast", "Balanced", "Detailed"}:
            self._initial_viewport_quality = "Balanced"
        self._last_preview_write = 0.0
        super().__init__(Path(root_path))
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 2 R2 Multi-View Repair")
        self.document.metadata["editor_branch"] = "ISL_plus_branch2_R2"
        geometry = str(self.layout_data.get("geometry", DEFAULT_GEOMETRY))
        try:
            self.geometry(geometry)
        except tk.TclError:
            self.geometry(DEFAULT_GEOMETRY)
        saved_view = str(self.layout_data.get("view_type", "Single"))
        saved_projection = str(self.layout_data.get("projection", "Top X/Z"))
        if saved_view in branch2.VIEW_TYPES:
            self.view_type.set(saved_view)
        if saved_projection in branch2.PROJECTIONS:
            self.projection.set(saved_projection)
        self.rebuild_viewport_layout()
        self.after(150, self._restore_main_sashes)
        self.update_status(
            "R2 active · independent X/Y/Z edit planes · deferred inactive views · live render progress"
        )


    # ---------- geometry cache ----------
    def _invalidate_geometry_cache(self) -> None:
        self._geometry_revision += 1
        self._view_target_cache = None

    def view_target(self) -> tuple[float, float, float]:
        key = (len(self.document.points), self._geometry_revision)
        if self._view_target_cache is not None and self._view_target_cache[0] == key:
            return self._view_target_cache[1]
        lower, upper = self.document.bounds()
        target = tuple((lower[index] + upper[index]) * 0.5 for index in range(3))
        self._view_target_cache = (key, target)
        return target  # type: ignore[return-value]

    def _sync_all_from_document(self) -> None:
        self._invalidate_geometry_cache()
        super()._sync_all_from_document()

    def finish_edit(self, label: str) -> None:
        self._invalidate_geometry_cache()
        super().finish_edit(label)

    # ---------- persisted layout ----------
    @staticmethod
    def _layout_path_for(root_path: Path) -> Path:
        return root_path.resolve() / "config" / "pcp3_workspace.json"

    @classmethod
    def _read_layout_file(cls, root_path: Path) -> dict[str, Any]:
        return WorkspaceLayoutStore(cls._layout_path_for(root_path)).read()

    def layout_path(self) -> Path:
        return self._layout_path_for(self.root_path)

    def schedule_layout_save(self) -> None:
        if self._layout_save_after is not None:
            try:
                self.after_cancel(self._layout_save_after)
            except tk.TclError:
                pass
        self._layout_save_after = self.after(300, self.save_workspace_layout)

    def save_workspace_layout(self) -> None:
        self._layout_save_after = None
        if self._closing or not self.winfo_exists():
            return
        left_sash = DEFAULT_LEFT_SASH
        right_width = DEFAULT_RIGHT_WIDTH
        try:
            left_sash = int(self.main_paned.sashpos(0))
            right_width = max(220, self.winfo_width() - int(self.main_paned.sashpos(1)))
        except (AttributeError, tk.TclError):
            pass
        data = {
            "schema": "pcp3_workspace_v1",
            "geometry": self.geometry(),
            "view_type": self.view_type.get(),
            "projection": self.projection.get(),
            "active_projection": self.active_projection,
            "main_left_sash": left_sash,
            "main_right_width": right_width,
            "layer_scroll_axis": self.layer_scroll_axis.get(),
            "viewport_quality": self.viewport_quality.get(),
            "pane_states": {key: value.to_json() for key, value in self.pane_states.items()},
        }
        try:
            WorkspaceLayoutStore(self.layout_path()).write(data)
        except OSError:
            pass

    def _restore_main_sashes(self) -> None:
        try:
            width = max(900, self.main_paned.winfo_width())
            left = int(self.layout_data.get("main_left_sash", DEFAULT_LEFT_SASH))
            right_width = int(self.layout_data.get("main_right_width", DEFAULT_RIGHT_WIDTH))
            self.main_paned.sashpos(0, max(120, min(width - 520, left)))
            self.main_paned.sashpos(1, max(left + 420, min(width - 220, width - right_width)))
        except (AttributeError, tk.TclError, ValueError):
            pass

    # ---------- responsive top toolbar ----------
    def _build_toolbar(self) -> None:
        if not hasattr(self, "viewport_quality"):
            self.viewport_quality = tk.StringVar(master=self, value=self._initial_viewport_quality)
        super()._build_toolbar()
        children = self.winfo_children()
        if len(children) < 2:
            return
        active_toolbar = children[-1]
        old_bar = children[-2]
        old_bar.destroy()
        bar = FlowBar(self, padding=(8, 4))
        bar.pack(fill="x", before=active_toolbar)
        self.command_flow_bar = bar

        for text, command in (
            ("New", self.new_document),
            ("Open", self.open_project),
            ("Save", self.save),
            ("Export Asset", self.export_to_database),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Native Preview", self.launch_native_preview),
            ("Tools Help", self.show_tools_help),
        ):
            group = bar.group()
            ttk.Button(group, text=text, command=command).pack()

        def paired(label: str, variable: tk.Variable, values: tuple[str, ...], width: int, callback: Callable[[], None]) -> None:
            group = bar.group()
            ttk.Label(group, text=label).pack(side="left")
            box = ttk.Combobox(group, textvariable=variable, values=values, state="readonly", width=width)
            box.pack(side="left", padx=(4, 0))
            box.bind("<<ComboboxSelected>>", lambda _event: callback())

        paired("Environment:", self.environment_type, branch2.ENVIRONMENT_TYPES, 18, self.change_environment_type)
        paired("View:", self.view_type, branch2.VIEW_TYPES, 10, self.view_type_changed)
        paired("Projection:", self.projection, branch2.PROJECTIONS, 15, self.projection_changed)
        paired("Display:", self.display_mode, branch2.DISPLAY_MODES, 9, self.redraw)
        paired("Viewport:", self.viewport_quality, ("Fast", "Balanced", "Detailed"), 9, self.viewport_quality_changed)
        live_group = bar.group()
        ttk.Checkbutton(live_group, text="Live native refresh", variable=self.auto_live_preview).pack()

    # ---------- workspace replacement ----------
    def _build_workspace(self) -> None:
        if not hasattr(self, "layer_scroll_axis"):
            self.layer_scroll_axis = tk.StringVar(master=self, value=self._initial_layer_scroll_axis)
        if not hasattr(self, "render_status"):
            self.render_status = tk.StringVar(master=self, value="Viewport ready")
        if not hasattr(self, "render_progress"):
            self.render_progress = tk.DoubleVar(master=self, value=0.0)
        super()._build_workspace()
        old_canvas = self.canvas
        center = old_canvas.master
        self.main_paned = center.master  # type: ignore[assignment]
        try:
            self.main_paned.bind("<ButtonRelease-1>", lambda _event: self.schedule_layout_save(), add=True)
        except tk.TclError:
            pass

        canvas_toolbar = center.winfo_children()[0]
        for child in canvas_toolbar.winfo_children():
            child.destroy()
        ttk.Label(canvas_toolbar, text="Active pane depth:").pack(side="left")
        self.depth_scale = ttk.Scale(
            canvas_toolbar,
            from_=-50.0,
            to=50.0,
            variable=self.depth_value,
            command=self.depth_changed,
        )
        self.depth_scale.pack(side="left", fill="x", expand=True, padx=6)
        self.busy_progress = ttk.Progressbar(
            canvas_toolbar,
            variable=self.render_progress,
            maximum=100.0,
            length=130,
        )
        self.busy_progress.pack(side="right", padx=(6, 0))
        ttk.Label(canvas_toolbar, textvariable=self.render_status, width=34).pack(side="right", padx=5)
        ttk.Label(canvas_toolbar, textvariable=self.coords_text, width=28).pack(side="right")

        old_canvas.destroy()
        self.viewport_host = ttk.Frame(center)
        self.viewport_host.pack(fill="both", expand=True)
        self.viewport_host.bind("<Configure>", self._viewport_host_configured)

        self._rebuild_layer_tree()

    def _rebuild_layer_tree(self) -> None:
        old_tree = self.layer_tree
        parent = old_tree.master
        siblings = parent.winfo_children()
        layer_buttons = next((child for child in siblings if isinstance(child, ttk.Frame) and child is not old_tree), None)
        old_tree.destroy()
        frame = ttk.Frame(parent)
        if layer_buttons is not None:
            frame.pack(fill="both", expand=True, before=layer_buttons)
        else:
            frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("visible", "semantic", "points"), show="tree headings", height=14)
        tree.heading("#0", text="Layer")
        tree.heading("visible", text="Visibility")
        tree.heading("semantic", text="Semantic")
        tree.heading("points", text="Points")
        tree.column("#0", width=170, minwidth=120, stretch=False)
        tree.column("visible", width=86, minwidth=75, anchor="center", stretch=False)
        tree.column("semantic", width=140, minwidth=100, stretch=False)
        tree.column("points", width=90, minwidth=65, anchor="e", stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        controls = ttk.Frame(frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.layer_axis_x = tk.BooleanVar(value=self.layer_scroll_axis.get() == "x")
        self.layer_axis_y = tk.BooleanVar(value=self.layer_scroll_axis.get() == "y")
        ttk.Label(controls, text="Scroll direction:").pack(side="left")
        ttk.Checkbutton(controls, text="X", variable=self.layer_axis_x, command=lambda: self.set_layer_scroll_axis("x")).pack(side="left")
        ttk.Checkbutton(controls, text="Y", variable=self.layer_axis_y, command=lambda: self.set_layer_scroll_axis("y")).pack(side="left")
        self.layer_shared_scroll = ttk.Scrollbar(frame, orient="horizontal")
        self.layer_shared_scroll.grid(row=2, column=0, sticky="ew")
        self.layer_tree = tree
        tree.bind("<<TreeviewSelect>>", self.layer_selected)
        tree.bind("<Button-1>", self.layer_row_click, add=True)
        tree.bind("<Double-Button-1>", self.layer_toggle_visible, add=True)
        self.apply_layer_scroll_axis()

    def set_layer_scroll_axis(self, axis: str) -> None:
        self.layer_scroll_axis.set("y" if axis == "y" else "x")
        self.layer_axis_x.set(self.layer_scroll_axis.get() == "x")
        self.layer_axis_y.set(self.layer_scroll_axis.get() == "y")
        self.apply_layer_scroll_axis()
        self.schedule_layout_save()

    def apply_layer_scroll_axis(self) -> None:
        if self.layer_scroll_axis.get() == "y":
            self.layer_shared_scroll.configure(command=self.layer_tree.yview)
            self.layer_tree.configure(xscrollcommand="", yscrollcommand=self.layer_shared_scroll.set)
        else:
            self.layer_shared_scroll.configure(command=self.layer_tree.xview)
            self.layer_tree.configure(xscrollcommand=self.layer_shared_scroll.set, yscrollcommand="")

    # ---------- independent pane construction ----------
    def view_type_changed(self) -> None:
        if self.view_type.get() == "3-Square":
            self.projection.set("All X/Y/Z")
        elif self.view_type.get() == "4-Square":
            self.projection.set("All X/Y/Z/NP")
        elif self.projection.get().startswith("All "):
            self.projection.set(self.active_projection if self.active_projection != "Perspective 3D" else "Top X/Z")
        self.rebuild_viewport_layout()
        self.schedule_layout_save()

    def projection_changed(self) -> None:
        projection = self.projection.get()
        if projection == "All X/Y/Z":
            self.view_type.set("3-Square")
        elif projection == "All X/Y/Z/NP":
            self.view_type.set("4-Square")
        else:
            self.view_type.set("Single")
            if projection in self.pane_states:
                self.active_projection = projection
        self.rebuild_viewport_layout()
        self.schedule_layout_save()

    def viewport_quality_changed(self) -> None:
        self.schedule_layout_save()
        self.redraw()

    def _pane_definitions(self) -> list[tuple[str, str]]:
        view = self.view_type.get()
        if view == "3-Square":
            return [
                ("X axis · Side Z/Y", "Side Z/Y"),
                ("Y axis · Top X/Z", "Top X/Z"),
                ("Z axis · Front X/Y", "Front X/Y"),
            ]
        if view == "4-Square":
            return [
                ("Z axis · Front X/Y", "Front X/Y"),
                ("Y axis · Top X/Z", "Top X/Z"),
                ("X axis · Side Z/Y", "Side Z/Y"),
                ("NP · Perspective editing bridge", "Perspective 3D"),
            ]
        projection = self.projection.get()
        if projection.startswith("All ") or projection not in self.pane_states:
            projection = "Top X/Z"
        return [(projection, projection)]

    def rebuild_viewport_layout(self) -> None:
        if not hasattr(self, "viewport_host"):
            return
        self._cancel_render_jobs()
        for child in self.viewport_host.winfo_children():
            child.destroy()
        self.pane_canvases.clear()
        self.canvas_projection.clear()
        self.canvas_name.clear()
        for index, (name, projection) in enumerate(self._pane_definitions()):
            canvas = tk.Canvas(
                self.viewport_host,
                background="#0d1115",
                highlightthickness=2,
                highlightbackground="#35424a",
                highlightcolor="#6eb4d2",
                cursor="crosshair",
            )
            key = f"pane_{index}_{projection}"
            self.pane_canvases[key] = canvas
            self.canvas_projection[canvas] = projection
            self.canvas_name[canvas] = name
            self._bind_pane_canvas(canvas)
        self._position_canvases()
        if self.active_projection not in {projection for _name, projection in self._pane_definitions()}:
            self.active_projection = self._pane_definitions()[0][1]
        self.active_canvas = next(
            (canvas for canvas, projection in self.canvas_projection.items() if projection == self.active_projection),
            next(iter(self.pane_canvases.values()), None),
        )
        if self.active_canvas is not None:
            self._activate_canvas(self.active_canvas, redraw=False)
        self.redraw()

    def _position_canvases(self) -> None:
        if not self.pane_canvases:
            return
        canvases = list(self.pane_canvases.values())
        view = self.view_type.get()
        expected = 4 if view == "4-Square" else 3 if view == "3-Square" else 1
        # Configure events may fire while rebuild_viewport_layout is still creating
        # the remaining independent canvases. Wait for the complete set instead of
        # indexing a partially constructed pane list.
        if len(canvases) < expected:
            return
        if view == "4-Square":
            for canvas, relx, rely in zip(canvases, (0.0, 0.5, 0.0, 0.5), (0.0, 0.0, 0.5, 0.5)):
                canvas.place(relx=relx, rely=rely, relwidth=0.5, relheight=0.5)
        elif view == "3-Square":
            canvases[0].place(relx=0.0, rely=0.0, relwidth=0.5, relheight=0.5)
            canvases[1].place(relx=0.5, rely=0.0, relwidth=0.5, relheight=0.5)
            canvases[2].place(relx=0.25, rely=0.5, relwidth=0.5, relheight=0.5)
        else:
            canvases[0].place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)

    def _viewport_host_configured(self, _event: tk.Event) -> None:
        self._position_canvases()
        self.redraw()

    def _bind_pane_canvas(self, canvas: tk.Canvas) -> None:
        canvas.bind("<Configure>", lambda _event, c=canvas: self.schedule_pane_render(c))
        canvas.bind("<ButtonPress-1>", self.canvas_press)
        canvas.bind("<Double-Button-1>", self.canvas_double_left)
        canvas.bind("<B1-Motion>", self.canvas_drag)
        canvas.bind("<ButtonRelease-1>", self.canvas_release)
        canvas.bind("<ButtonPress-3>", self.canvas_right_press)
        canvas.bind("<Double-Button-3>", self.canvas_double_right)
        canvas.bind("<B3-Motion>", self.canvas_right_drag)
        canvas.bind("<ButtonRelease-3>", self.canvas_right_release)
        canvas.bind("<ButtonPress-2>", self.pan_press)
        canvas.bind("<B2-Motion>", self.pan_drag)
        canvas.bind("<ButtonRelease-2>", lambda _event: setattr(self, "pan_anchor", None))
        canvas.bind("<MouseWheel>", self.mouse_wheel)
        canvas.bind("<Button-4>", lambda event: self.mouse_wheel_linux(event, 1))
        canvas.bind("<Button-5>", lambda event: self.mouse_wheel_linux(event, -1))
        canvas.bind("<Motion>", self.canvas_motion)
        canvas.bind("<Enter>", lambda event: self._activate_canvas(event.widget, redraw=False))

    def _activate_canvas(self, widget: tk.Misc, *, redraw: bool = True) -> None:
        if not isinstance(widget, tk.Canvas) or widget not in self.canvas_projection:
            return
        old_projection = self.active_projection
        self.active_canvas = widget
        self.canvas = widget
        self._event_canvas = widget
        self.active_projection = self.canvas_projection[widget]
        self.active_event_pane = self.pane_for_canvas(widget)
        state = self.pane_states[self.active_projection]
        self._syncing_depth = True
        self.depth_value.set(state.depth)
        self.zoom.set(state.zoom)
        self.pan_x = state.pan_x
        self.pan_y = state.pan_y
        self._syncing_depth = False
        if old_projection != self.active_projection:
            self.stroke_last_world = None
            self._stroke_projection = None
        for canvas in self.canvas_projection:
            canvas.configure(highlightbackground="#6eb4d2" if canvas is widget else "#35424a")
        if redraw:
            self.schedule_pane_render(widget, fast=True)

    def pane_for_canvas(self, canvas: tk.Canvas | None) -> Pane:
        if canvas is None or canvas not in self.canvas_projection:
            canvas = self.active_canvas or next(iter(self.pane_canvases.values()))
        projection = self.canvas_projection[canvas]
        return Pane(
            self.canvas_name[canvas],
            projection,
            0.0,
            0.0,
            max(1.0, float(canvas.winfo_width())),
            max(1.0, float(canvas.winfo_height())),
        )

    def panes(self) -> list[Pane]:
        return [self.pane_for_canvas(canvas) for canvas in self.pane_canvases.values()]

    def pane_at(self, _sx: float, _sy: float) -> Pane:
        return self.pane_for_canvas(self._event_canvas or self.active_canvas)

    def state_for_pane(self, pane: Pane) -> PaneState:
        return self.pane_states[pane.projection]

    def depth_changed(self, _value: str | None = None) -> None:
        if self._syncing_depth:
            return
        state = self.pane_states[self.active_projection]
        state.depth = float(self.depth_value.get())
        if self.active_canvas is not None:
            self.schedule_pane_render(self.active_canvas, fast=True)
        self.schedule_layout_save()

    # ---------- flat axis mapping ----------
    def _axis_is_locked(self, pane: Pane) -> bool:
        return self.view_type.get() != "Single" and pane.projection != "Perspective 3D"

    def world_to_screen(self, point: PCPPoint, pane: Pane | None = None) -> tuple[float, float]:
        pane = pane or self.pane_for_canvas(self.active_canvas)
        state = self.state_for_pane(pane)
        if pane.projection == "Perspective 3D":
            projected = perspective_project(
                (point.x, point.y, point.z), pane, self.view_target(),
                -45.0 + self.rotate_y_degrees.get(), 24.0 + self.rotate_x_degrees.get(),
                self.roll_degrees.get(), self.perspective_distance.get(),
            )
            return (-100000.0, -100000.0) if projected is None else (projected[0], projected[1])
        if self._axis_is_locked(pane):
            x, y, z = point.x, point.y, point.z
        else:
            x, y, z = rotate_xyz(
                (point.x, point.y, point.z),
                self.rotate_x_degrees.get(), self.rotate_y_degrees.get(), self.roll_degrees.get(),
            )
        if pane.projection.startswith("Top"):
            horizontal, vertical = x, z
        elif pane.projection.startswith("Front"):
            horizontal, vertical = x, y
        else:
            horizontal, vertical = z, y
        return (
            pane.width / 2.0 + state.pan_x + horizontal * state.zoom,
            pane.height / 2.0 + state.pan_y - vertical * state.zoom,
        )

    def screen_to_world(self, sx: float, sy: float, pane: Pane | None = None) -> tuple[float, float, float]:
        pane = pane or self.pane_for_canvas(self.active_canvas)
        state = self.state_for_pane(pane)
        if pane.projection == "Perspective 3D":
            return perspective_ray_to_target_plane(
                sx, sy, pane, self.view_target(),
                -45.0 + self.rotate_y_degrees.get(), 24.0 + self.rotate_x_degrees.get(),
                self.roll_degrees.get(), self.perspective_distance.get(),
            )
        horizontal = (sx - pane.width / 2.0 - state.pan_x) / max(0.1, state.zoom)
        vertical = -(sy - pane.height / 2.0 - state.pan_y) / max(0.1, state.zoom)
        depth = state.depth
        if pane.projection.startswith("Top"):
            rotated = (horizontal, depth, vertical)
        elif pane.projection.startswith("Front"):
            rotated = (horizontal, vertical, depth)
        else:
            rotated = (depth, vertical, horizontal)
        if self._axis_is_locked(pane):
            return rotated
        return inverse_rotate_xyz(
            rotated, self.rotate_x_degrees.get(), self.rotate_y_degrees.get(), self.roll_degrees.get()
        )

    def point_depth(self, point: PCPPoint, pane: Pane | None = None) -> float:
        pane = pane or self.pane_for_canvas(self.active_canvas)
        if pane.projection == "Perspective 3D":
            projected = perspective_project(
                (point.x, point.y, point.z), pane, self.view_target(),
                -45.0 + self.rotate_y_degrees.get(), 24.0 + self.rotate_x_degrees.get(),
                self.roll_degrees.get(), self.perspective_distance.get(),
            )
            return projected[2] if projected else 1e9
        if self._axis_is_locked(pane):
            x, y, z = point.x, point.y, point.z
        else:
            x, y, z = rotate_xyz(
                (point.x, point.y, point.z),
                self.rotate_x_degrees.get(), self.rotate_y_degrees.get(), self.roll_degrees.get(),
            )
        if pane.projection.startswith("Top"):
            return y
        if pane.projection.startswith("Front"):
            return z
        return x

    # ---------- truly pane-aware brush ----------
    def brush_points(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        pane = self.active_event_pane or self.pane_for_canvas(self.active_canvas)
        if pane.projection == "Perspective 3D":
            return self.brush_points_3d(world)
        spacing = max(0.04, self.brush_spacing.get())
        radius = max(spacing, self.brush_size.get())
        hardness = max(0.0, min(1.0, self.brush_hardness.get()))
        steps = max(1, min(18, int(math.ceil(radius / spacing))))
        points: list[PCPPoint] = []
        for a in range(-steps, steps + 1):
            for b in range(-steps, steps + 1):
                da = a * spacing
                db = b * spacing
                distance = math.sqrt(da * da + db * db)
                if distance > radius:
                    continue
                probability = hardness + (1.0 - hardness) * max(0.0, 1.0 - distance / radius)
                if random.random() > probability:
                    continue
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
                points.append(self.make_point(x, y, z, density=max(0.1, 1.0 - distance / (radius * 1.2))))
        return points

    # ---------- event activation wrappers ----------
    def canvas_motion(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        super().canvas_motion(event)

    def canvas_press(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        self._stroke_projection = self.active_projection
        super().canvas_press(event)

    def canvas_drag(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        if self._stroke_projection is not None and self._stroke_projection != self.active_projection:
            self.stroke_last_world = None
            self._stroke_projection = self.active_projection
        super().canvas_drag(event)

    def canvas_release(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        super().canvas_release(event)
        self._stroke_projection = None
        self.redraw()

    def canvas_right_press(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        super().canvas_right_press(event)

    def canvas_double_right(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        super().canvas_double_right(event)

    def canvas_right_drag(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        super().canvas_right_drag(event)

    def canvas_right_release(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        super().canvas_right_release(event)

    def pan_press(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        state = self.pane_states[self.active_projection]
        self.pan_anchor = (event.x, event.y, state.pan_x, state.pan_y)

    def pan_drag(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        if self.pan_anchor is None:
            return
        x, y, start_x, start_y = self.pan_anchor
        state = self.pane_states[self.active_projection]
        state.pan_x = start_x + event.x - x
        state.pan_y = start_y + event.y - y
        self.pan_x, self.pan_y = state.pan_x, state.pan_y
        self.schedule_pane_render(event.widget, fast=True)
        self.schedule_layout_save()

    def mouse_wheel(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        pane = self.pane_for_canvas(event.widget)
        if pane.projection == "Perspective 3D":
            self.perspective_distance.set(
                max(0.5, min(5000.0, self.perspective_distance.get() * (0.88 if event.delta > 0 else 1 / 0.88)))
            )
        else:
            state = self.pane_states[pane.projection]
            state.zoom = max(2.0, min(400.0, state.zoom * (1.12 if event.delta > 0 else 1 / 1.12)))
            self.zoom.set(state.zoom)
        self.schedule_pane_render(event.widget, fast=True)
        self.schedule_layout_save()

    def mouse_wheel_linux(self, event: tk.Event, direction: int) -> None:
        event.delta = 120 if direction > 0 else -120
        self.mouse_wheel(event)

    # ---------- bounded asynchronous rendering ----------
    def _quality_multiplier(self) -> float:
        return {"Fast": 0.55, "Balanced": 1.0, "Detailed": 1.6}.get(self.viewport_quality.get(), 1.0)

    def pane_budget(self, *, fast: bool = False) -> int:
        if fast:
            return FAST_ACTIVE_BUDGET
        count = max(1, len(self.pane_canvases))
        total = SINGLE_POINT_BUDGET if count == 1 else THREE_PANE_BUDGET if count == 3 else FOUR_PANE_BUDGET
        return max(300, int(total * self._quality_multiplier() / count))

    def redraw(self) -> None:
        if not hasattr(self, "pane_canvases"):
            return
        for canvas in self.pane_canvases.values():
            self.schedule_pane_render(canvas)

    def request_redraw(self) -> None:
        if self.active_canvas is not None:
            self.schedule_pane_render(self.active_canvas, fast=True)

    def _perform_requested_redraw(self) -> None:
        self.redraw_after = None
        self.request_redraw()

    def _cancel_render_jobs(self) -> None:
        self._render_token += 1
        for after_id in list(self._render_after.values()):
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._render_after.clear()
        self._render_jobs.clear()

    def schedule_pane_render(self, canvas: tk.Canvas, *, fast: bool = False) -> None:
        if canvas not in self.canvas_projection or not canvas.winfo_exists():
            return
        self._render_token += 1
        token = self._render_token
        previous = self._render_after.pop(canvas, None)
        if previous is not None:
            try:
                self.after_cancel(previous)
            except tk.TclError:
                pass
        delay = 12 if fast else 45
        self._render_after[canvas] = self.after(delay, lambda c=canvas, t=token, f=fast: self._start_pane_render(c, t, f))

    def _sample_for_pane(self, limit: int) -> list[tuple[int, PCPPoint]]:
        return self._sample_visible_points(limit)

    def _start_pane_render(self, canvas: tk.Canvas, token: int, fast: bool) -> None:
        self._render_after.pop(canvas, None)
        if canvas not in self.canvas_projection or not canvas.winfo_exists():
            return
        pane = self.pane_for_canvas(canvas)
        points = self._sample_for_pane(self.pane_budget(fast=fast))
        if pane.projection == "Perspective 3D":
            points = sorted(points, key=lambda item: self.point_depth(item[1], pane), reverse=True)
        self._render_jobs[canvas] = {
            "token": token,
            "pane": pane,
            "points": points,
            "index": 0,
            "fast": fast,
        }
        if not self._render_started:
            self._render_started = time.monotonic()
        self._begin_canvas(canvas, pane)
        self._ensure_busy_tick()
        self._render_chunk(canvas)

    def _begin_canvas(self, canvas: tk.Canvas, pane: Pane) -> None:
        canvas.delete("all")
        canvas.create_rectangle(
            0, 0, pane.width, pane.height,
            fill="#0f1418" if pane.projection != "Perspective 3D" else "#080c10",
            outline="#4b5961",
        )
        self._draw_grid(canvas, pane)

    def _render_chunk(self, canvas: tk.Canvas) -> None:
        job = self._render_jobs.get(canvas)
        if job is None or not canvas.winfo_exists():
            return
        pane: Pane = job["pane"]
        points: list[tuple[int, PCPPoint]] = job["points"]
        start = int(job["index"])
        end = min(len(points), start + RENDER_CHUNK)
        layer_map = {layer.id: layer for layer in self.document.layers}
        mode = self.display_mode.get()
        state = self.state_for_pane(pane)
        for index, point in points[start:end]:
            layer = layer_map.get(point.layer_id)
            if layer is None:
                continue
            sx, sy = self.world_to_screen(point, pane)
            if not (0 <= sx <= pane.width and 0 <= sy <= pane.height):
                continue
            if pane.projection == "Perspective 3D":
                fade = max(0.18, min(1.0, 18.0 / max(1.0, self.point_depth(point, pane))))
            else:
                depth_delta = abs(self.point_depth(point, pane) - state.depth)
                fade = max(0.14, 1.0 - depth_delta / max(0.2, self.brush_size.get() * 1.5))
            color = self.point_display_color(point, layer, mode, fade)
            size = max(1.0, min(8.0, point.radius * 0.65 * self.document.settings.point_scale))
            outline = "#ffffff" if index in self.document.selected_indices else ""
            canvas.create_oval(sx - size, sy - size, sx + size, sy + size, fill=color, outline=outline, width=1)
        job["index"] = end
        if end < len(points):
            self._render_after[canvas] = self.after(1, lambda c=canvas: self._render_chunk(c))
            return
        self._finish_canvas(canvas, pane, len(points))
        self._render_jobs.pop(canvas, None)
        self._render_after.pop(canvas, None)
        if not self._render_jobs:
            elapsed = time.monotonic() - self._render_started if self._render_started else 0.0
            self.render_progress.set(100.0)
            self.render_status.set(f"Viewport ready · last refresh {elapsed:.2f}s")
            self._render_started = 0.0
            if self._busy_tick_after is not None:
                try:
                    self.after_cancel(self._busy_tick_after)
                except tk.TclError:
                    pass
                self._busy_tick_after = None

    def _ensure_busy_tick(self) -> None:
        if self._busy_tick_after is None:
            self._busy_tick()

    def _busy_tick(self) -> None:
        if not self._render_jobs:
            self._busy_tick_after = None
            return
        total = sum(max(1, len(job["points"])) for job in self._render_jobs.values())
        complete = sum(min(len(job["points"]), int(job["index"])) for job in self._render_jobs.values())
        percent = 100.0 * complete / max(1, total)
        elapsed = time.monotonic() - self._render_started
        self.render_progress.set(percent)
        self.render_status.set(f"Rendering {len(self._render_jobs)} view(s) · {percent:.0f}% · {elapsed:.1f}s")
        self._busy_tick_after = self.after(100, self._busy_tick)

    def _draw_grid(self, canvas: tk.Canvas, pane: Pane) -> None:
        if pane.projection == "Perspective 3D":
            target = self.view_target()
            extent = max(self.document.settings.width, self.document.settings.depth, 4.0) * 0.6
            for step in range(-8, 9):
                offset = step * extent / 8.0
                for start, end in (
                    ((-extent, target[1], offset), (extent, target[1], offset)),
                    ((offset, target[1], -extent), (offset, target[1], extent)),
                ):
                    x1, y1 = self.world_to_screen(PCPPoint(*start), pane)
                    x2, y2 = self.world_to_screen(PCPPoint(*end), pane)
                    canvas.create_line(x1, y1, x2, y2, fill="#182329")
            return
        state = self.state_for_pane(pane)
        spacing = max(0.05, self.document.settings.grid_spacing) * state.zoom
        while spacing < 18:
            spacing *= 2
        origin_x = pane.width / 2 + state.pan_x
        origin_y = pane.height / 2 + state.pan_y
        x = origin_x % spacing
        while x < pane.width:
            canvas.create_line(x, 0, x, pane.height, fill="#1c252b")
            x += spacing
        y = origin_y % spacing
        while y < pane.height:
            canvas.create_line(0, y, pane.width, y, fill="#1c252b")
            y += spacing
        canvas.create_line(origin_x, 0, origin_x, pane.height, fill="#6e3d3d", width=2)
        canvas.create_line(0, origin_y, pane.width, origin_y, fill="#3d586e", width=2)

    def _finish_canvas(self, canvas: tk.Canvas, pane: Pane, sample_count: int) -> None:
        self._draw_bounds(canvas, pane)
        canvas.create_text(8, 8, text=pane.name, anchor="nw", fill="#a9c4d2", font=("Sans", 9, "bold"))
        state = self.state_for_pane(pane)
        if pane.projection != "Perspective 3D":
            axis = "Y" if pane.projection.startswith("Top") else "Z" if pane.projection.startswith("Front") else "X"
            canvas.create_text(
                8, 25, text=f"Independent {axis}-depth {state.depth:.2f} · zoom {state.zoom:.1f}",
                anchor="nw", fill="#6f8793", font=("Sans", 8),
            )
        else:
            canvas.create_text(
                8, 25, text="Perspective bridge · F5 real renderer · B native brush",
                anchor="nw", fill="#6f8793", font=("Sans", 8),
            )
        canvas.create_text(
            8, max(8, pane.height - 8),
            text=f"display {sample_count:,}/{len(self.document.points):,} points",
            anchor="sw", fill="#71838d", font=("Sans", 8),
        )
        self._draw_overlays(canvas, pane)

    def _draw_bounds(self, canvas: tk.Canvas, pane: Pane) -> None:
        if pane.projection == "Perspective 3D":
            return
        if pane.projection.startswith("Top"):
            corners = [
                PCPPoint(-self.document.settings.width / 2, 0, -self.document.settings.depth / 2),
                PCPPoint(self.document.settings.width / 2, 0, self.document.settings.depth / 2),
            ]
        elif pane.projection.startswith("Front"):
            corners = [
                PCPPoint(-self.document.settings.width / 2, -self.document.settings.height / 2, 0),
                PCPPoint(self.document.settings.width / 2, self.document.settings.height / 2, 0),
            ]
        else:
            corners = [
                PCPPoint(0, -self.document.settings.height / 2, -self.document.settings.depth / 2),
                PCPPoint(0, self.document.settings.height / 2, self.document.settings.depth / 2),
            ]
        x1, y1 = self.world_to_screen(corners[0], pane)
        x2, y2 = self.world_to_screen(corners[1], pane)
        canvas.create_rectangle(x1, y1, x2, y2, outline="#3b4c55", dash=(5, 5))

    def _draw_overlays(self, canvas: tk.Canvas, pane: Pane) -> None:
        selection_projection = self.selection_pane.projection if self.selection_pane else None
        if self.selection_box_start and self.selection_box_end and pane.projection == selection_projection:
            canvas.create_rectangle(*self.selection_box_start, *self.selection_box_end, outline="#ffdc61", width=2, dash=(6, 3))
        shape_projection = self.shape_pane.projection if self.shape_pane else None
        if self.shape_region_start and self.shape_region_end and pane.projection == shape_projection:
            canvas.create_rectangle(*self.shape_region_start, *self.shape_region_end, outline="#50d7ff", width=2, dash=(4, 3))
        if self.curve_anchors and (selection_projection is None or pane.projection == selection_projection):
            anchors = list(self.curve_anchors)
            if self.curve_hover is not None:
                anchors.append(self.curve_hover)
            if len(anchors) >= 2:
                coords: list[float] = []
                for anchor in anchors:
                    coords.extend(self.world_to_screen(PCPPoint(*anchor), pane))
                canvas.create_line(*coords, fill="#ff74e8", width=2, dash=(5, 2))
            for anchor in self.curve_anchors:
                sx, sy = self.world_to_screen(PCPPoint(*anchor), pane)
                canvas.create_oval(sx - 5, sy - 5, sx + 5, sy + 5, fill="#ff74e8", outline="#ffffff")
        if self.shape_preview and (shape_projection is None or pane.projection == shape_projection):
            points = self.shape_preview_polyline(self.shape_preview)
            if len(points) >= 2:
                coords: list[float] = []
                for point in points:
                    coords.extend(self.world_to_screen(PCPPoint(*point), pane))
                canvas.create_line(*coords, fill="#48e8ff", width=2, dash=(5, 2))

    # ---------- frame and preview throttling ----------
    def frame_all(self) -> None:
        lower, upper = self.document.bounds()
        for canvas, projection in self.canvas_projection.items():
            state = self.pane_states[projection]
            pane = self.pane_for_canvas(canvas)
            if projection.startswith("Top"):
                size_h, size_v = upper[0] - lower[0], upper[2] - lower[2]
            elif projection.startswith("Front"):
                size_h, size_v = upper[0] - lower[0], upper[1] - lower[1]
            elif projection.startswith("Side"):
                size_h, size_v = upper[2] - lower[2], upper[1] - lower[1]
            else:
                continue
            state.zoom = max(2.0, min(160.0, 0.72 * min(pane.width / max(1.0, size_h), pane.height / max(1.0, size_v))))
            state.pan_x = 0.0
            state.pan_y = 0.0
        size = max(upper[index] - lower[index] for index in range(3))
        self.perspective_distance.set(max(2.0, size * 2.1))
        self.redraw()
        self.schedule_layout_save()

    def schedule_live_preview(self, force: bool = False) -> None:
        preview_running = self.preview_process is not None and self.preview_process.poll() is None
        if not force and (not self.auto_live_preview.get() or not preview_running):
            return
        if self.preview_write_after is not None:
            try:
                self.after_cancel(self.preview_write_after)
            except tk.TclError:
                pass
        delay = 650 if self.view_type.get() == "Single" else 1800
        self.render_status.set(f"Native preview refresh queued · {delay / 1000:.1f}s idle")
        self.preview_write_after = self.after(delay, self.write_live_preview)

    def write_live_preview(self) -> None:
        started = time.monotonic()
        self.render_status.set("Writing native preview…")
        self.update_idletasks()
        super().write_live_preview()
        elapsed = time.monotonic() - started
        self._last_preview_write = time.monotonic()
        self.render_status.set(f"Native preview updated in {elapsed:.2f}s")

    # ---------- safer close ----------
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
        for after_id in (self.preview_poll_after, self.preview_write_after, self._busy_tick_after, self._layout_save_after):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
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
