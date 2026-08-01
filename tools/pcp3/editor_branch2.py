from __future__ import annotations

import json
import math
import os
import random
import subprocess
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import editor as base_editor
from .editor import ToolTip
from .interaction import (
    Pane,
    catmull_rom_points,
    inverse_rotate_xyz,
    perspective_project,
    perspective_ray_to_target_plane,
    region_indices,
    resample_polyline,
    rotate_xyz,
)
from .model import (
    ENVIRONMENT_LABELS,
    ENVIRONMENT_TYPES,
    SEMANTIC_FLAGS,
    Layer,
    PCPPoint,
    primitive_box,
    primitive_cylinder,
    primitive_line,
    primitive_sphere,
)

TOOLS = (
    ("select", "Select Region"),
    ("pencil", "Point Pencil"),
    ("brush", "3D Brush"),
    ("eraser", "Eraser"),
    ("recolor", "Recolor"),
    ("picker", "Attribute Picker"),
    ("line", "Line / Curve"),
    ("rotate", "Rotate"),
    ("roll", "Roll"),
    ("pan", "Pan"),
)
TOOLS_DICT = dict(TOOLS)
DISPLAY_MODES = ("RGB", "Layer", "Point", "Semantic", "Tool")
VIEW_TYPES = ("Single", "3-Square", "4-Square")
PROJECTIONS = ("Top X/Z", "Front X/Y", "Side Z/Y", "Perspective 3D", "All X/Y/Z", "All X/Y/Z/NP")

# A few inherited helpers refer to these module globals in the Branch 1 module.
base_editor.TOOLS = TOOLS
base_editor.TOOLS_DICT = TOOLS_DICT
base_editor.DISPLAY_MODES = DISPLAY_MODES
base_editor.PROJECTIONS = PROJECTIONS


class ShapeParameterDialog(tk.Toplevel):
    """Region-derived shape parameters with paired entries and sliders."""

    def __init__(
        self,
        editor: "PCP3Editor",
        shape: str,
        initial: dict[str, float],
        on_generate: Callable[[dict[str, float]], None],
    ) -> None:
        super().__init__(editor)
        self.editor = editor
        self.shape = shape
        self.on_generate = on_generate
        self.title(f"{shape.title()} generator parameters")
        self.transient(editor)
        self.resizable(True, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.variables = {key: tk.DoubleVar(value=value) for key, value in initial.items()}

        ttk.Label(
            self,
            text=(
                "The selected grid region established the center and first dimensions. "
                "Use either the numeric input or slider. The colored wireframe updates live."
            ),
            wraplength=560,
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 6))

        keys = ["center_x", "center_y", "center_z", "spacing"]
        if shape == "box":
            keys += ["size_x", "size_y", "size_z"]
        elif shape == "sphere":
            keys += ["radius"]
        else:
            keys += ["radius", "height"]
        extent = max(
            editor.document.settings.width,
            editor.document.settings.height,
            editor.document.settings.depth,
            4.0,
        )
        for row, key in enumerate(keys, start=1):
            ttk.Label(self, text=key.replace("_", " ").title()).grid(
                row=row, column=0, sticky="w", padx=(10, 5), pady=3
            )
            entry = ttk.Entry(self, textvariable=self.variables[key], width=12)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            if key.startswith("center_"):
                low, high = -extent, extent
            elif key == "spacing":
                low, high = 0.03, max(1.0, extent / 4.0)
            else:
                low, high = 0.05, extent * 2.0
            ttk.Scale(
                self,
                from_=low,
                to=high,
                variable=self.variables[key],
                command=lambda _value: self.changed(),
            ).grid(row=row, column=2, sticky="ew", padx=(6, 10), pady=3)
            entry.bind("<KeyRelease>", lambda _event: self.changed())
            entry.bind("<FocusOut>", lambda _event: self.changed())

        buttons = ttk.Frame(self, padding=10)
        buttons.grid(row=len(keys) + 1, column=0, columnspan=3, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=3)
        ttk.Button(buttons, text="Generate", command=self.generate).pack(side="right", padx=3)
        self.columnconfigure(2, weight=1)
        self.after_idle(self.changed)

    def values(self) -> dict[str, float]:
        output: dict[str, float] = {}
        for key, variable in self.variables.items():
            try:
                output[key] = float(variable.get())
            except (tk.TclError, ValueError):
                output[key] = 0.0
        return output

    def changed(self) -> None:
        self.editor.shape_preview = {"shape": self.shape, **self.values()}
        self.editor.redraw()

    def generate(self) -> None:
        self.on_generate(self.values())
        self.editor.shape_preview = None
        self.editor.shape_mode = None
        self.destroy()

    def cancel(self) -> None:
        self.editor.shape_preview = None
        self.editor.shape_mode = None
        self.editor.redraw()
        self.destroy()


