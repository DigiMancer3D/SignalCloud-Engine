from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Any

from tools.signalcloud_studio.ui import ToolTip

from .io import export_asset, export_ply, import_ply, load_project, save_project, slugify
from .model import (
    ENVIRONMENT_LABELS,
    ENVIRONMENT_TYPES,
    SEMANTIC_FLAGS,
    Layer,
    PCPDocument,
    PCPPoint,
    primitive_box,
    primitive_cylinder,
    primitive_line,
    primitive_sphere,
)

TOOLS = (
    ("select", "Select"),
    ("pencil", "Point Pencil"),
    ("brush", "3D Brush"),
    ("eraser", "Eraser"),
    ("recolor", "Recolor"),
    ("picker", "Attribute Picker"),
    ("line", "Line / Curve"),
    ("pan", "Pan"),
)

DISPLAY_MODES = ("RGB", "Layer", "Point", "Semantic", "Tool")
PROJECTIONS = ("Top X/Z", "Front X/Y", "Side Z/Y")



class PCP3Editor(tk.Tk):
    def __init__(self, root_path: Path) -> None:
        super().__init__()
        self.root_path = root_path.resolve()
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3")
        self.geometry("1420x900")
        self.minsize(1080, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.document = PCPDocument.new("environment_object")
        self.project_path: Path | None = None
        self.history: list[dict[str, Any]] = []
        self.future: list[dict[str, Any]] = []
        self.preview_process: subprocess.Popen[Any] | None = None
        self.preview_write_after: str | None = None
        self.drag_start: tuple[float, float, float] | None = None
        self.pan_anchor: tuple[int, int, float, float] | None = None
        self.line_start: tuple[float, float, float] | None = None
        self.selection_box_start: tuple[int, int] | None = None

        self.tool = tk.StringVar(value="brush")
        self.display_mode = tk.StringVar(value="RGB")
        self.projection = tk.StringVar(value="Top X/Z")
        self.depth_value = tk.DoubleVar(value=0.0)
        self.zoom = tk.DoubleVar(value=28.0)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.brush_size = tk.DoubleVar(value=0.8)
        self.brush_hardness = tk.DoubleVar(value=0.75)
        self.brush_spacing = tk.DoubleVar(value=0.22)
        self.point_radius = tk.DoubleVar(value=2.0)
        self.color_hex = tk.StringVar(value="#d9cc94")
        self.alpha = tk.DoubleVar(value=1.0)
        self.semantic = tk.StringVar(value="generic")
        self.environment_type = tk.StringVar(value=self.document.environment_type)
        self.status = tk.StringVar(value="Ready · create points in the 2D canvas and preview them through SignalCloud")
        self.point_count_text = tk.StringVar(value="0 points")
        self.coords_text = tk.StringVar(value="x 0.00 · y 0.00 · z 0.00")
        self.auto_live_preview = tk.BooleanVar(value=True)

        self._build_menu()
        self._build_toolbar()
        self._build_workspace()
        self._bind_shortcuts()
        self._sync_all_from_document()
        self.push_history("New document")

    # ---------- UI construction ----------
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
        view_menu.add_command(label="Frame All", accelerator="F", command=self.frame_all)
        view_menu.add_command(label="Native SignalCloud Preview", accelerator="F5", command=self.launch_native_preview)
        menu.add_cascade(label="View", menu=view_menu)

        environment_menu = tk.Menu(menu, tearoff=False)
        for kind in ENVIRONMENT_TYPES:
            environment_menu.add_radiobutton(
                label=ENVIRONMENT_LABELS[kind], value=kind, variable=self.environment_type,
                command=self.change_environment_type,
            )
        menu.add_cascade(label="Environment", menu=environment_menu)

        tools_menu = tk.Menu(menu, tearoff=False)
        for key, label in TOOLS:
            tools_menu.add_radiobutton(label=label, value=key, variable=self.tool, command=self.update_tool_hud)
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
        help_menu.add_command(label="Branch Scope", command=self.show_scope)
        help_menu.add_command(label="Format Information", command=self.show_format_info)
        menu.add_cascade(label="Help", menu=help_menu)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        for text, command in (
            ("New", self.new_document), ("Open", self.open_project), ("Save", self.save),
            ("Export Asset", self.export_to_database), ("Undo", self.undo), ("Redo", self.redo),
            ("Native Preview", self.launch_native_preview),
        ):
            ttk.Button(bar, text=text, command=command).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(bar, text="Environment:").pack(side="left")
        environment_box = ttk.Combobox(
            bar, textvariable=self.environment_type,
            values=ENVIRONMENT_TYPES, state="readonly", width=20,
        )
        environment_box.pack(side="left", padx=4)
        environment_box.bind("<<ComboboxSelected>>", lambda _event: self.change_environment_type())
        ttk.Label(bar, text="Projection:").pack(side="left", padx=(12, 0))
        projection_box = ttk.Combobox(bar, textvariable=self.projection, values=PROJECTIONS, state="readonly", width=12)
        projection_box.pack(side="left", padx=4)
        projection_box.bind("<<ComboboxSelected>>", lambda _event: self.redraw())
        ttk.Label(bar, text="Display:").pack(side="left", padx=(12, 0))
        display_box = ttk.Combobox(bar, textvariable=self.display_mode, values=DISPLAY_MODES, state="readonly", width=10)
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
        ttk.Spinbox(toolbar, from_=0.05, to=10.0, increment=0.05, textvariable=self.brush_spacing, width=7).grid(row=0, column=6, padx=3)
        ttk.Label(toolbar, text="Point px").grid(row=0, column=7)
        ttk.Spinbox(toolbar, from_=0.25, to=255.0, increment=0.25, textvariable=self.point_radius, width=7).grid(row=0, column=8, padx=3)
        ttk.Label(toolbar, text="Semantic").grid(row=0, column=9)
        semantic_box = ttk.Combobox(toolbar, textvariable=self.semantic, values=tuple(SEMANTIC_FLAGS), state="readonly", width=16)
        semantic_box.grid(row=0, column=10, padx=3)
        ttk.Button(toolbar, text="Color", command=self.choose_color).grid(row=0, column=11, padx=(10, 3))
        self.color_swatch = tk.Label(toolbar, width=4, relief="sunken", background=self.color_hex.get())
        self.color_swatch.grid(row=0, column=12, padx=3)
        ttk.Label(toolbar, text="Alpha").grid(row=0, column=13)
        ttk.Spinbox(toolbar, from_=0.0, to=1.0, increment=0.05, textvariable=self.alpha, width=6).grid(row=0, column=14, padx=3)

    def _build_workspace(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8)

        tools_frame = ttk.Frame(paned, padding=5)
        paned.add(tools_frame, weight=0)
        ttk.Label(tools_frame, text="Tools", font=("Sans", 11, "bold")).pack(anchor="w", pady=(0, 4))
        for key, label in TOOLS:
            button = ttk.Radiobutton(tools_frame, text=label, value=key, variable=self.tool, command=self.update_tool_hud)
            button.pack(fill="x", pady=1)
            ToolTip(button, self.tool_help(key))
        ttk.Separator(tools_frame).pack(fill="x", pady=8)
        ttk.Label(tools_frame, text="Shape generators", font=("Sans", 10, "bold")).pack(anchor="w")
        for label, command in (
            ("Box", lambda: self.shape_dialog("box")),
            ("Sphere", lambda: self.shape_dialog("sphere")),
            ("Cylinder", lambda: self.shape_dialog("cylinder")),
            ("Room Shell", self.generate_room_shell),
            ("Humanoid Guide", self.generate_humanoid_guide),
            ("Liquid Plane", self.generate_liquid_plane),
        ):
            ttk.Button(tools_frame, text=label, command=command).pack(fill="x", pady=1)

        center = ttk.Frame(paned)
        paned.add(center, weight=4)
        canvas_toolbar = ttk.Frame(center, padding=(4, 2))
        canvas_toolbar.pack(fill="x")
        ttk.Label(canvas_toolbar, text="Edit plane depth:").pack(side="left")
        depth_scale = ttk.Scale(canvas_toolbar, from_=-50.0, to=50.0, variable=self.depth_value, command=lambda _value: self.redraw())
        depth_scale.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(canvas_toolbar, textvariable=self.coords_text, width=28).pack(side="right")

        self.canvas = tk.Canvas(center, background="#101418", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.canvas_press)
        self.canvas.bind("<B1-Motion>", self.canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
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
        self.layer_tree = ttk.Treeview(layers_tab, columns=("visible", "semantic", "points"), show="tree headings", height=14)
        self.layer_tree.heading("#0", text="Layer")
        self.layer_tree.heading("visible", text="V")
        self.layer_tree.heading("semantic", text="Semantic")
        self.layer_tree.heading("points", text="Points")
        self.layer_tree.column("#0", width=130)
        self.layer_tree.column("visible", width=28, anchor="center")
        self.layer_tree.column("semantic", width=100)
        self.layer_tree.column("points", width=60, anchor="e")
        self.layer_tree.pack(fill="both", expand=True)
        self.layer_tree.bind("<<TreeviewSelect>>", self.layer_selected)
        self.layer_tree.bind("<Double-1>", self.layer_toggle_visible)
        layer_buttons = ttk.Frame(layers_tab)
        layer_buttons.pack(fill="x", pady=(5, 0))
        for text, command in (("+", self.add_layer), ("Copy", self.duplicate_layer), ("−", self.delete_layer), ("↑", lambda: self.move_layer(-1)), ("↓", lambda: self.move_layer(1))):
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
        ttk.Button(layer_props, text="Apply layer properties", command=self.apply_layer_properties).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
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
            ("Asset ID", self.asset_id), ("Display name", self.display_name),
            ("Canvas width", self.canvas_width), ("Canvas height", self.canvas_height),
            ("Canvas depth", self.canvas_depth), ("Ambient light", self.ambient_light),
            ("Point scale", self.document_point_scale), ("Density scale", self.document_density_scale),
            ("Grid spacing", self.grid_spacing), ("Preview zone", self.runtime_zone),
            ("Preview scale", self.runtime_scale),
        )
        for row, (label, variable) in enumerate(rows):
            self._labeled_entry(properties_tab, label, variable, row)
        ttk.Checkbutton(properties_tab, text="Runtime enabled", variable=self.runtime_enabled).grid(row=len(rows), column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(properties_tab, text="Auto-preview in game", variable=self.runtime_game_preview).grid(row=len(rows)+1, column=0, columnspan=2, sticky="w")
        ttk.Button(properties_tab, text="Apply document settings", command=self.apply_document_properties).grid(row=len(rows)+2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
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
        ttk.Button(cert_tab, text="Apply author form", command=self.apply_author_form).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        ttk.Label(cert_tab, text="The first save has no visible version number. Later modifications extend the proof chain; author-form edits also record the editing user.", wraplength=290).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)
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

    def _labeled_entry(self, parent: tk.Misc, label: str, variable: tk.Variable, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 5), pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=2)

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-n>", lambda _event: self.new_document())
        self.bind_all("<Control-o>", lambda _event: self.open_project())
        self.bind_all("<Control-s>", lambda _event: self.save())
        self.bind_all("<Control-Shift-S>", lambda _event: self.save_as())
        self.bind_all("<Control-z>", lambda _event: self.undo())
        self.bind_all("<Control-y>", lambda _event: self.redo())
        self.bind_all("<Control-a>", lambda _event: self.select_all())
        self.bind_all("<Delete>", lambda _event: self.delete_selected())
        self.bind_all("<Escape>", lambda _event: self.clear_selection())
        self.bind_all("<F5>", lambda _event: self.launch_native_preview())
        self.bind_all("<Key-f>", lambda _event: self.frame_all())

    # ---------- model/UI sync ----------
    def _sync_all_from_document(self) -> None:
        self.environment_type.set(self.document.environment_type)
        self.asset_id.set(self.document.asset_id)
        self.display_name.set(self.document.display_name)
        self.canvas_width.set(self.document.settings.width)
        self.canvas_height.set(self.document.settings.height)
        self.canvas_depth.set(self.document.settings.depth)
        self.ambient_light.set(self.document.settings.ambient_light)
        self.document_point_scale.set(self.document.settings.point_scale)
        self.document_density_scale.set(self.document.settings.density_scale)
        self.grid_spacing.set(self.document.settings.grid_spacing)
        self.creator_name.set(self.document.author.creator_name)
        self.creator_title.set(self.document.author.title)
        self.creator_tags.set(", ".join(self.document.author.tags))
        self.creator_description.delete("1.0", "end")
        self.creator_description.insert("1.0", self.document.author.description)
        self.runtime_enabled.set(bool(self.document.runtime.get("enabled", True)))
        self.runtime_game_preview.set(bool(self.document.runtime.get("auto_preview_in_game", False)))
        self.runtime_zone.set(str(self.document.runtime.get("preview_zone", "Reception Tape")))
        self.runtime_scale.set(float(self.document.runtime.get("preview_scale", 1.0)))
        self.refresh_layers()
        self.redraw()
        self.update_status()

    def _sync_document_from_ui(self) -> None:
        self.document.asset_id = slugify(self.asset_id.get() or self.display_name.get())
        self.document.display_name = self.display_name.get().strip() or "Untitled Asset"
        self.document.environment_type = self.environment_type.get()
        self.document.author.asset_type = self.document.environment_type
        self.document.settings.width = max(0.1, float(self.canvas_width.get()))
        self.document.settings.height = max(0.1, float(self.canvas_height.get()))
        self.document.settings.depth = max(0.1, float(self.canvas_depth.get()))
        self.document.settings.ambient_light = max(0.0, float(self.ambient_light.get()))
        self.document.settings.point_scale = max(0.01, float(self.document_point_scale.get()))
        self.document.settings.density_scale = max(0.01, float(self.document_density_scale.get()))
        self.document.settings.grid_spacing = max(0.01, float(self.grid_spacing.get()))
        self.document.runtime["enabled"] = bool(self.runtime_enabled.get())
        self.document.runtime["auto_preview_in_game"] = bool(self.runtime_game_preview.get())
        self.document.runtime["preview_zone"] = self.runtime_zone.get().strip() or "Reception Tape"
        self.document.runtime["preview_scale"] = max(0.01, float(self.runtime_scale.get()))

    def apply_document_properties(self) -> None:
        self.push_history("Document settings")
        try:
            self._sync_document_from_ui()
        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc))
            return
        self.document.dirty = True
        self.update_status("Document settings applied")
        self.redraw()
        self.schedule_live_preview()

    def apply_author_form(self) -> None:
        self.push_history("Author form")
        self.document.author.creator_name = self.creator_name.get().strip()
        self.document.author.title = self.creator_title.get().strip()
        self.document.author.description = self.creator_description.get("1.0", "end-1c").strip()
        self.document.author.tags = [tag.strip() for tag in self.creator_tags.get().split(",") if tag.strip()]
        self.document.author.asset_type = self.document.environment_type
        self.document.dirty = True
        self.finish_edit("Author form updated")
        self.update_status("Creator certificate form updated; next save extends the proof chain if data changed")

    def change_environment_type(self) -> None:
        new_type = self.environment_type.get()
        if new_type not in ENVIRONMENT_TYPES or new_type == self.document.environment_type:
            return
        self.push_history("Environment type")
        self.document.environment_type = new_type
        self.document.author.asset_type = new_type
        self.document.metadata["tool_profile"] = self.document.new(new_type).metadata["tool_profile"]
        self.document.dirty = True
        self.update_status(f"Environment mode: {ENVIRONMENT_LABELS[new_type]}")

    # ---------- history ----------
    def push_history(self, label: str) -> None:
        self.history.append({"label": label, "snapshot": self.document.snapshot()})
        if len(self.history) > 80:
            self.history.pop(0)
        self.future.clear()
        self.refresh_history()

    def undo(self) -> None:
        if len(self.history) <= 1:
            return
        current = self.history.pop()
        self.future.append(current)
        self.document.restore(self.history[-1]["snapshot"])
        self._sync_all_from_document()
        self.update_status(f"Undo: {current['label']}")
        self.refresh_history()
        self.schedule_live_preview()

    def redo(self) -> None:
        if not self.future:
            return
        event = self.future.pop()
        self.history.append(event)
        self.document.restore(event["snapshot"])
        self._sync_all_from_document()
        self.update_status(f"Redo: {event['label']}")
        self.refresh_history()
        self.schedule_live_preview()

    def refresh_history(self) -> None:
        if not hasattr(self, "history_list"):
            return
        self.history_list.delete(0, "end")
        for item in self.history:
            self.history_list.insert("end", item["label"])
        if self.history:
            self.history_list.selection_set(len(self.history) - 1)
            self.history_list.see(len(self.history) - 1)

    # ---------- canvas projection ----------
    def world_to_screen(self, point: PCPPoint) -> tuple[float, float]:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        zoom = self.zoom.get()
        projection = self.projection.get()
        if projection.startswith("Top"):
            horizontal, vertical = point.x, point.z
        elif projection.startswith("Front"):
            horizontal, vertical = point.x, point.y
        else:
            horizontal, vertical = point.z, point.y
        return width / 2 + self.pan_x + horizontal * zoom, height / 2 + self.pan_y - vertical * zoom

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float, float]:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        zoom = max(0.1, self.zoom.get())
        horizontal = (sx - width / 2 - self.pan_x) / zoom
        vertical = -(sy - height / 2 - self.pan_y) / zoom
        depth = self.depth_value.get()
        projection = self.projection.get()
        if projection.startswith("Top"):
            return horizontal, depth, vertical
        if projection.startswith("Front"):
            return horizontal, vertical, depth
        return depth, vertical, horizontal

    def point_depth(self, point: PCPPoint) -> float:
        projection = self.projection.get()
        if projection.startswith("Top"):
            return point.y
        if projection.startswith("Front"):
            return point.z
        return point.x

    def redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        self.draw_grid()
        layer_map = {layer.id: layer for layer in self.document.layers}
        mode = self.display_mode.get()
        active_depth = self.depth_value.get()
        max_depth_delta = max(0.2, self.brush_size.get() * 1.5)
        points = list(self.document.visible_points())
        if len(points) > 180_000:
            stride = max(1, len(points) // 180_000)
            points = points[::stride]
        for index, point in points:
            layer = layer_map.get(point.layer_id)
            if layer is None:
                continue
            sx, sy = self.world_to_screen(point)
            depth_delta = abs(self.point_depth(point) - active_depth)
            fade = max(0.12, 1.0 - depth_delta / max_depth_delta)
            color = self.point_display_color(point, layer, mode, fade)
            size = max(1.0, min(9.0, point.radius * 0.65 * self.document.settings.point_scale))
            outline = "#ffffff" if index in self.document.selected_indices else ""
            self.canvas.create_oval(sx-size, sy-size, sx+size, sy+size, fill=color, outline=outline, width=1)
        if self.line_start is not None and self.tool.get() == "line":
            preview = PCPPoint(*self.line_start)
            sx, sy = self.world_to_screen(preview)
            self.canvas.create_oval(sx-4, sy-4, sx+4, sy+4, outline="#ffffff", width=2)
        self.draw_canvas_bounds()

    def draw_grid(self) -> None:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        zoom = max(1.0, self.zoom.get())
        spacing_world = max(0.05, self.document.settings.grid_spacing)
        spacing = spacing_world * zoom
        while spacing < 18:
            spacing *= 2
        origin_x = width / 2 + self.pan_x
        origin_y = height / 2 + self.pan_y
        start_x = origin_x % spacing
        start_y = origin_y % spacing
        for x in range(int(start_x), width, max(1, int(spacing))):
            self.canvas.create_line(x, 0, x, height, fill="#1c252b")
        for y in range(int(start_y), height, max(1, int(spacing))):
            self.canvas.create_line(0, y, width, y, fill="#1c252b")
        self.canvas.create_line(origin_x, 0, origin_x, height, fill="#6e3d3d", width=2)
        self.canvas.create_line(0, origin_y, width, origin_y, fill="#3d586e", width=2)

    def draw_canvas_bounds(self) -> None:
        projection = self.projection.get()
        if projection.startswith("Top"):
            hw, hv = self.document.settings.width / 2, self.document.settings.depth / 2
        elif projection.startswith("Front"):
            hw, hv = self.document.settings.width / 2, self.document.settings.height / 2
        else:
            hw, hv = self.document.settings.depth / 2, self.document.settings.height / 2
        corners = [PCPPoint(-hw, 0, -hv), PCPPoint(hw, 0, hv)]
        if projection.startswith("Front"):
            corners = [PCPPoint(-hw, -hv, 0), PCPPoint(hw, hv, 0)]
        elif projection.startswith("Side"):
            corners = [PCPPoint(0, -hv, -hw), PCPPoint(0, hv, hw)]
        x1, y1 = self.world_to_screen(corners[0])
        x2, y2 = self.world_to_screen(corners[1])
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#3b4c55", dash=(5, 5))

    def point_display_color(self, point: PCPPoint, layer: Layer, mode: str, fade: float) -> str:
        if mode == "Layer":
            hue = (layer.id * 0.173) % 1.0
            r, g, b = self.hsv_to_rgb(hue, 0.65, 0.95)
        elif mode == "Point":
            value = max(0.0, min(1.0, point.density))
            r, g, b = value, value, value
        elif mode == "Semantic":
            semantic = point.flags & 0xFF
            hue = (semantic * 0.117) % 1.0
            r, g, b = self.hsv_to_rgb(hue, 0.75, 0.95)
        elif mode == "Tool":
            selected = point.layer_id == self.document.active_layer_id and abs(self.point_depth(point) - self.depth_value.get()) <= self.brush_size.get()
            r, g, b = ((1.0, 0.78, 0.22) if selected else (0.25, 0.28, 0.3))
        else:
            r, g, b = point.r, point.g, point.b
        opacity = max(0.0, min(1.0, point.a * layer.opacity * fade))
        background = (0x10/255, 0x14/255, 0x18/255)
        r = background[0] * (1-opacity) + max(0.0, min(1.0, r)) * opacity
        g = background[1] * (1-opacity) + max(0.0, min(1.0, g)) * opacity
        b = background[2] * (1-opacity) + max(0.0, min(1.0, b)) * opacity
        return f"#{round(r*255):02x}{round(g*255):02x}{round(b*255):02x}"

    @staticmethod
    def hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
        i = int(h * 6)
        f = h * 6 - i
        p = v * (1 - s)
        q = v * (1 - f * s)
        t = v * (1 - (1 - f) * s)
        return ((v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q))[i % 6]

    # ---------- canvas events / tools ----------
    def canvas_motion(self, event: tk.Event) -> None:
        x, y, z = self.screen_to_world(event.x, event.y)
        self.coords_text.set(f"x {x:.2f} · y {y:.2f} · z {z:.2f}")

    def canvas_press(self, event: tk.Event) -> None:
        world = self.screen_to_world(event.x, event.y)
        self.drag_start = world
        tool = self.tool.get()
        if tool == "pan":
            self.pan_press(event)
            return
        if tool == "select":
            self.select_nearest(world, additive=bool(event.state & 0x0001))
        elif tool == "picker":
            self.pick_nearest(world)
        elif tool == "line":
            if self.line_start is None:
                self.line_start = world
                self.update_status("Line start placed; click the end point")
                self.redraw()
            else:
                self.push_history("Line")
                self.document.add_points(primitive_line(
                    self.line_start, world, self.brush_spacing.get(), self.document.active_layer_id,
                    self.current_color(), self.point_radius.get(), self.semantic.get(),
                ))
                self.line_start = None
                self.finish_edit("Line generated")
        else:
            self.push_history(TOOLS_DICT.get(tool, tool))
            self.apply_tool(world, first=True)

    def canvas_drag(self, event: tk.Event) -> None:
        tool = self.tool.get()
        if tool == "pan":
            self.pan_drag(event)
            return
        if tool in {"pencil", "brush", "eraser", "recolor"}:
            world = self.screen_to_world(event.x, event.y)
            self.apply_tool(world, first=False)

    def canvas_release(self, _event: tk.Event) -> None:
        if self.tool.get() in {"pencil", "brush", "eraser", "recolor"}:
            self.finish_edit(f"{TOOLS_DICT.get(self.tool.get(), self.tool.get())} stroke")
        self.drag_start = None

    def apply_tool(self, world: tuple[float, float, float], first: bool) -> None:
        tool = self.tool.get()
        layer = self.document.active_layer()
        if layer.locked:
            self.update_status("Active layer is locked")
            return
        if tool == "pencil":
            self.document.add_point(self.make_point(*world))
        elif tool == "brush":
            self.document.add_points(self.brush_points(world))
        elif tool == "eraser":
            self.document.erase_sphere(*world, self.brush_size.get(), active_layer_only=False)
        elif tool == "recolor":
            self.document.recolor_sphere(*world, self.brush_size.get(), self.current_color())
        if first or random.random() > 0.35:
            self.redraw()
            self.update_status()

    def brush_points(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        spacing = max(0.04, self.brush_spacing.get())
        radius = max(spacing, self.brush_size.get())
        hardness = max(0.0, min(1.0, self.brush_hardness.get()))
        steps = max(1, min(18, int(math.ceil(radius / spacing))))
        points: list[PCPPoint] = []
        projection = self.projection.get()
        for a in range(-steps, steps + 1):
            for b in range(-steps, steps + 1):
                da = a * spacing
                db = b * spacing
                distance = math.sqrt(da * da + db * db)
                if distance > radius:
                    continue
                probability = hardness + (1.0-hardness) * max(0.0, 1.0-distance/radius)
                if random.random() > probability:
                    continue
                x, y, z = world
                if projection.startswith("Top"):
                    x += da; z += db
                elif projection.startswith("Front"):
                    x += da; y += db
                else:
                    z += da; y += db
                points.append(self.make_point(x, y, z, density=max(0.1, 1.0-distance/(radius*1.2))))
        return points

    def make_point(self, x: float, y: float, z: float, density: float = 1.0) -> PCPPoint:
        color = self.current_color()
        return PCPPoint(
            x, y, z, self.point_radius.get(), *color,
            0.0, 1.0, 0.0, density,
            self.document.active_layer_id, SEMANTIC_FLAGS.get(self.semantic.get(), 0),
        )

    def current_color(self) -> tuple[float, float, float, float]:
        value = self.color_hex.get().lstrip("#")
        if len(value) != 6:
            value = "d9cc94"
        return tuple(int(value[index:index+2], 16) / 255.0 for index in (0, 2, 4)) + (max(0.0, min(1.0, self.alpha.get())),)

    def choose_color(self) -> None:
        chosen = colorchooser.askcolor(color=self.color_hex.get(), title="Point Cloud Paint++ color")
        if chosen[1]:
            self.color_hex.set(chosen[1])
            self.color_swatch.configure(background=chosen[1])

    def select_nearest(self, world: tuple[float, float, float], additive: bool = False) -> None:
        candidates = [(point.distance_sq(*world), index) for index, point in self.document.visible_points()]
        if not candidates:
            return
        distance, index = min(candidates)
        if distance > max(0.05, self.brush_size.get()) ** 2 * 4:
            if not additive:
                self.clear_selection()
            return
        if not additive:
            self.document.selected_indices.clear()
        if index in self.document.selected_indices and additive:
            self.document.selected_indices.remove(index)
        else:
            self.document.selected_indices.add(index)
        self.update_status(f"Selected {len(self.document.selected_indices)} point(s)")
        self.redraw()

    def pick_nearest(self, world: tuple[float, float, float]) -> None:
        candidates = [(point.distance_sq(*world), point) for _index, point in self.document.visible_points()]
        if not candidates:
            return
        _distance, point = min(candidates, key=lambda item: item[0])
        self.color_hex.set(f"#{round(point.r*255):02x}{round(point.g*255):02x}{round(point.b*255):02x}")
        self.color_swatch.configure(background=self.color_hex.get())
        self.alpha.set(point.a)
        self.point_radius.set(point.radius)
        semantic = next((name for name, value in SEMANTIC_FLAGS.items() if value == (point.flags & 0xFF)), "generic")
        self.semantic.set(semantic)
        self.update_status("Point attributes sampled")

    def mark_dirty(self, label: str = "Project settings changed") -> None:
        """Mark non-geometry authoring controls dirty without creating a full cloud snapshot.

        Metadata toggles can fire frequently and should not duplicate the point cloud in
        undo history.  This helper updates the dirty marker/title/status while leaving
        geometry history untouched.
        """
        self.document.dirty = True
        self.update_status(label)

    def finish_edit(self, label: str) -> None:
        self.document.dirty = True
        self.history[-1] = {"label": label, "snapshot": self.document.snapshot()}
        self.refresh_history()
        self.redraw()
        self.refresh_layers()
        self.update_status(label)
        self.schedule_live_preview()

    def pan_press(self, event: tk.Event) -> None:
        self.pan_anchor = (event.x, event.y, self.pan_x, self.pan_y)

    def pan_drag(self, event: tk.Event) -> None:
        if self.pan_anchor is None:
            return
        x, y, start_x, start_y = self.pan_anchor
        self.pan_x = start_x + event.x - x
        self.pan_y = start_y + event.y - y
        self.redraw()

    def mouse_wheel(self, event: tk.Event) -> None:
        self.zoom.set(max(2.0, min(400.0, self.zoom.get() * (1.12 if event.delta > 0 else 1/1.12))))
        self.redraw()

    def mouse_wheel_linux(self, event: tk.Event, direction: int) -> None:
        self.zoom.set(max(2.0, min(400.0, self.zoom.get() * (1.12 if direction > 0 else 1/1.12))))
        self.redraw()

    # ---------- layers ----------
    def refresh_layers(self) -> None:
        if not hasattr(self, "layer_tree"):
            return
        self.layer_tree.delete(*self.layer_tree.get_children())
        counts: dict[int, int] = {}
        for point in self.document.points:
            counts[point.layer_id] = counts.get(point.layer_id, 0) + 1
        for layer in self.document.layers:
            self.layer_tree.insert("", "end", iid=str(layer.id), text=layer.name,
                                   values=("●" if layer.visible else "○", layer.semantic, counts.get(layer.id, 0)))
        if self.layer_tree.exists(str(self.document.active_layer_id)):
            self.layer_tree.selection_set(str(self.document.active_layer_id))
        self.refresh_active_layer_fields()
        self.update_status()

    def layer_selected(self, _event: tk.Event | None = None) -> None:
        selected = self.layer_tree.selection()
        if not selected:
            return
        self.document.active_layer_id = int(selected[0])
        self.refresh_active_layer_fields()
        self.redraw()

    def refresh_active_layer_fields(self) -> None:
        layer = self.document.active_layer()
        self.layer_name.set(layer.name)
        self.layer_group.set(layer.group)
        self.layer_opacity.set(layer.opacity)
        self.layer_locked.set(layer.locked)
        self.semantic.set(layer.semantic if layer.semantic in SEMANTIC_FLAGS else "generic")

    def layer_toggle_visible(self, event: tk.Event) -> None:
        item = self.layer_tree.identify_row(event.y)
        if not item:
            return
        self.push_history("Layer visibility")
        layer = next((layer for layer in self.document.layers if layer.id == int(item)), None)
        if layer:
            layer.visible = not layer.visible
            self.document.dirty = True
            self.finish_edit("Layer visibility")

    def add_layer(self) -> None:
        name = simpledialog.askstring("Add layer", "Layer name:", initialvalue=f"Layer {len(self.document.layers)+1}", parent=self)
        if name is None:
            return
        self.push_history("Add layer")
        self.document.add_layer(name, self.semantic.get())
        self.finish_edit("Layer added")

    def duplicate_layer(self) -> None:
        source = self.document.active_layer()
        self.push_history("Duplicate layer")
        target = self.document.add_layer(source.name + " Copy", source.semantic)
        target.group = source.group
        target.opacity = source.opacity
        copied = []
        for _index, point in self.document.layer_points(source.id):
            clone = PCPPoint(**asdict(point))
            clone.layer_id = target.id
            copied.append(clone)
        self.document.add_points(copied)
        self.finish_edit("Layer duplicated")

    def delete_layer(self) -> None:
        if len(self.document.layers) <= 1:
            messagebox.showinfo("Layer", "A document must retain at least one layer.")
            return
        layer = self.document.active_layer()
        if not messagebox.askyesno("Delete layer", f"Delete '{layer.name}' and all of its points?"):
            return
        self.push_history("Delete layer")
        self.document.remove_layer(layer.id)
        self.finish_edit("Layer deleted")

    def move_layer(self, delta: int) -> None:
        current = next((index for index, layer in enumerate(self.document.layers) if layer.id == self.document.active_layer_id), -1)
        target = current + delta
        if current < 0 or target < 0 or target >= len(self.document.layers):
            return
        self.push_history("Reorder layers")
        self.document.layers[current], self.document.layers[target] = self.document.layers[target], self.document.layers[current]
        self.document.dirty = True
        self.finish_edit("Layers reordered")

    def apply_layer_properties(self) -> None:
        self.push_history("Layer properties")
        layer = self.document.active_layer()
        layer.name = self.layer_name.get().strip() or layer.name
        layer.group = self.layer_group.get().strip() or "Geometry"
        layer.opacity = max(0.0, min(1.0, self.layer_opacity.get()))
        layer.locked = bool(self.layer_locked.get())
        layer.semantic = self.semantic.get()
        self.document.dirty = True
        self.finish_edit("Layer properties applied")

    # ---------- shapes / effects ----------
    def shape_dialog(self, shape: str) -> None:
        window = tk.Toplevel(self)
        window.title(f"Generate {shape.title()}")
        window.transient(self)
        values = {
            "center_x": tk.DoubleVar(value=0.0), "center_y": tk.DoubleVar(value=self.depth_value.get()), "center_z": tk.DoubleVar(value=0.0),
            "size_x": tk.DoubleVar(value=4.0), "size_y": tk.DoubleVar(value=4.0), "size_z": tk.DoubleVar(value=4.0),
            "radius": tk.DoubleVar(value=2.0), "height": tk.DoubleVar(value=4.0), "spacing": tk.DoubleVar(value=self.brush_spacing.get()),
        }
        labels = ["center_x", "center_y", "center_z", "spacing"]
        if shape == "box": labels += ["size_x", "size_y", "size_z"]
        elif shape == "sphere": labels += ["radius"]
        else: labels += ["radius", "height"]
        for row, key in enumerate(labels):
            ttk.Label(window, text=key.replace("_", " ").title()).grid(row=row, column=0, sticky="w", padx=8, pady=3)
            ttk.Entry(window, textvariable=values[key]).grid(row=row, column=1, padx=8, pady=3)
        def create() -> None:
            self.push_history(f"Generate {shape}")
            center = (values["center_x"].get(), values["center_y"].get(), values["center_z"].get())
            common = (self.document.active_layer_id, self.current_color(), self.point_radius.get(), self.semantic.get())
            if shape == "box":
                points = primitive_box(center, (values["size_x"].get(), values["size_y"].get(), values["size_z"].get()), values["spacing"].get(), *common)
            elif shape == "sphere":
                points = primitive_sphere(center, values["radius"].get(), values["spacing"].get(), *common)
            else:
                points = primitive_cylinder(center, values["radius"].get(), values["height"].get(), values["spacing"].get(), *common)
            self.document.add_points(points)
            window.destroy()
            self.finish_edit(f"{shape.title()} generated ({len(points)} points)")
        ttk.Button(window, text="Generate", command=create).grid(row=len(labels), column=0, columnspan=2, sticky="ew", padx=8, pady=8)

    def generate_room_shell(self) -> None:
        self.push_history("Room shell")
        layer = self.document.add_layer("Room Shell", "wall")
        points = primitive_box((0.0, self.document.settings.height/2, 0.0),
                               (self.document.settings.width, self.document.settings.height, self.document.settings.depth),
                               max(0.18, self.brush_spacing.get()), layer.id, self.current_color(), self.point_radius.get(), "wall")
        self.document.add_points(points)
        self.finish_edit(f"Room shell generated ({len(points)} points)")

    def generate_humanoid_guide(self) -> None:
        self.push_history("Humanoid guide")
        layer = self.document.add_layer("Humanoid Guide", "bone")
        color = self.current_color()
        points: list[PCPPoint] = []
        points += primitive_sphere((0, 1.72, 0), 0.18, 0.10, layer.id, color, self.point_radius.get(), "bone")
        for start, end in (
            ((0, 1.52, 0), (0, 0.86, 0)),
            ((0, 1.40, 0), (-0.55, 1.05, 0)), ((0, 1.40, 0), (0.55, 1.05, 0)),
            ((0, 0.86, 0), (-0.28, 0.0, 0)), ((0, 0.86, 0), (0.28, 0.0, 0)),
        ):
            points += primitive_line(start, end, 0.08, layer.id, color, self.point_radius.get(), "bone")
        self.document.add_points(points)
        self.finish_edit(f"Humanoid guide generated ({len(points)} points)")

    def generate_liquid_plane(self) -> None:
        self.push_history("Liquid plane")
        layer = self.document.add_layer("Liquid Surface", "water_surface")
        y = self.depth_value.get() if self.projection.get().startswith("Top") else 0.0
        spacing = max(0.1, self.brush_spacing.get())
        points: list[PCPPoint] = []
        nx = max(2, int(self.document.settings.width / spacing))
        nz = max(2, int(self.document.settings.depth / spacing))
        color = self.current_color()
        for ix in range(nx + 1):
            x = -self.document.settings.width/2 + self.document.settings.width * ix/nx
            for iz in range(nz + 1):
                z = -self.document.settings.depth/2 + self.document.settings.depth * iz/nz
                points.append(PCPPoint(x, y, z, self.point_radius.get(), *color, 0,1,0, 0.72, layer.id, SEMANTIC_FLAGS["water_surface"], 0.0, 0.0))
        self.document.add_points(points)
        self.finish_edit(f"Liquid surface generated ({len(points)} points)")

    def effect_jitter(self) -> None:
        if not self.document.selected_indices:
            messagebox.showinfo("Jitter", "Select points first.")
            return
        amount = simpledialog.askfloat("Jitter selected", "Maximum displacement:", initialvalue=0.05, minvalue=0.0, parent=self)
        if amount is None:
            return
        self.push_history("Jitter selected")
        for index in self.document.selected_indices:
            if index < len(self.document.points):
                point = self.document.points[index]
                point.x += random.uniform(-amount, amount)
                point.y += random.uniform(-amount, amount)
                point.z += random.uniform(-amount, amount)
        self.finish_edit("Selected points jittered")

    def effect_normalize_radius(self) -> None:
        if not self.document.selected_indices:
            return
        self.push_history("Normalize radius")
        for index in self.document.selected_indices:
            if index < len(self.document.points):
                self.document.points[index].radius = self.point_radius.get()
        self.finish_edit("Selected point radius normalized")

    def effect_mirror(self, axis: str) -> None:
        if not self.document.selected_indices:
            return
        self.push_history(f"Mirror {axis}")
        clones: list[PCPPoint] = []
        for index in self.document.selected_indices:
            if index >= len(self.document.points):
                continue
            clone = PCPPoint(**asdict(self.document.points[index]))
            setattr(clone, axis, -getattr(clone, axis))
            if axis == "x": clone.nx = -clone.nx
            elif axis == "y": clone.ny = -clone.ny
            else: clone.nz = -clone.nz
            clones.append(clone)
        self.document.add_points(clones)
        self.finish_edit(f"Mirrored {len(clones)} point(s) across {axis.upper()}")

    # ---------- selection ----------
    def select_all(self) -> None:
        self.document.selected_indices = {index for index, _point in self.document.visible_points()}
        self.update_status(f"Selected {len(self.document.selected_indices)} visible points")
        self.redraw()

    def clear_selection(self) -> None:
        self.document.selected_indices.clear()
        self.line_start = None
        self.redraw()
        self.update_status("Selection cleared")

    def delete_selected(self) -> None:
        if not self.document.selected_indices:
            return
        self.push_history("Delete selected")
        selected = self.document.selected_indices
        self.document.points = [point for index, point in enumerate(self.document.points) if index not in selected]
        removed = len(selected)
        self.document.selected_indices.clear()
        self.document.dirty = True
        self.finish_edit(f"Deleted {removed} point(s)")

    # ---------- files ----------
    def new_document(self) -> None:
        if not self.confirm_discard():
            return
        selector = tk.Toplevel(self)
        selector.title("New Point Cloud Paint++ asset")
        kind = tk.StringVar(value="environment_object")
        ttk.Label(selector, text="Environment type", font=("Sans", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        box = ttk.Combobox(selector, textvariable=kind, values=ENVIRONMENT_TYPES, state="readonly", width=28)
        box.pack(fill="x", padx=12)
        def create() -> None:
            self.document = PCPDocument.new(kind.get())
            self.project_path = None
            self.history.clear(); self.future.clear()
            self.push_history("New document")
            self._sync_all_from_document()
            selector.destroy()
        ttk.Button(selector, text="Create", command=create).pack(fill="x", padx=12, pady=12)

    def open_project(self) -> None:
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(
            parent=self, title="Open Point Cloud Paint++ project",
            initialdir=self.root_path / "user_data" / "pcp3" / "projects",
            filetypes=(("Point Cloud Paint++", "*.pcp3"), ("All files", "*")),
        )
        if not path:
            return
        try:
            self.document = load_project(Path(path))
            self.project_path = Path(path)
            self.history.clear(); self.future.clear()
            self.push_history("Opened project")
            self._sync_all_from_document()
            self.frame_all()
            self.update_status(f"Opened {path}")
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def save(self) -> bool:
        if self.project_path is None:
            return self.save_as()
        return self._save_to(self.project_path)

    def save_as(self) -> bool:
        default = slugify(self.asset_id.get() or self.display_name.get()) + ".pcp3"
        path = filedialog.asksaveasfilename(
            parent=self, title="Save Point Cloud Paint++ project",
            initialdir=self.root_path / "user_data" / "pcp3" / "projects",
            initialfile=default, defaultextension=".pcp3",
            filetypes=(("Point Cloud Paint++", "*.pcp3"),),
        )
        if not path:
            return False
        self.project_path = Path(path)
        return self._save_to(self.project_path)

    def _save_to(self, path: Path) -> bool:
        try:
            self._sync_document_from_ui()
            self.apply_author_form_silent()
            paths = save_project(self.document, path, editor_name=self.editor_name.get())
            self.project_path = paths["project"]
            self.update_status(f"Saved {paths['project'].name} · certificate and cloud checksums updated")
            self.schedule_live_preview(force=True)
            return True
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            return False

    def apply_author_form_silent(self) -> None:
        self.document.author.creator_name = self.creator_name.get().strip()
        self.document.author.title = self.creator_title.get().strip()
        self.document.author.description = self.creator_description.get("1.0", "end-1c").strip()
        self.document.author.tags = [tag.strip() for tag in self.creator_tags.get().split(",") if tag.strip()]
        self.document.author.asset_type = self.document.environment_type

    def export_to_database(self) -> None:
        if not self.save():
            return
        try:
            self._sync_document_from_ui()
            asset_dir = export_asset(self.document, self.root_path, self.project_path, self.editor_name.get())
            python = self.python_executable()
            subprocess.run([python, str(self.root_path / "tools" / "asset_doctor" / "asset_doctor.py"), str(self.root_path)], check=True, cwd=self.root_path)
            subprocess.run([python, str(self.root_path / "tools" / "stress_content_catalog.py"), str(self.root_path)], check=True, cwd=self.root_path)
            self.update_status(f"Exported to SignalCloud database: {asset_dir.relative_to(self.root_path)}")
            messagebox.showinfo("Export complete", f"Asset exported to:\n{asset_dir}\n\nThe manifest and stress catalog were refreshed.")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def import_ply_file(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Import ASCII PLY", filetypes=(("PLY point cloud", "*.ply"),))
        if not path:
            return
        try:
            self.push_history("Import PLY")
            points = import_ply(Path(path), self.document.active_layer_id)
            self.document.add_points(points)
            self.finish_edit(f"Imported {len(points)} PLY points")
            self.frame_all()
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def export_ply_file(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Export ASCII PLY", defaultextension=".ply", filetypes=(("PLY point cloud", "*.ply"),))
        if not path:
            return
        try:
            export_ply(self.document, Path(path))
            self.update_status(f"Exported PLY: {path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    # ---------- native preview ----------
    def autosave_path(self) -> Path:
        return self.root_path / "user_data" / "pcp3" / "autosave" / "live_preview.pcp3"

    def schedule_live_preview(self, force: bool = False) -> None:
        if not force and not self.auto_live_preview.get():
            return
        if self.preview_write_after is not None:
            self.after_cancel(self.preview_write_after)
        self.preview_write_after = self.after(350, self.write_live_preview)

    def write_live_preview(self) -> None:
        self.preview_write_after = None
        try:
            self._sync_document_from_ui()
            self.apply_author_form_silent()
            save_project(self.document, self.autosave_path(), editor_name=self.editor_name.get())
        except Exception as exc:
            self.update_status(f"Live preview write failed: {exc}")

    def launch_native_preview(self) -> None:
        binary = self.root_path / "build" / "almond_signal_pcp_preview"
        if not binary.exists():
            messagebox.showerror("Preview not built", "Run ./scripts/setup_dev_environment.sh first.")
            return
        self.write_live_preview()
        if self.preview_process is not None and self.preview_process.poll() is None:
            self.update_status("Native preview is already running and will refresh automatically")
            return
        try:
            self.preview_process = subprocess.Popen([
                str(binary), f"--root={self.root_path}", f"--asset={self.autosave_path().with_suffix('.pcp3cloud')}", "--live"
            ], cwd=self.root_path)
            self.update_status("Native SignalCloud preview launched · WASD/QE move · mouse look · F frame · R reload")
        except OSError as exc:
            messagebox.showerror("Preview launch failed", str(exc))

    # ---------- misc ----------
    def frame_all(self) -> None:
        lower, upper = self.document.bounds()
        projection = self.projection.get()
        if projection.startswith("Top"):
            size_h, size_v = upper[0]-lower[0], upper[2]-lower[2]
            center_h, center_v = (upper[0]+lower[0])/2, (upper[2]+lower[2])/2
        elif projection.startswith("Front"):
            size_h, size_v = upper[0]-lower[0], upper[1]-lower[1]
            center_h, center_v = (upper[0]+lower[0])/2, (upper[1]+lower[1])/2
        else:
            size_h, size_v = upper[2]-lower[2], upper[1]-lower[1]
            center_h, center_v = (upper[2]+lower[2])/2, (upper[1]+lower[1])/2
        width = max(100, self.canvas.winfo_width())
        height = max(100, self.canvas.winfo_height())
        self.zoom.set(max(2.0, min(160.0, 0.8 * min(width/max(1.0, size_h), height/max(1.0, size_v)))))
        self.pan_x = -center_h * self.zoom.get()
        self.pan_y = center_v * self.zoom.get()
        self.redraw()

    def update_tool_hud(self) -> None:
        label = TOOLS_DICT.get(self.tool.get(), self.tool.get())
        self.active_tool_label.configure(text=label)
        self.update_status(f"Active tool: {label}")

    def update_status(self, message: str | None = None) -> None:
        if message is not None:
            self.status.set(message)
        self.point_count_text.set(f"{len(self.document.points):,} points · {len(self.document.layers)} layers · {len(self.document.selected_indices)} selected")
        self.refresh_active_title()

    def refresh_active_title(self) -> None:
        name = self.document.display_name or "Untitled Asset"
        dirty = " *" if self.document.dirty else ""
        self.title(f"{name}{dirty} — Point Cloud Paint++ · +PCP+ · #PCP3")

    def tool_help(self, key: str) -> str:
        return {
            "select": "Select the nearest point. Hold Shift to add or toggle points.",
            "pencil": "Place one precise point on the active edit plane.",
            "brush": "Paint a dense disc of points on the active projection plane.",
            "eraser": "Remove points inside the 3D brush radius.",
            "recolor": "Replace point color and alpha inside the brush radius.",
            "picker": "Sample color, radius, alpha, and semantic flag from a point.",
            "line": "Click a start and end position to generate a point spline.",
            "pan": "Drag the 2D canvas. Middle-drag always pans.",
        }.get(key, "")

    def confirm_discard(self) -> bool:
        if not self.document.dirty:
            return True
        response = messagebox.askyesnocancel("Unsaved project", "Save changes before continuing?")
        if response is None:
            return False
        if response:
            return self.save()
        return True

    def python_executable(self) -> str:
        configured = os.environ.get("SC_PYTHON")
        if configured and Path(configured).is_file():
            return configured
        xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        standalone = xdg_data / "signalcloud-engine" / "envs" / "tools-py3" / "bin" / "python"
        development = self.root_path.parent.parent / ".signalcloud_envs" / "tools-py3" / "bin" / "python"
        for candidate in (standalone, development):
            if candidate.is_file():
                return str(candidate)
        return sys.executable

    def show_scope(self) -> None:
        messagebox.showinfo(
            "Point Cloud Paint++ branch1 scope",
            "This branch is a functional authoring foundation: layered 2D orthographic painting, native 3D preview, shapes, semantic data, PLY interchange, creator certificates, and forgiving SignalCloud export.\n\nDirect 3D viewport brushing, skeletal timelines, liquid simulation, encounter graphs, GPU octrees, and plugins remain staged future work. Existing files retain unknown fields for those future systems.",
        )

    def show_format_info(self) -> None:
        messagebox.showinfo(
            "PCP3 formats",
            ".pcp3 — editable project metadata\n.pcp3cloud — 64-byte extensible binary point records\n.pcpcert.json — creator certificate and append-only proof chain\n.udata — forgiving SignalCloud database sidecar\n.ply — Blender/CloudCompare/MeshLab interchange",
        )

    def on_close(self) -> None:
        if not self.confirm_discard():
            return
        if self.preview_process is not None and self.preview_process.poll() is None:
            # The native preview is intentionally independent; do not kill it.
            pass
        self.destroy()


TOOLS_DICT = dict(TOOLS)


def main(root_path: Path) -> int:
    editor = PCP3Editor(root_path)
    editor.mainloop()
    return 0