class PCP3Editor(base_editor.PCP3Editor):
    """Branch 2 interaction editor layered over the Branch 1 data/pipeline core."""

    def __init__(self, root_path: Path) -> None:
        tk.Tk.__init__(self)
        self.root_path = root_path.resolve()
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 2")
        self.geometry("1480x930")
        self.minsize(1120, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.document = base_editor.PCPDocument.new("environment_object")
        self.document.metadata["editor_branch"] = "ISL_plus_branch2"
        self.project_path: Path | None = None
        self.history: list[dict[str, Any]] = []
        self.future: list[dict[str, Any]] = []
        self.preview_process: subprocess.Popen[Any] | None = None
        self.preview_write_after: str | None = None
        self.drag_start: tuple[float, float, float] | None = None
        self.pan_anchor: tuple[int, int, float, float] | None = None
        self.line_start: tuple[float, float, float] | None = None
        self.selection_box_start: tuple[int, int] | None = None

        self.view_type = tk.StringVar(value="Single")
        self.rotate_x_degrees = tk.DoubleVar(value=0.0)
        self.rotate_y_degrees = tk.DoubleVar(value=0.0)
        self.roll_degrees = tk.DoubleVar(value=0.0)
        self.perspective_distance = tk.DoubleVar(value=14.0)
        self.selection_box_end: tuple[int, int] | None = None
        self.selection_pane: Pane | None = None
        self.selection_waiting_second = False
        self.selection_dragged = False
        self.selection_additive = False
        self.shape_mode: str | None = None
        self.shape_preview: dict[str, float | str] | None = None
        self.shape_region_start: tuple[int, int] | None = None
        self.shape_region_end: tuple[int, int] | None = None
        self.shape_pane: Pane | None = None
        self.curve_anchors: list[tuple[float, float, float]] = []
        self.curve_hover: tuple[float, float, float] | None = None
        self.stroke_last_world: tuple[float, float, float] | None = None
        self.redraw_after: str | None = None
        self.active_event_pane: Pane | None = None
        self.rotate_anchor: tuple[int, int, float, float, float] | None = None
        self.left_button_down = False
        self.right_button_down = False
        self.left_button_moved = False
        self.right_button_moved = False
        self.double_left = False
        self.double_right = False
        self.reset_hold_after: str | None = None
        self.reset_prompted = False
        self.preview_command_offset = 0
        self.preview_poll_after: str | None = None

        self.tool = tk.StringVar(value="brush")
        self.display_mode = tk.StringVar(value="RGB")
        self.projection = tk.StringVar(value="Top X/Z")
        self.depth_value = tk.DoubleVar(value=0.0)
        self.zoom = tk.DoubleVar(value=28.0)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.brush_size = tk.DoubleVar(value=0.8)
        self.brush_hardness = tk.DoubleVar(value=0.75)
        self.brush_spacing = tk.DoubleVar(value=0.12)
        self.point_radius = tk.DoubleVar(value=2.0)
        self.color_hex = tk.StringVar(value="#d9cc94")
        self.alpha = tk.DoubleVar(value=1.0)
        self.semantic = tk.StringVar(value="generic")
        self.environment_type = tk.StringVar(value=self.document.environment_type)
        self.status = tk.StringVar(value="Ready · create points in the canvas or native 3D brush window")
        self.point_count_text = tk.StringVar(value="0 points")
        self.coords_text = tk.StringVar(value="x 0.00 · y 0.00 · z 0.00")
        self.auto_live_preview = tk.BooleanVar(value=True)

        self._build_menu()
        self._build_toolbar()
        self._build_workspace()
        self._bind_shortcuts()
        self._sync_all_from_document()
        self.push_history("New document")
        self.after(120, self.poll_native_brush_commands)

    # ---------- Branch 2 UI ----------
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        self.config(menu=menu)

        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="New…", accelerator="Ctrl+N", command=self.new_document)
        file_menu.add_command(label="Open…", accelerator="Ctrl+O", command=self.open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        file_menu.add_command(label="Save As…", accelerator="Ctrl+Shift+S", command=self.save_as)
        file_menu.add_command(label="Export to SignalCloud Database…", command=self.export_to_database)
        file_menu.add_separator()
        file_menu.add_command(label="Import ASCII PLY…", command=self.import_ply_file)
        file_menu.add_command(label="Export ASCII PLY…", command=self.export_ply_file)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menu.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Delete Selected", accelerator="Delete", command=self.delete_selected)
        edit_menu.add_command(label="Select All", accelerator="Ctrl+A", command=self.select_all)
        edit_menu.add_command(label="Clear Selection", accelerator="Esc", command=self.clear_selection)
        menu.add_cascade(label="Edit", menu=edit_menu)

        view_menu = tk.Menu(menu, tearoff=False)
        for mode in DISPLAY_MODES:
            view_menu.add_radiobutton(label=mode, value=mode, variable=self.display_mode, command=self.redraw)
        view_menu.add_separator()
        for view in VIEW_TYPES:
            view_menu.add_radiobutton(label=view, value=view, variable=self.view_type, command=self.view_type_changed)
        view_menu.add_separator()
        view_menu.add_command(label="Frame All", accelerator="F", command=self.frame_all)
        view_menu.add_command(label="Native SignalCloud Preview", accelerator="F5", command=self.launch_native_preview)
        menu.add_cascade(label="View", menu=view_menu)

        environment_menu = tk.Menu(menu, tearoff=False)
        for kind in ENVIRONMENT_TYPES:
            environment_menu.add_radiobutton(
                label=ENVIRONMENT_LABELS[kind],
                value=kind,
                variable=self.environment_type,
                command=self.change_environment_type,
            )
        menu.add_cascade(label="Environment", menu=environment_menu)

        tools_menu = tk.Menu(menu, tearoff=False)
        for key, label in TOOLS:
            tools_menu.add_radiobutton(label=label, value=key, variable=self.tool, command=self.update_tool_hud)
        tools_menu.add_separator()
        tools_menu.add_command(label="Tools Help Guide", command=self.show_tools_help)
        menu.add_cascade(label="Tools", menu=tools_menu)

        layers_menu = tk.Menu(menu, tearoff=False)
        layers_menu.add_command(label="Add Layer", command=self.add_layer)
        layers_menu.add_command(label="Duplicate Layer", command=self.duplicate_layer)
        layers_menu.add_command(label="Delete Layer", command=self.delete_layer)
        layers_menu.add_separator()
        layers_menu.add_command(label="Move Layer Up", command=lambda: self.move_layer(-1))
        layers_menu.add_command(label="Move Layer Down", command=lambda: self.move_layer(1))
        menu.add_cascade(label="Layers", menu=layers_menu)

        effects_menu = tk.Menu(menu, tearoff=False)
        effects_menu.add_command(label="Jitter Selected…", command=self.effect_jitter)
        effects_menu.add_command(label="Normalize Selected Radius", command=self.effect_normalize_radius)
        effects_menu.add_command(label="Mirror Selected X", command=lambda: self.effect_mirror("x"))
        effects_menu.add_command(label="Mirror Selected Y", command=lambda: self.effect_mirror("y"))
        effects_menu.add_command(label="Mirror Selected Z", command=lambda: self.effect_mirror("z"))
        menu.add_cascade(label="Effects", menu=effects_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="Tools Help Guide", command=self.show_tools_help)
        help_menu.add_command(label="Branch Scope", command=self.show_scope)
        help_menu.add_command(label="Format Information", command=self.show_format_info)
        menu.add_cascade(label="Help", menu=help_menu)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
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
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(bar, text="Environment:").pack(side="left")
        environment_box = ttk.Combobox(
            bar, textvariable=self.environment_type, values=ENVIRONMENT_TYPES, state="readonly", width=18
        )
        environment_box.pack(side="left", padx=4)
        environment_box.bind("<<ComboboxSelected>>", lambda _event: self.change_environment_type())
        ttk.Label(bar, text="View:").pack(side="left", padx=(10, 0))
        view_box = ttk.Combobox(bar, textvariable=self.view_type, values=VIEW_TYPES, state="readonly", width=10)
        view_box.pack(side="left", padx=4)
        view_box.bind("<<ComboboxSelected>>", lambda _event: self.view_type_changed())
        ttk.Label(bar, text="Projection:").pack(side="left", padx=(10, 0))
        projection_box = ttk.Combobox(
            bar, textvariable=self.projection, values=PROJECTIONS, state="readonly", width=15
        )
        projection_box.pack(side="left", padx=4)
        projection_box.bind("<<ComboboxSelected>>", lambda _event: self.projection_changed())
        ttk.Label(bar, text="Display:").pack(side="left", padx=(10, 0))
        display_box = ttk.Combobox(
            bar, textvariable=self.display_mode, values=DISPLAY_MODES, state="readonly", width=9
        )
        display_box.pack(side="left", padx=4)
        display_box.bind("<<ComboboxSelected>>", lambda _event: self.redraw())
        ttk.Checkbutton(bar, text="Live native refresh", variable=self.auto_live_preview).pack(side="right", padx=4)

        toolbar = ttk.LabelFrame(self, text="Active Tool HUD", padding=(8, 5))
        toolbar.pack(fill="x", padx=8, pady=(0, 6))
        self.active_tool_label = ttk.Label(toolbar, text="3D Brush", width=18)
        self.active_tool_label.grid(row=0, column=0, sticky="w", padx=3)
        ttk.Label(toolbar, text="Size").grid(row=0, column=1)
        ttk.Spinbox(toolbar, from_=0.05, to=50.0, increment=0.05, textvariable=self.brush_size, width=8).grid(row=0, column=2, padx=3)
        ttk.Label(toolbar, text="Hardness").grid(row=0, column=3)
        ttk.Spinbox(toolbar, from_=0.0, to=1.0, increment=0.05, textvariable=self.brush_hardness, width=7).grid(row=0, column=4, padx=3)
        ttk.Label(toolbar, text="Spacing").grid(row=0, column=5)
        ttk.Spinbox(toolbar, from_=0.02, to=10.0, increment=0.02, textvariable=self.brush_spacing, width=7).grid(row=0, column=6, padx=3)
        ttk.Label(toolbar, text="Point px").grid(row=0, column=7)
        ttk.Spinbox(toolbar, from_=0.25, to=255.0, increment=0.25, textvariable=self.point_radius, width=7).grid(row=0, column=8, padx=3)
        ttk.Label(toolbar, text="Semantic").grid(row=0, column=9)
        ttk.Combobox(
            toolbar, textvariable=self.semantic, values=tuple(SEMANTIC_FLAGS), state="readonly", width=15
        ).grid(row=0, column=10, padx=3)
        ttk.Button(toolbar, text="Color", command=self.choose_color).grid(row=0, column=11, padx=(10, 3))
        self.color_swatch = tk.Label(toolbar, width=4, relief="sunken", background=self.color_hex.get())
        self.color_swatch.grid(row=0, column=12, padx=3)
        ttk.Label(toolbar, text="Alpha").grid(row=0, column=13)
        ttk.Spinbox(toolbar, from_=0.0, to=1.0, increment=0.05, textvariable=self.alpha, width=6).grid(row=0, column=14, padx=3)
        self.rotation_label = ttk.Label(toolbar, text="X 0° · Y 0° · Z 0°")
        self.rotation_label.grid(row=1, column=0, columnspan=6, sticky="w", pady=(5, 0))
        ttk.Button(toolbar, text="Reset View Angles", command=self.prompt_reset_angles).grid(
            row=1, column=11, columnspan=4, sticky="e", pady=(5, 0)
        )

    def _build_workspace(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8)

        tools_frame = ttk.Frame(paned, padding=5)
        paned.add(tools_frame, weight=0)
        ttk.Label(tools_frame, text="Tools", font=("Sans", 11, "bold")).pack(anchor="w", pady=(0, 4))
        for key, label in TOOLS:
            button = ttk.Radiobutton(
                tools_frame, text=label, value=key, variable=self.tool, command=self.update_tool_hud
            )
            button.pack(fill="x", pady=1)
            ToolTip(button, self.tool_help(key))
        ttk.Separator(tools_frame).pack(fill="x", pady=8)
        ttk.Label(tools_frame, text="Guided shapes", font=("Sans", 10, "bold")).pack(anchor="w")
        for shape, label in (("box", "Box"), ("sphere", "Sphere"), ("cylinder", "Cylinder")):
            button = ttk.Button(tools_frame, text=label, command=lambda value=shape: self.activate_shape_tool(value))
            button.pack(fill="x", pady=1)
            ToolTip(button, "Click the shape, select a region, then tune values in the live slider/input window.")
        for label, command in (
            ("Room Shell", self.generate_room_shell),
            ("Humanoid Guide", self.generate_humanoid_guide),
            ("Liquid Plane", self.generate_liquid_plane),
        ):
            ttk.Button(tools_frame, text=label, command=command).pack(fill="x", pady=1)

        center = ttk.Frame(paned)
        paned.add(center, weight=5)
        canvas_toolbar = ttk.Frame(center, padding=(4, 2))
        canvas_toolbar.pack(fill="x")
        ttk.Label(canvas_toolbar, text="Edit-plane depth:").pack(side="left")
        ttk.Scale(
            canvas_toolbar,
            from_=-50.0,
            to=50.0,
            variable=self.depth_value,
            command=lambda _value: self.redraw(),
        ).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(canvas_toolbar, textvariable=self.coords_text, width=28).pack(side="right")

        self.canvas = tk.Canvas(center, background="#0d1115", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.canvas_press)
        self.canvas.bind("<Double-Button-1>", self.canvas_double_left)
        self.canvas.bind("<B1-Motion>", self.canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
        self.canvas.bind("<ButtonPress-3>", self.canvas_right_press)
        self.canvas.bind("<Double-Button-3>", self.canvas_double_right)
        self.canvas.bind("<B3-Motion>", self.canvas_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.canvas_right_release)
        self.canvas.bind("<ButtonPress-2>", self.pan_press)
        self.canvas.bind("<B2-Motion>", self.pan_drag)
        self.canvas.bind("<ButtonRelease-2>", lambda _event: setattr(self, "pan_anchor", None))
        self.canvas.bind("<MouseWheel>", self.mouse_wheel)
        self.canvas.bind("<Button-4>", lambda event: self.mouse_wheel_linux(event, 1))
        self.canvas.bind("<Button-5>", lambda event: self.mouse_wheel_linux(event, -1))
        self.canvas.bind("<Motion>", self.canvas_motion)

        right = ttk.Frame(paned, padding=5)
        paned.add(right, weight=1)
        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)

        layers_tab = ttk.Frame(notebook, padding=6)
        notebook.add(layers_tab, text="Layers")
        self.layer_tree = ttk.Treeview(
            layers_tab, columns=("visible", "semantic", "points"), show="tree headings", height=14
        )
        self.layer_tree.heading("#0", text="Layer")
        self.layer_tree.heading("visible", text="Visibility")
        self.layer_tree.heading("semantic", text="Semantic")
        self.layer_tree.heading("points", text="Points")
        self.layer_tree.column("#0", width=130)
        self.layer_tree.column("visible", width=68, anchor="center")
        self.layer_tree.column("semantic", width=100)
        self.layer_tree.column("points", width=60, anchor="e")
        self.layer_tree.pack(fill="both", expand=True)
        self.layer_tree.bind("<<TreeviewSelect>>", self.layer_selected)
        self.layer_tree.bind("<Button-1>", self.layer_row_click, add=True)
        layer_buttons = ttk.Frame(layers_tab)
        layer_buttons.pack(fill="x", pady=(5, 0))
        for text, command in (
            ("+", self.add_layer),
            ("Copy", self.duplicate_layer),
            ("−", self.delete_layer),
            ("↑", lambda: self.move_layer(-1)),
            ("↓", lambda: self.move_layer(1)),
        ):
            ttk.Button(layer_buttons, text=text, width=6, command=command).pack(side="left", padx=1)
        self.layer_name = tk.StringVar()
        self.layer_group = tk.StringVar()
        self.layer_opacity = tk.DoubleVar(value=1.0)
        self.layer_locked = tk.BooleanVar(value=False)
        layer_props = ttk.LabelFrame(layers_tab, text="Layer properties", padding=5)
        layer_props.pack(fill="x", pady=(6, 0))
        self._labeled_entry(layer_props, "Name", self.layer_name, 0)
        self._labeled_entry(layer_props, "Group", self.layer_group, 1)
        ttk.Label(layer_props, text="Opacity").grid(row=2, column=0, sticky="w")
        ttk.Scale(layer_props, from_=0.0, to=1.0, variable=self.layer_opacity).grid(row=2, column=1, sticky="ew")
        ttk.Checkbutton(layer_props, text="Locked", variable=self.layer_locked).grid(row=3, column=1, sticky="w")
        ttk.Button(layer_props, text="Apply layer properties", command=self.apply_layer_properties).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )
        layer_props.columnconfigure(1, weight=1)

        properties_tab = ttk.Frame(notebook, padding=6)
        notebook.add(properties_tab, text="Properties")
        self.asset_id = tk.StringVar()
        self.display_name = tk.StringVar()
        self.canvas_width = tk.DoubleVar()
        self.canvas_height = tk.DoubleVar()
        self.canvas_depth = tk.DoubleVar()
        self.ambient_light = tk.DoubleVar()
        self.document_point_scale = tk.DoubleVar()
        self.document_density_scale = tk.DoubleVar()
        self.grid_spacing = tk.DoubleVar()
        self.runtime_enabled = tk.BooleanVar(value=True)
        self.runtime_game_preview = tk.BooleanVar(value=False)
        self.runtime_zone = tk.StringVar(value="Reception Tape")
        self.runtime_scale = tk.DoubleVar(value=1.0)
        rows = (
            ("Asset ID", self.asset_id),
            ("Display name", self.display_name),
            ("Canvas width", self.canvas_width),
            ("Canvas height", self.canvas_height),
            ("Canvas depth", self.canvas_depth),
            ("Ambient light", self.ambient_light),
            ("Point scale", self.document_point_scale),
            ("Density scale", self.document_density_scale),
            ("Grid spacing", self.grid_spacing),
            ("Preview zone", self.runtime_zone),
            ("Preview scale", self.runtime_scale),
        )
        for row, (label, variable) in enumerate(rows):
            self._labeled_entry(properties_tab, label, variable, row)
        ttk.Checkbutton(properties_tab, text="Runtime enabled", variable=self.runtime_enabled).grid(
            row=len(rows), column=0, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(properties_tab, text="Auto-preview in game", variable=self.runtime_game_preview).grid(
            row=len(rows) + 1, column=0, columnspan=2, sticky="w"
        )
        ttk.Button(properties_tab, text="Apply document settings", command=self.apply_document_properties).grid(
            row=len(rows) + 2, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        properties_tab.columnconfigure(1, weight=1)

        cert_tab = ttk.Frame(notebook, padding=6)
        notebook.add(cert_tab, text="Certificate")
        self.creator_name = tk.StringVar()
        self.creator_title = tk.StringVar()
        self.creator_tags = tk.StringVar()
        self.editor_name = tk.StringVar()
        self.creator_description = tk.Text(cert_tab, height=8, wrap="word")
        self._labeled_entry(cert_tab, "Creator name", self.creator_name, 0)
        self._labeled_entry(cert_tab, "Title", self.creator_title, 1)
        self._labeled_entry(cert_tab, "Tags", self.creator_tags, 2)
        self._labeled_entry(cert_tab, "Editing user", self.editor_name, 3)
        ttk.Label(cert_tab, text="Description").grid(row=4, column=0, sticky="nw", pady=3)
        self.creator_description.grid(row=4, column=1, sticky="nsew", pady=3)
        ttk.Button(cert_tab, text="Apply author form", command=self.apply_author_form).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(5, 0)
        )
        ttk.Label(
            cert_tab,
            text=(
                "The first save has no visible version number. Later modifications extend the proof chain; "
                "author-form edits also record the editing user."
            ),
            wraplength=290,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)
        cert_tab.columnconfigure(1, weight=1)
        cert_tab.rowconfigure(4, weight=1)

        history_tab = ttk.Frame(notebook, padding=6)
        notebook.add(history_tab, text="History")
        self.history_list = tk.Listbox(history_tab)
        self.history_list.pack(fill="both", expand=True)
        ttk.Button(history_tab, text="Undo", command=self.undo).pack(side="left", fill="x", expand=True, pady=4)
        ttk.Button(history_tab, text="Redo", command=self.redo).pack(side="left", fill="x", expand=True, pady=4)

        status = ttk.Frame(self, padding=(8, 4))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status).pack(side="left", fill="x", expand=True)
        ttk.Label(status, textvariable=self.point_count_text).pack(side="right")

    # ---------- View and projection ----------
    def view_type_changed(self) -> None:
        if self.view_type.get() == "3-Square":
            self.projection.set("All X/Y/Z")
        elif self.view_type.get() == "4-Square":
            self.projection.set("All X/Y/Z/NP")
        elif self.projection.get().startswith("All "):
            self.projection.set("Top X/Z")
        self.redraw()

    def projection_changed(self) -> None:
        projection = self.projection.get()
        if projection == "All X/Y/Z":
            self.view_type.set("3-Square")
        elif projection == "All X/Y/Z/NP":
            self.view_type.set("4-Square")
        elif self.view_type.get() != "Single":
            self.view_type.set("Single")
        self.redraw()

    def panes(self) -> list[Pane]:
        width = max(1.0, float(self.canvas.winfo_width()))
        height = max(1.0, float(self.canvas.winfo_height()))
        gap = 3.0
        view = self.view_type.get()
        if view == "4-Square":
            half_w = (width - gap) / 2.0
            half_h = (height - gap) / 2.0
            return [
                Pane("Z axis · Front X/Y", "Front X/Y", 0, 0, half_w, half_h),
                Pane("Y axis · Top X/Z", "Top X/Z", half_w + gap, 0, half_w, half_h),
                Pane("X axis · Side Z/Y", "Side Z/Y", 0, half_h + gap, half_w, half_h),
                Pane("NP · Perspective editing bridge", "Perspective 3D", half_w + gap, half_h + gap, half_w, half_h),
            ]
        if view == "3-Square":
            half_w = (width - gap) / 2.0
            half_h = (height - gap) / 2.0
            return [
                Pane("X axis · Side Z/Y", "Side Z/Y", 0, 0, half_w, half_h),
                Pane("Y axis · Top X/Z", "Top X/Z", half_w + gap, 0, half_w, half_h),
                Pane("Z axis · Front X/Y", "Front X/Y", (width - half_w) / 2.0, half_h + gap, half_w, half_h),
            ]
        projection = self.projection.get()
        if projection.startswith("All "):
            projection = "Top X/Z"
        return [Pane(projection, projection, 0, 0, width, height)]

    def pane_at(self, sx: float, sy: float) -> Pane:
        for pane in self.panes():
            if pane.contains(sx, sy):
                return pane
        return self.panes()[0]

    def view_target(self) -> tuple[float, float, float]:
        lower, upper = self.document.bounds()
        return tuple((lower[index] + upper[index]) * 0.5 for index in range(3))  # type: ignore[return-value]

    def rotated(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        return rotate_xyz(
            point,
            self.rotate_x_degrees.get(),
            self.rotate_y_degrees.get(),
            self.roll_degrees.get(),
        )

    def world_to_screen(self, point: PCPPoint, pane: Pane | None = None) -> tuple[float, float]:
        pane = pane or self.active_event_pane or self.panes()[0]
        if pane.projection == "Perspective 3D":
            projected = perspective_project(
                (point.x, point.y, point.z),
                pane,
                self.view_target(),
                -45.0 + self.rotate_y_degrees.get(),
                24.0 + self.rotate_x_degrees.get(),
                self.roll_degrees.get(),
                self.perspective_distance.get(),
            )
            if projected is None:
                return -100000.0, -100000.0
            return projected[0], projected[1]
        x, y, z = self.rotated((point.x, point.y, point.z))
        if pane.projection.startswith("Top"):
            horizontal, vertical = x, z
        elif pane.projection.startswith("Front"):
            horizontal, vertical = x, y
        else:
            horizontal, vertical = z, y
        return (
            pane.x + pane.width / 2.0 + self.pan_x + horizontal * self.zoom.get(),
            pane.y + pane.height / 2.0 + self.pan_y - vertical * self.zoom.get(),
        )

    def screen_to_world(self, sx: float, sy: float, pane: Pane | None = None) -> tuple[float, float, float]:
        pane = pane or self.active_event_pane or self.pane_at(sx, sy)
        if pane.projection == "Perspective 3D":
            return perspective_ray_to_target_plane(
                sx,
                sy,
                pane,
                self.view_target(),
                -45.0 + self.rotate_y_degrees.get(),
                24.0 + self.rotate_x_degrees.get(),
                self.roll_degrees.get(),
                self.perspective_distance.get(),
            )
        zoom = max(0.1, self.zoom.get())
        horizontal = (sx - pane.x - pane.width / 2.0 - self.pan_x) / zoom
        vertical = -(sy - pane.y - pane.height / 2.0 - self.pan_y) / zoom
        depth = self.depth_value.get()
        if pane.projection.startswith("Top"):
            rotated = (horizontal, depth, vertical)
        elif pane.projection.startswith("Front"):
            rotated = (horizontal, vertical, depth)
        else:
            rotated = (depth, vertical, horizontal)
        return inverse_rotate_xyz(
            rotated,
            self.rotate_x_degrees.get(),
            self.rotate_y_degrees.get(),
            self.roll_degrees.get(),
        )

    def point_depth(self, point: PCPPoint, pane: Pane | None = None) -> float:
        pane = pane or self.active_event_pane or self.panes()[0]
        if pane.projection == "Perspective 3D":
            projected = perspective_project(
                (point.x, point.y, point.z),
                pane,
                self.view_target(),
                -45.0 + self.rotate_y_degrees.get(),
                24.0 + self.rotate_x_degrees.get(),
                self.roll_degrees.get(),
                self.perspective_distance.get(),
            )
            return projected[2] if projected else 1e9
        x, y, z = self.rotated((point.x, point.y, point.z))
        if pane.projection.startswith("Top"):
            return y
        if pane.projection.startswith("Front"):
            return z
        return x

    def redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        layer_map = {layer.id: layer for layer in self.document.layers}
        mode = self.display_mode.get()
        points = list(self.document.visible_points())
        if len(points) > 180_000:
            stride = max(1, len(points) // 180_000)
            points = points[::stride]
        for pane in self.panes():
            self.active_event_pane = pane
            self.canvas.create_rectangle(
                pane.x,
                pane.y,
                pane.x + pane.width,
                pane.y + pane.height,
                fill="#0f1418" if pane.projection != "Perspective 3D" else "#080c10",
                outline="#4b5961",
                width=1,
            )
            self.draw_grid(pane)
            pane_points = points
            if pane.projection == "Perspective 3D":
                pane_points = sorted(points, key=lambda item: self.point_depth(item[1], pane), reverse=True)
            for index, point in pane_points:
                layer = layer_map.get(point.layer_id)
                if layer is None:
                    continue
                sx, sy = self.world_to_screen(point, pane)
                if not pane.contains(sx, sy):
                    continue
                if pane.projection == "Perspective 3D":
                    fade = max(0.18, min(1.0, 18.0 / max(1.0, self.point_depth(point, pane))))
                else:
                    depth_delta = abs(self.point_depth(point, pane) - self.depth_value.get())
                    max_depth_delta = max(0.2, self.brush_size.get() * 1.5)
                    fade = max(0.12, 1.0 - depth_delta / max_depth_delta)
                color = self.point_display_color(point, layer, mode, fade)
                size = max(1.0, min(9.0, point.radius * 0.65 * self.document.settings.point_scale))
                outline = "#ffffff" if index in self.document.selected_indices else ""
                self.canvas.create_oval(
                    sx - size,
                    sy - size,
                    sx + size,
                    sy + size,
                    fill=color,
                    outline=outline,
                    width=1,
                )
            self.draw_canvas_bounds(pane)
            self.canvas.create_text(
                pane.x + 8,
                pane.y + 8,
                text=pane.name,
                anchor="nw",
                fill="#a9c4d2",
                font=("Sans", 9, "bold"),
            )
            if pane.projection == "Perspective 3D":
                self.canvas.create_text(
                    pane.x + 8,
                    pane.y + 25,
                    text="Brush/edit here · F5 opens real SignalCloud renderer · B toggles native brush mode",
                    anchor="nw",
                    fill="#6f8793",
                    font=("Sans", 8),
                )
        self.active_event_pane = None
        self.draw_interaction_overlays()

    def request_redraw(self) -> None:
        if self.redraw_after is None:
            self.redraw_after = self.after(16, self._perform_requested_redraw)

    def _perform_requested_redraw(self) -> None:
        self.redraw_after = None
        self.redraw()

    def draw_grid(self, pane: Pane | None = None) -> None:
        pane = pane or self.panes()[0]
        if pane.projection == "Perspective 3D":
            target = self.view_target()
            spacing = max(0.25, self.document.settings.grid_spacing)
            extent = max(self.document.settings.width, self.document.settings.depth) * 0.6
            line_color = "#182329"
            for step in range(-10, 11):
                offset = step * spacing * max(1.0, extent / (spacing * 10.0))
                for start, end in (
                    ((-extent, target[1], offset), (extent, target[1], offset)),
                    ((offset, target[1], -extent), (offset, target[1], extent)),
                ):
                    p1 = PCPPoint(*start)
                    p2 = PCPPoint(*end)
                    x1, y1 = self.world_to_screen(p1, pane)
                    x2, y2 = self.world_to_screen(p2, pane)
                    self.canvas.create_line(x1, y1, x2, y2, fill=line_color)
            return
        zoom = max(1.0, self.zoom.get())
        spacing_world = max(0.05, self.document.settings.grid_spacing)
        spacing = spacing_world * zoom
        while spacing < 18:
            spacing *= 2
        origin_x = pane.x + pane.width / 2 + self.pan_x
        origin_y = pane.y + pane.height / 2 + self.pan_y
        start_x = (origin_x - pane.x) % spacing
        start_y = (origin_y - pane.y) % spacing
        x = pane.x + start_x
        while x < pane.x + pane.width:
            self.canvas.create_line(x, pane.y, x, pane.y + pane.height, fill="#1c252b")
            x += spacing
        y = pane.y + start_y
        while y < pane.y + pane.height:
            self.canvas.create_line(pane.x, y, pane.x + pane.width, y, fill="#1c252b")
            y += spacing
        self.canvas.create_line(origin_x, pane.y, origin_x, pane.y + pane.height, fill="#6e3d3d", width=2)
        self.canvas.create_line(pane.x, origin_y, pane.x + pane.width, origin_y, fill="#3d586e", width=2)

    def draw_canvas_bounds(self, pane: Pane | None = None) -> None:
        pane = pane or self.panes()[0]
        if pane.projection == "Perspective 3D":
            return
        if pane.projection.startswith("Top"):
            hw, hv = self.document.settings.width / 2, self.document.settings.depth / 2
            corners = [PCPPoint(-hw, 0, -hv), PCPPoint(hw, 0, hv)]
        elif pane.projection.startswith("Front"):
            hw, hv = self.document.settings.width / 2, self.document.settings.height / 2
            corners = [PCPPoint(-hw, -hv, 0), PCPPoint(hw, hv, 0)]
        else:
            hw, hv = self.document.settings.depth / 2, self.document.settings.height / 2
            corners = [PCPPoint(0, -hv, -hw), PCPPoint(0, hv, hw)]
        x1, y1 = self.world_to_screen(corners[0], pane)
        x2, y2 = self.world_to_screen(corners[1], pane)
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#3b4c55", dash=(5, 5))

    def draw_interaction_overlays(self) -> None:
        if self.selection_box_start and self.selection_box_end:
            x1, y1 = self.selection_box_start
            x2, y2 = self.selection_box_end
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffdc61", width=2, dash=(6, 3))
        if self.shape_region_start and self.shape_region_end:
            x1, y1 = self.shape_region_start
            x2, y2 = self.shape_region_end
            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#50d7ff", width=2, dash=(4, 3))
        if self.curve_anchors:
            pane = self.active_event_pane or self.selection_pane or self.panes()[0]
            anchors = list(self.curve_anchors)
            if self.curve_hover is not None:
                anchors.append(self.curve_hover)
            self.draw_polyline_overlay(anchors, pane, "#ff74e8")
            for anchor in self.curve_anchors:
                sx, sy = self.world_to_screen(PCPPoint(*anchor), pane)
                self.canvas.create_oval(sx - 5, sy - 5, sx + 5, sy + 5, fill="#ff74e8", outline="#ffffff")
        if self.shape_preview:
            pane = self.shape_pane or self.panes()[0]
            points = self.shape_preview_polyline(self.shape_preview)
            self.draw_polyline_overlay(points, pane, "#48e8ff")

    def draw_polyline_overlay(
        self, points: list[tuple[float, float, float]], pane: Pane, color: str
    ) -> None:
        if len(points) < 2:
            return
        projected = [self.world_to_screen(PCPPoint(*point), pane) for point in points]
        flat = [coordinate for pair in projected for coordinate in pair]
        self.canvas.create_line(*flat, fill=color, width=2, dash=(5, 2))

    def shape_preview_polyline(self, preview: dict[str, float | str]) -> list[tuple[float, float, float]]:
        shape = str(preview.get("shape", "box"))
        cx = float(preview.get("center_x", 0.0))
        cy = float(preview.get("center_y", 0.0))
        cz = float(preview.get("center_z", 0.0))
        if shape == "box":
            sx = max(0.01, float(preview.get("size_x", 1.0))) / 2
            sy = max(0.01, float(preview.get("size_y", 1.0))) / 2
            sz = max(0.01, float(preview.get("size_z", 1.0))) / 2
            corners = {
                key: (cx + x * sx, cy + y * sy, cz + z * sz)
                for key, (x, y, z) in {
                    "000": (-1, -1, -1), "100": (1, -1, -1), "110": (1, 1, -1), "010": (-1, 1, -1),
                    "001": (-1, -1, 1), "101": (1, -1, 1), "111": (1, 1, 1), "011": (-1, 1, 1),
                }.items()
            }
            order = ["000", "100", "110", "010", "000", "001", "101", "111", "011", "001", "101", "100", "110", "111", "011", "010"]
            return [corners[key] for key in order]
        radius = max(0.01, float(preview.get("radius", 1.0)))
        if shape == "sphere":
            return [
                (cx + math.cos(step * math.tau / 48) * radius, cy, cz + math.sin(step * math.tau / 48) * radius)
                for step in range(49)
            ]
        height = max(0.01, float(preview.get("height", 2.0)))
        lower = [
            (cx + math.cos(step * math.tau / 32) * radius, cy - height / 2, cz + math.sin(step * math.tau / 32) * radius)
            for step in range(33)
        ]
        upper = [
            (cx + math.cos(step * math.tau / 32) * radius, cy + height / 2, cz + math.sin(step * math.tau / 32) * radius)
            for step in range(33)
        ]
        return lower + [upper[0]] + upper

    # ---------- Canvas interaction ----------
    def canvas_motion(self, event: tk.Event) -> None:
        pane = self.pane_at(event.x, event.y)
        world = self.screen_to_world(event.x, event.y, pane)
        self.coords_text.set(f"x {world[0]:.2f} · y {world[1]:.2f} · z {world[2]:.2f}")
        if self.tool.get() == "line" and self.curve_anchors:
            self.curve_hover = world
            self.request_redraw()

    def canvas_press(self, event: tk.Event) -> None:
        self.left_button_down = True
        self.left_button_moved = False
        self.double_left = False
        pane = self.pane_at(event.x, event.y)
        self.active_event_pane = pane
        world = self.screen_to_world(event.x, event.y, pane)
        self.drag_start = world
        tool = self.tool.get()
        if tool in {"rotate", "roll"}:
            self.rotate_anchor = (
                event.x,
                event.y,
                self.rotate_x_degrees.get(),
                self.rotate_y_degrees.get(),
                self.roll_degrees.get(),
            )
            self.schedule_reset_hold()
            return
        if self.shape_mode:
            self.begin_shape_region(event, pane)
            return
        if tool == "pan":
            self.pan_press(event)
            return
        if tool == "select":
            self.begin_selection(event, pane)
            return
        if tool == "picker":
            self.pick_nearest(world)
            return
        if tool == "line":
            if not self.curve_anchors:
                self.curve_anchors = [world]
                self.selection_pane = pane
                self.update_status("Curve start placed · right-click adds anchors · left-click finishes")
            else:
                anchors = [*self.curve_anchors, world]
                self.generate_curve(anchors)
            self.redraw()
            return
        self.push_history(TOOLS_DICT.get(tool, tool))
        self.stroke_last_world = None
        self.apply_tool(world, first=True)

    def canvas_double_left(self, event: tk.Event) -> None:
        if self.tool.get() == "rotate":
            self.double_left = True
            self.rotate_x_degrees.set(self.rotate_x_degrees.get() + 5.0)
            self.rotation_changed("Rotate X +5°")
        elif self.tool.get() == "roll":
            self.double_left = True
            self.roll_degrees.set(self.roll_degrees.get() + 5.0)
            self.rotation_changed("Roll +5°")

    def canvas_drag(self, event: tk.Event) -> None:
        tool = self.tool.get()
        if tool in {"rotate", "roll"}:
            self.left_button_moved = True
            self.drag_rotation(event, button=1)
            return
        if self.shape_mode and self.shape_region_start:
            self.shape_region_end = (event.x, event.y)
            self.request_redraw()
            return
        if tool == "select" and self.selection_box_start:
            self.selection_dragged = True
            self.selection_box_end = (event.x, event.y)
            self.request_redraw()
            return
        if tool == "pan":
            self.pan_drag(event)
            return
        if tool in {"pencil", "brush", "eraser", "recolor"}:
            pane = self.pane_at(event.x, event.y)
            world = self.screen_to_world(event.x, event.y, pane)
            self.apply_tool(world, first=False)

    def canvas_release(self, event: tk.Event) -> None:
        tool = self.tool.get()
        if tool in {"rotate", "roll"}:
            if not self.left_button_moved and not self.double_left:
                if tool == "rotate":
                    self.rotate_x_degrees.set(self.rotate_x_degrees.get() + 1.0)
                    self.rotation_changed("Rotate X +1°")
                else:
                    self.roll_degrees.set(self.roll_degrees.get() + 1.0)
                    self.rotation_changed("Roll +1°")
            self.rotate_anchor = None
        elif self.shape_mode and self.shape_region_start:
            self.shape_region_end = (event.x, event.y)
            self.finish_shape_region()
        elif tool == "select" and self.selection_box_start:
            self.selection_box_end = (event.x, event.y)
            if self.selection_dragged and self.selection_distance() >= 4.0:
                self.finish_selection_region()
            else:
                self.selection_waiting_second = True
                self.update_status("Selection first corner placed · click the opposite corner or drag either corner")
                self.redraw()
        elif tool in {"pencil", "brush", "eraser", "recolor"}:
            self.finish_edit(f"{TOOLS_DICT.get(tool, tool)} stroke")
        self.left_button_down = False
        self.stroke_last_world = None
        self.drag_start = None
        self.cancel_reset_hold_if_released()

    def canvas_right_press(self, event: tk.Event) -> None:
        self.right_button_down = True
        self.right_button_moved = False
        self.double_right = False
        pane = self.pane_at(event.x, event.y)
        world = self.screen_to_world(event.x, event.y, pane)
        tool = self.tool.get()
        if tool in {"rotate", "roll"}:
            self.rotate_anchor = (
                event.x,
                event.y,
                self.rotate_x_degrees.get(),
                self.rotate_y_degrees.get(),
                self.roll_degrees.get(),
            )
            self.schedule_reset_hold()
            return
        if tool == "line":
            if not self.curve_anchors:
                self.curve_anchors = [world]
                self.selection_pane = pane
            else:
                self.curve_anchors.append(world)
            self.update_status(f"Curve anchor added · {len(self.curve_anchors)} anchor(s)")
            self.redraw()

    def canvas_double_right(self, event: tk.Event) -> None:
        tool = self.tool.get()
        if tool == "rotate":
            self.double_right = True
            self.rotate_y_degrees.set(self.rotate_y_degrees.get() + 5.0)
            self.rotation_changed("Rotate Y +5°")
        elif tool == "roll":
            self.double_right = True
            self.roll_degrees.set(self.roll_degrees.get() - 5.0)
            self.rotation_changed("Roll −5°")
        elif tool == "line" and self.curve_anchors:
            pane = self.pane_at(event.x, event.y)
            world = self.screen_to_world(event.x, event.y, pane)
            nearest = min(range(len(self.curve_anchors)), key=lambda i: sum((self.curve_anchors[i][axis] - world[axis]) ** 2 for axis in range(3)))
            self.curve_anchors.pop(nearest)
            self.update_status("Nearest curve anchor removed")
            self.redraw()

    def canvas_right_drag(self, event: tk.Event) -> None:
        if self.tool.get() in {"rotate", "roll"}:
            self.right_button_moved = True
            self.drag_rotation(event, button=3)

    def canvas_right_release(self, _event: tk.Event) -> None:
        tool = self.tool.get()
        if tool in {"rotate", "roll"}:
            if not self.right_button_moved and not self.double_right:
                if tool == "rotate":
                    self.rotate_y_degrees.set(self.rotate_y_degrees.get() + 1.0)
                    self.rotation_changed("Rotate Y +1°")
                else:
                    self.roll_degrees.set(self.roll_degrees.get() - 1.0)
                    self.rotation_changed("Roll −1°")
            self.rotate_anchor = None
        self.right_button_down = False
        self.cancel_reset_hold_if_released()

    def drag_rotation(self, event: tk.Event, button: int) -> None:
        if self.rotate_anchor is None:
            return
        start_x, start_y, base_x, base_y, base_z = self.rotate_anchor
        dx = event.x - start_x
        dy = event.y - start_y
        if self.tool.get() == "rotate":
            if button == 1:
                self.rotate_x_degrees.set(base_x + dy * 0.35)
            else:
                self.rotate_y_degrees.set(base_y + dx * 0.35)
        else:
            direction = 1.0 if button == 1 else -1.0
            self.roll_degrees.set(base_z + dx * 0.35 * direction)
        self.rotation_changed("Free view rotation", schedule_preview=False)

    def rotation_changed(self, message: str, schedule_preview: bool = False) -> None:
        self.rotation_label.configure(
            text=f"X {self.rotate_x_degrees.get():.1f}° · Y {self.rotate_y_degrees.get():.1f}° · Z {self.roll_degrees.get():.1f}°"
        )
        self.update_status(message)
        self.redraw()
        if schedule_preview:
            self.schedule_live_preview()

    def schedule_reset_hold(self) -> None:
        if self.left_button_down and self.right_button_down and self.reset_hold_after is None:
            self.reset_prompted = False
            self.reset_hold_after = self.after(5000, self._reset_hold_elapsed)

    def _reset_hold_elapsed(self) -> None:
        self.reset_hold_after = None
        if self.left_button_down and self.right_button_down and not self.reset_prompted:
            self.reset_prompted = True
            if messagebox.askyesno("Reset view angles", "Reset Rotate X/Y and Roll Z to the starting default?"):
                self.reset_view_angles()
            else:
                self.update_status("View-angle reset canceled")

    def cancel_reset_hold_if_released(self) -> None:
        if self.left_button_down and self.right_button_down:
            return
        if self.reset_hold_after is not None:
            self.after_cancel(self.reset_hold_after)
            self.reset_hold_after = None

    def prompt_reset_angles(self) -> None:
        if messagebox.askyesno("Reset view angles", "Reset Rotate X/Y and Roll Z to the starting default?"):
            self.reset_view_angles()

    def reset_view_angles(self) -> None:
        self.rotate_x_degrees.set(0.0)
        self.rotate_y_degrees.set(0.0)
        self.roll_degrees.set(0.0)
        self.rotation_changed("View angles reset")

    # ---------- Region selection ----------
    def begin_selection(self, event: tk.Event, pane: Pane) -> None:
        if self.selection_waiting_second and self.selection_box_start:
            self.selection_box_end = (event.x, event.y)
            self.selection_pane = self.selection_pane or pane
            self.finish_selection_region()
            return
        self.selection_box_start = (event.x, event.y)
        self.selection_box_end = (event.x, event.y)
        self.selection_pane = pane
        self.selection_waiting_second = False
        self.selection_dragged = False
        self.selection_additive = bool(event.state & 0x0001)
        self.redraw()

    def selection_distance(self) -> float:
        if not self.selection_box_start or not self.selection_box_end:
            return 0.0
        return math.dist(self.selection_box_start, self.selection_box_end)

    def finish_selection_region(self) -> None:
        if not self.selection_box_start or not self.selection_box_end:
            return
        pane = self.selection_pane or self.panes()[0]
        x1, y1 = self.selection_box_start
        x2, y2 = self.selection_box_end
        selected = region_indices(
            self.document.visible_points(),
            lambda point: self.world_to_screen(point, pane),
            x1,
            y1,
            x2,
            y2,
        )
        if not self.selection_additive:
            self.document.selected_indices.clear()
        self.document.selected_indices.update(selected)
        self.selection_box_start = None
        self.selection_box_end = None
        self.selection_pane = None
        self.selection_waiting_second = False
        self.selection_dragged = False
        self.update_status(f"Selected {len(self.document.selected_indices)} point(s) in region")
        self.redraw()

    # ---------- Guided shapes ----------
    def activate_shape_tool(self, shape: str) -> None:
        self.shape_mode = shape
        self.shape_preview = None
        self.shape_region_start = None
        self.shape_region_end = None
        self.update_status(f"{shape.title()} generator active · select a grid region")

    def begin_shape_region(self, event: tk.Event, pane: Pane) -> None:
        self.shape_region_start = (event.x, event.y)
        self.shape_region_end = (event.x, event.y)
        self.shape_pane = pane
        self.redraw()

    def finish_shape_region(self) -> None:
        if not self.shape_mode or not self.shape_region_start or not self.shape_region_end:
            return
        pane = self.shape_pane or self.panes()[0]
        x1, y1 = self.shape_region_start
        x2, y2 = self.shape_region_end
        if math.dist((x1, y1), (x2, y2)) < 4.0:
            x2, y2 = x1 + 40, y1 + 40
        a = self.screen_to_world(x1, y1, pane)
        b = self.screen_to_world(x2, y2, pane)
        center = tuple((a[index] + b[index]) * 0.5 for index in range(3))
        size = [max(0.1, abs(a[index] - b[index])) for index in range(3)]
        missing_axis = min(range(3), key=lambda axis: size[axis])
        size[missing_axis] = max(0.5, self.brush_size.get() * 2.0)
        initial = {
            "center_x": center[0],
            "center_y": center[1],
            "center_z": center[2],
            "size_x": size[0],
            "size_y": size[1],
            "size_z": size[2],
            "radius": max(size) * 0.5,
            "height": max(size[1], self.brush_size.get() * 2.0),
            "spacing": max(0.03, self.brush_spacing.get()),
        }
        shape = self.shape_mode
        self.shape_region_start = None
        self.shape_region_end = None
        ShapeParameterDialog(self, shape, initial, lambda values: self.generate_shape_from_values(shape, values))

    def generate_shape_from_values(self, shape: str, values: dict[str, float]) -> None:
        self.push_history(f"Generate {shape}")
        center = (values["center_x"], values["center_y"], values["center_z"])
        common = (
            self.document.active_layer_id,
            self.current_color(),
            self.point_radius.get(),
            self.semantic.get(),
        )
        spacing = max(0.03, values["spacing"])
        if shape == "box":
            points = primitive_box(
                center,
                (values["size_x"], values["size_y"], values["size_z"]),
                spacing,
                *common,
            )
        elif shape == "sphere":
            points = primitive_sphere(center, values["radius"], spacing, *common)
        else:
            points = primitive_cylinder(center, values["radius"], values["height"], spacing, *common)
        self.document.add_points(points)
        self.finish_edit(f"{shape.title()} generated ({len(points):,} points)")

    # Keep legacy menu hooks routed into the new guided workflow.
    def shape_dialog(self, shape: str) -> None:
        self.activate_shape_tool(shape)

    # ---------- Curve tool ----------
    def generate_curve(self, anchors: list[tuple[float, float, float]]) -> None:
        if len(anchors) < 2:
            return
        self.push_history("Line / Curve")
        curve = catmull_rom_points(anchors, samples_per_segment=24)
        sampled = resample_polyline(curve, max(0.02, self.brush_spacing.get()))
        points = [self.make_point(*position) for position in sampled]
        self.document.add_points(points)
        self.curve_anchors.clear()
        self.curve_hover = None
        self.finish_edit(f"Curve generated ({len(points):,} points)")

    # ---------- Faster strokes and 3D pane brushing ----------
    def apply_tool(self, world: tuple[float, float, float], first: bool) -> None:
        tool = self.tool.get()
        layer = self.document.active_layer()
        if layer.locked:
            self.update_status("Active layer is locked")
            return
        positions = [world]
        if self.stroke_last_world is not None and tool in {"pencil", "brush", "eraser", "recolor"}:
            spacing = max(0.01, min(self.brush_spacing.get(), 1.25 / max(2.0, self.zoom.get())))
            positions = resample_polyline([self.stroke_last_world, world], spacing)[1:]
            if not positions:
                positions = [world]
        for position in positions:
            if tool == "pencil":
                self.document.add_point(self.make_point(*position))
            elif tool == "brush":
                self.document.add_points(self.brush_points(position))
            elif tool == "eraser":
                self.document.erase_sphere(*position, self.brush_size.get(), active_layer_only=False)
            elif tool == "recolor":
                self.document.recolor_sphere(*position, self.brush_size.get(), self.current_color())
        self.stroke_last_world = world
        self.request_redraw()
        self.update_status()

    # ---------- Layer visibility ----------
    def layer_row_click(self, event: tk.Event) -> str | None:
        row = self.layer_tree.identify_row(event.y)
        column = self.layer_tree.identify_column(event.x)
        if row and column == "#1":
            layer = next((item for item in self.document.layers if str(item.id) == row), None)
            if layer is not None:
                self.push_history("Layer visibility")
                layer.visible = not layer.visible
                self.document.dirty = True
                self.finish_edit(f"Layer {'shown' if layer.visible else 'hidden'}: {layer.name}")
                return "break"
        return None

    def layer_toggle_visible(self, event: tk.Event) -> None:
        # Double-click remains accepted anywhere on the row for accessibility.
        row = self.layer_tree.identify_row(event.y)
        if not row:
            return
        layer = next((item for item in self.document.layers if str(item.id) == row), None)
        if layer is None:
            return
        self.push_history("Layer visibility")
        layer.visible = not layer.visible
        self.document.dirty = True
        self.finish_edit(f"Layer {'shown' if layer.visible else 'hidden'}: {layer.name}")

    # ---------- Native 3D brush bridge ----------
    def native_brush_command_path(self) -> Path:
        return self.root_path / "user_data" / "pcp3" / "autosave" / "native_brush_commands.jsonl"

    def launch_native_preview(self) -> None:
        binary = self.root_path / "build" / "almond_signal_pcp_preview"
        if not binary.exists():
            messagebox.showerror("Preview not built", "Run ./scripts/setup_dev_environment.sh first.")
            return
        self.write_live_preview()
        if self.preview_process is not None and self.preview_process.poll() is None:
            self.update_status("Native preview is already running · press B there to toggle 3D brush mode")
            return
        command_path = self.native_brush_command_path()
        command_path.parent.mkdir(parents=True, exist_ok=True)
        command_path.write_text("", encoding="utf-8")
        self.preview_command_offset = 0
        try:
            self.preview_process = subprocess.Popen(
                [
                    str(binary),
                    f"--root={self.root_path}",
                    f"--asset={self.autosave_path().with_suffix('.pcp3cloud')}",
                    f"--brush-commands={command_path}",
                    "--live",
                ],
                cwd=self.root_path,
            )
            self.update_status(
                "Native preview launched · B toggles 3D brush · left paints · right erases · middle orbits"
            )
        except OSError as exc:
            messagebox.showerror("Preview launch failed", str(exc))

    def poll_native_brush_commands(self) -> None:
        path = self.native_brush_command_path()
        if path.exists():
            try:
                size = path.stat().st_size
                if size < self.preview_command_offset:
                    self.preview_command_offset = 0
                if size > self.preview_command_offset:
                    with path.open("r", encoding="utf-8") as handle:
                        handle.seek(self.preview_command_offset)
                        lines = handle.readlines()
                        self.preview_command_offset = handle.tell()
                    commands = []
                    for line in lines:
                        try:
                            command = json.loads(line)
                            if all(key in command for key in ("action", "x", "y", "z")):
                                commands.append(command)
                        except json.JSONDecodeError:
                            continue
                    if commands:
                        self.push_history("Native 3D brush")
                        for command in commands:
                            world = (float(command["x"]), float(command["y"]), float(command["z"]))
                            if command["action"] == "erase":
                                self.document.erase_sphere(*world, self.brush_size.get(), active_layer_only=False)
                            else:
                                self.document.add_points(self.brush_points_3d(world))
                        self.finish_edit(f"Native 3D brush · {len(commands)} sample(s)")
            except OSError:
                pass
        self.preview_poll_after = self.after(100, self.poll_native_brush_commands)

    def brush_points_3d(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        spacing = max(0.05, self.brush_spacing.get())
        radius = max(spacing, self.brush_size.get())
        steps = max(1, min(10, int(math.ceil(radius / spacing))))
        points: list[PCPPoint] = []
        for ix in range(-steps, steps + 1):
            for iy in range(-steps, steps + 1):
                for iz in range(-steps, steps + 1):
                    dx, dy, dz = ix * spacing, iy * spacing, iz * spacing
                    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if distance > radius:
                        continue
                    probability = self.brush_hardness.get() + (1.0 - self.brush_hardness.get()) * max(0.0, 1.0 - distance / radius)
                    if random.random() <= probability:
                        points.append(self.make_point(world[0] + dx, world[1] + dy, world[2] + dz, max(0.1, 1.0 - distance / (radius * 1.2))))
        return points

    # ---------- Misc overrides ----------
    def mouse_wheel(self, event: tk.Event) -> None:
        pane = self.pane_at(event.x, event.y)
        if pane.projection == "Perspective 3D":
            self.perspective_distance.set(
                max(0.5, min(5000.0, self.perspective_distance.get() * (0.88 if event.delta > 0 else 1 / 0.88)))
            )
        else:
            self.zoom.set(max(2.0, min(400.0, self.zoom.get() * (1.12 if event.delta > 0 else 1 / 1.12))))
        self.redraw()

    def mouse_wheel_linux(self, event: tk.Event, direction: int) -> None:
        pane = self.pane_at(event.x, event.y)
        if pane.projection == "Perspective 3D":
            self.perspective_distance.set(
                max(0.5, min(5000.0, self.perspective_distance.get() * (0.88 if direction > 0 else 1 / 0.88)))
            )
        else:
            self.zoom.set(max(2.0, min(400.0, self.zoom.get() * (1.12 if direction > 0 else 1 / 1.12))))
        self.redraw()

    def clear_selection(self) -> None:
        self.document.selected_indices.clear()
        self.line_start = None
        self.curve_anchors.clear()
        self.curve_hover = None
        self.selection_box_start = None
        self.selection_box_end = None
        self.selection_waiting_second = False
        self.shape_region_start = None
        self.shape_region_end = None
        self.redraw()
        self.update_status("Selection and active guides cleared")

    def frame_all(self) -> None:
        lower, upper = self.document.bounds()
        size = max(upper[index] - lower[index] for index in range(3))
        width = max(100, self.canvas.winfo_width())
        height = max(100, self.canvas.winfo_height())
        divisor = 2 if self.view_type.get() in {"3-Square", "4-Square"} else 1
        self.zoom.set(max(2.0, min(160.0, 0.72 * min(width / divisor, height / divisor) / max(1.0, size))))
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.perspective_distance.set(max(2.0, size * 2.1))
        self.redraw()

    def update_tool_hud(self) -> None:
        label = TOOLS_DICT.get(self.tool.get(), self.tool.get())
        self.active_tool_label.configure(text=label)
        self.shape_mode = None
        if self.tool.get() != "line":
            self.curve_anchors.clear()
            self.curve_hover = None
        self.update_status(f"Active tool: {label} · {self.tool_help(self.tool.get())}")
        self.redraw()

    def tool_help(self, key: str) -> str:
        return {
            "select": "Click one corner then the opposite corner, or click-drag a live region border. Shift adds to the selection.",
            "pencil": "Paints a continuously interpolated precision line on the active edit plane.",
            "brush": "Paints a dense 2D disc; in the Perspective pane it paints on the camera-facing edit plane.",
            "eraser": "Removes points inside the full 3D brush radius.",
            "recolor": "Changes point RGBA values inside the brush radius.",
            "picker": "Samples color, alpha, radius, and semantic attributes from the nearest point.",
            "line": "Left-click start/end. Right-click adds curve anchors. Double-right-click removes the nearest anchor.",
            "rotate": "Left controls X, right controls Y. Click +1°, double-click +5°, or hold-drag freely.",
            "roll": "Left is positive Z roll; right is negative. Click ±1°, double-click ±5°, or hold-drag freely.",
            "pan": "Drag the active 2D canvas. Middle-drag always pans.",
        }.get(key, "")

    def show_tools_help(self) -> None:
        window = tk.Toplevel(self)
        window.title("Point Cloud Paint++ — Tools Help")
        window.geometry("760x700")
        window.transient(self)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="word", padx=10, pady=10)
        scrollbar = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        sections = [
            ("Select Region", self.tool_help("select") + " A click without dragging leaves the first corner active until the second click."),
            ("Point Pencil", self.tool_help("pencil") + " Branch 2 fills the gaps between motion events for cleaner lines."),
            ("3D Brush", self.tool_help("brush") + " Press F5 for the real renderer; press B in that window for native brush mode."),
            ("Eraser", self.tool_help("eraser")),
            ("Recolor", self.tool_help("recolor")),
            ("Attribute Picker", self.tool_help("picker")),
            ("Line / Curve", self.tool_help("line") + " Press Esc to cancel the active anchor chain."),
            ("Rotate", self.tool_help("rotate") + " Hold both left and right for five seconds to request a complete angle reset."),
            ("Roll", self.tool_help("roll") + " The same five-second two-button reset applies."),
            ("Guided Shapes", "Click Box, Sphere, or Cylinder; select a region; then use paired inputs and sliders. Cyan lines show the live result before generation."),
            ("3-Square", "Shows X, Y, and Z axis projections in three equal editing panes. Selecting All X/Y/Z switches to this view automatically."),
            ("4-Square", "Shows Z, Y, X, and a perspective editing bridge. Selecting All X/Y/Z/NP switches to this view automatically."),
            ("Native SignalCloud Preview", "F5 opens the real PointRenderer. B toggles native brush mode, left paints, right erases, middle-drag orbits, and R reloads."),
            ("Layer Visibility", "Click anywhere inside the Visibility column for a layer row; the larger hit area replaces the tiny bubble-only requirement."),
        ]
        for heading, body in sections:
            text.insert("end", heading + "\n", "heading")
            text.insert("end", body + "\n\n")
        text.tag_configure("heading", font=("Sans", 12, "bold"), foreground="#5aaacb")
        text.configure(state="disabled")

    def show_scope(self) -> None:
        messagebox.showinfo(
            "Point Cloud Paint++ Branch 2 scope",
            (
                "Branch 2 adds rotate/roll controls, guided shapes, 3-Square and 4-Square editing, region selection, "
                "curve anchors, faster pencil interpolation, a complete tools guide, a perspective editing pane, and "
                "a native SignalCloud brush command bridge. Advanced skeletal timelines, liquid simulation, encounter "
                "graphs, GPU octrees, and plugins remain staged future work."
            ),
        )

    def on_close(self) -> None:
        if not self.confirm_discard():
            return
        if self.preview_poll_after is not None:
            self.after_cancel(self.preview_poll_after)
        self.destroy()


def main(root_path: Path) -> int:
    editor = PCP3Editor(root_path)
    editor.mainloop()
    return 0
