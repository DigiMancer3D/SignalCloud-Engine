from __future__ import annotations

import json
import math
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from tools.pcp3 import editor_branch3r1 as branch3r1
from tools.pcp3.advanced_authoring import (
    AuthoringIssue,
    add_anchor,
    add_bone,
    add_clip,
    add_flow_node,
    add_keyframe,
    add_placement,
    add_theme_slot,
    add_timeline_event,
    add_trigger,
    add_wave,
    authoring_summary,
    capabilities_for,
    ensure_authoring,
    sample_clip,
    validate_authoring,
    write_authoring_report,
)
from tools.pcp3.brushes import BrushPreset, save_brush
from tools.pcp3.editor_branch3 import ModeAwareBrushEditorWindow
from tools.pcp3.environment_profiles import validation_counts, write_validation_report
from tools.pcp3.io import export_asset, slugify
from tools.pcp3.model import Layer, PCPPoint, SEMANTIC_FLAGS


AUTHORING_CHANNELS = (
    "geometry",
    "bone_weight",
    "flow_strength",
    "trigger_mask",
    "light_intensity",
    "density",
)


class AdvancedBrushEditorWindow(ModeAwareBrushEditorWindow):
    """Branch 4 authoring-channel metadata for the existing layered 3D Brush Editor."""

    def __init__(self, master: tk.Misc, root_path: Path, initial: BrushPreset, on_apply: Any, current_environment: str) -> None:
        super().__init__(master, root_path, initial, on_apply, current_environment)
        self.authoring_channel = tk.StringVar(value=str(self.brush.metadata.get("authoring_channel", "geometry")))
        self.channel_value = tk.DoubleVar(value=float(self.brush.metadata.get("channel_value", 1.0)))
        self.stamp_role = tk.StringVar(value=str(self.brush.metadata.get("stamp_role", "paint")))
        self._build_authoring_channel()

    def _build_authoring_channel(self) -> None:
        frame = ttk.LabelFrame(self, text="Advanced authoring channel", padding=5)
        frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Channel:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.authoring_channel, values=AUTHORING_CHANNELS, state="readonly", width=20).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(frame, text="Channel value:").grid(row=1, column=0, sticky="w")
        ttk.Scale(frame, from_=0.0, to=4.0, variable=self.channel_value).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Spinbox(frame, from_=0.0, to=100.0, increment=0.05, textvariable=self.channel_value, width=8).grid(row=1, column=2, padx=3)
        ttk.Label(frame, text="Stamp role:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.stamp_role, values=("paint", "rig", "attack", "trigger", "flow", "theme"), state="readonly").grid(row=2, column=1, sticky="ew", padx=4)

    def _sync_mode_metadata(self) -> None:
        super()._sync_mode_metadata()
        self.brush.metadata["authoring_channel"] = self.authoring_channel.get()
        self.brush.metadata["channel_value"] = float(self.channel_value.get())
        self.brush.metadata["stamp_role"] = self.stamp_role.get()
        self.brush.metadata["editor"] = "PCP3 Branch 4 Advanced Authoring Studio"

    def _load_mode_metadata(self) -> None:
        super()._load_mode_metadata()
        if hasattr(self, "authoring_channel"):
            self.authoring_channel.set(str(self.brush.metadata.get("authoring_channel", "geometry")))
            self.channel_value.set(float(self.brush.metadata.get("channel_value", 1.0)))
            self.stamp_role.set(str(self.brush.metadata.get("stamp_role", "paint")))


class PCP3Editor(branch3r1.PCP3Editor):
    """Branch 4: advanced rig, timeline, gameplay, placement, flow, and theme authoring."""

    def __init__(self, root_path: Path) -> None:
        self.authoring_tab: ttk.Frame | None = None
        self.authoring_status: tk.StringVar | None = None
        self.current_clip_name: tk.StringVar | None = None
        self.scrub_time: tk.DoubleVar | None = None
        self.sample_text: tk.StringVar | None = None
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 4 Advanced Authoring Studio")
        self.document.metadata["editor_branch"] = "ISL_plus_branch4"
        ensure_authoring(self.document)
        self._ensure_advanced_brushes()
        self.refresh_authoring_studio()
        self.update_status("Branch 4 active · rig · timelines · triggers · placements · flow · theme authoring")

    # ---------- toolbar / workspace ----------
    def _build_toolbar(self) -> None:
        super()._build_toolbar()
        shell = getattr(self, "command_toolbar", None)
        if shell is None:
            return
        for child in list(shell.winfo_children()):
            try:
                if int(child.grid_info().get("row", -1)) == 0:
                    child.destroy()
            except (tk.TclError, ValueError, TypeError):
                continue
        row = ttk.Frame(shell)
        row.grid(row=0, column=0, pady=(0, 4))

        def button(text: str, command: Callable[[], Any]) -> None:
            ttk.Button(row, text=text, command=command).pack(side="left", padx=2)

        button("New", self.new_document)
        button("Open", self.open_project)
        button("Save", self.save)
        button("Export Asset", self.export_to_database)
        button("Undo", self.undo)
        button("Redo", self.redo)
        ttk.Label(row, text=" |:| ").pack(side="left", padx=2)
        button("Native Preview", self.launch_native_preview)
        ttk.Label(row, text=" |:| ").pack(side="left", padx=2)
        button("Brush Editor", self.open_brush_editor)
        button("Mode Template", self.prompt_apply_mode_template)
        button("Validate", self.validate_mode_asset)
        button("Authoring Studio", self.show_authoring_studio)
        button("Tools Help", self.show_tools_help)

    def _build_workspace(self) -> None:
        super()._build_workspace()
        self._insert_authoring_tab()

    def _insert_authoring_tab(self) -> None:
        notebook = getattr(self, "right_notebook", None)
        if notebook is None:
            return
        tab = ttk.Frame(notebook, padding=5)
        notebook.insert(3, tab, text="Authoring")
        self.authoring_tab = tab
        self.authoring_status = tk.StringVar(master=self, value="Advanced authoring data pending")
        self.current_clip_name = tk.StringVar(master=self, value="Default")
        self.scrub_time = tk.DoubleVar(master=self, value=0.0)
        self.sample_text = tk.StringVar(master=self, value="Timeline sample pending")
        ttk.Label(tab, textvariable=self.authoring_status, wraplength=310, font=("Sans", 9, "bold")).pack(fill="x", pady=(0, 4))
        inner = ttk.Notebook(tab)
        inner.pack(fill="both", expand=True)
        self.authoring_notebook = inner
        self._build_rig_panel(inner)
        self._build_timeline_panel(inner)
        self._build_gameplay_panel(inner)
        self._build_placement_panel(inner)
        self._build_flow_theme_panel(inner)
        bottom = ttk.Frame(tab)
        bottom.pack(fill="x", pady=(4, 0))
        ttk.Button(bottom, text="Validate authoring", command=self.validate_authoring_data).pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Refresh", command=self.refresh_authoring_studio).pack(side="left", fill="x", expand=True, padx=(3, 0))

    def _entry(self, master: tk.Misc, variable: tk.Variable, row: int, label: str, *, width: int = 10, column: int = 0) -> ttk.Entry:
        ttk.Label(master, text=label).grid(row=row, column=column, sticky="w", padx=2, pady=2)
        entry = ttk.Entry(master, textvariable=variable, width=width)
        entry.grid(row=row, column=column + 1, sticky="ew", padx=2, pady=2)
        return entry

    def _vec_vars(self, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[tk.DoubleVar]:
        return [tk.DoubleVar(value=default[index]) for index in range(3)]

    def _vec_row(self, master: tk.Misc, variables: list[tk.DoubleVar], row: int, label: str) -> None:
        ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=2, pady=2)
        holder = ttk.Frame(master)
        holder.grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        for index, axis in enumerate("XYZ"):
            ttk.Label(holder, text=axis).pack(side="left")
            ttk.Spinbox(holder, from_=-100000.0, to=100000.0, increment=0.1, textvariable=variables[index], width=7).pack(side="left", padx=(1, 3))

    # ---------- rig ----------
    def _build_rig_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4)
        notebook.add(panel, text="Rig")
        self.rig_tree = ttk.Treeview(panel, columns=("parent", "start", "end"), show="tree headings", height=8)
        self.rig_tree.heading("#0", text="Bone")
        self.rig_tree.heading("parent", text="Parent")
        self.rig_tree.heading("start", text="Start")
        self.rig_tree.heading("end", text="End")
        self.rig_tree.column("#0", width=90)
        self.rig_tree.column("parent", width=80)
        self.rig_tree.column("start", width=110)
        self.rig_tree.column("end", width=110)
        self.rig_tree.pack(fill="x")
        form = ttk.LabelFrame(panel, text="Bone / anchor", padding=4)
        form.pack(fill="x", pady=4)
        form.columnconfigure(1, weight=1)
        self.bone_name = tk.StringVar(value="root")
        self.bone_parent = tk.StringVar(value="")
        self.bone_start = self._vec_vars()
        self.bone_end = self._vec_vars((0.0, 1.0, 0.0))
        self._entry(form, self.bone_name, 0, "Name")
        self._entry(form, self.bone_parent, 1, "Parent")
        self._vec_row(form, self.bone_start, 2, "Start")
        self._vec_row(form, self.bone_end, 3, "End")
        row = ttk.Frame(form)
        row.grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Button(row, text="Focus → Start", command=lambda: self._set_vec(self.bone_start, self.current_focus())).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Focus → End", command=lambda: self._set_vec(self.bone_end, self.current_focus())).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Add Bone", command=self.add_bone_ui).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Remove", command=self.remove_bone_ui).pack(side="left", fill="x", expand=True, padx=(2, 0))
        anchor = ttk.Frame(panel)
        anchor.pack(fill="x")
        self.anchor_name = tk.StringVar(value="attack_anchor")
        self.anchor_role = tk.StringVar(value="attack")
        ttk.Entry(anchor, textvariable=self.anchor_name, width=14).pack(side="left", fill="x", expand=True)
        ttk.Combobox(anchor, textvariable=self.anchor_role, values=("attack", "interaction", "camera", "effect", "spawn", "generic"), state="readonly", width=12).pack(side="left", padx=2)
        ttk.Button(anchor, text="Add Anchor at Focus", command=self.add_anchor_ui).pack(side="left")
        ttk.Button(panel, text="Generate / Refresh Bone Guide Points", command=self.generate_bone_guides).pack(fill="x", pady=(4, 0))

    # ---------- timeline ----------
    def _build_timeline_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4)
        notebook.add(panel, text="Timeline")
        header = ttk.Frame(panel)
        header.pack(fill="x")
        assert self.current_clip_name is not None
        self.clip_combo = ttk.Combobox(header, textvariable=self.current_clip_name, state="readonly", width=18)
        self.clip_combo.pack(side="left", fill="x", expand=True)
        self.clip_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_timeline())
        ttk.Button(header, text="+ Clip", command=self.add_clip_ui).pack(side="left", padx=2)
        self.clip_duration = tk.DoubleVar(value=1.0)
        self.clip_fps = tk.IntVar(value=30)
        self.clip_loop = tk.BooleanVar(value=True)
        clip_settings = ttk.Frame(panel)
        clip_settings.pack(fill="x", pady=3)
        ttk.Label(clip_settings, text="Duration").pack(side="left")
        ttk.Spinbox(clip_settings, from_=0.05, to=3600.0, increment=0.05, textvariable=self.clip_duration, width=7).pack(side="left", padx=2)
        ttk.Label(clip_settings, text="FPS").pack(side="left")
        ttk.Spinbox(clip_settings, from_=1, to=240, textvariable=self.clip_fps, width=5).pack(side="left", padx=2)
        ttk.Checkbutton(clip_settings, text="Loop", variable=self.clip_loop).pack(side="left")
        ttk.Button(clip_settings, text="Apply", command=self.apply_clip_settings).pack(side="right")
        self.key_tree = ttk.Treeview(panel, columns=("time", "target", "position", "rotation"), show="headings", height=7)
        for key, label, width in (("time", "Time", 50), ("target", "Target", 80), ("position", "Position", 110), ("rotation", "Rotation", 110)):
            self.key_tree.heading(key, text=label); self.key_tree.column(key, width=width)
        self.key_tree.pack(fill="x")
        form = ttk.LabelFrame(panel, text="Keyframe", padding=3)
        form.pack(fill="x", pady=3); form.columnconfigure(1, weight=1)
        self.key_time = tk.DoubleVar(value=0.0)
        self.key_target = tk.StringVar(value="root")
        self.key_position = self._vec_vars()
        self.key_rotation = self._vec_vars()
        self.key_scale = self._vec_vars((1.0, 1.0, 1.0))
        self._entry(form, self.key_time, 0, "Time")
        self._entry(form, self.key_target, 1, "Target")
        self._vec_row(form, self.key_position, 2, "Position")
        self._vec_row(form, self.key_rotation, 3, "Rotation")
        self._vec_row(form, self.key_scale, 4, "Scale")
        actions = ttk.Frame(form); actions.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="Focus → Position", command=lambda: self._set_vec(self.key_position, self.current_focus())).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Add Key", command=self.add_keyframe_ui).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="Remove", command=self.remove_keyframe_ui).pack(side="left", fill="x", expand=True)
        scrub = ttk.Frame(panel); scrub.pack(fill="x", pady=(4, 0))
        ttk.Label(scrub, text="Scrub").pack(side="left")
        assert self.scrub_time is not None
        self.scrub_scale = ttk.Scale(scrub, from_=0.0, to=1.0, variable=self.scrub_time, command=lambda _value: self.update_timeline_sample())
        self.scrub_scale.pack(side="left", fill="x", expand=True, padx=3)
        assert self.sample_text is not None
        ttk.Label(panel, textvariable=self.sample_text, wraplength=310).pack(fill="x")
        event = ttk.Frame(panel); event.pack(fill="x", pady=(3, 0))
        self.event_type = tk.StringVar(value="attack")
        self.event_action = tk.StringVar(value="claw_arc")
        ttk.Combobox(event, textvariable=self.event_type, values=("attack", "movement", "effect", "sound", "script"), state="readonly", width=10).pack(side="left")
        ttk.Entry(event, textvariable=self.event_action).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(event, text="Add Event @ Scrub", command=self.add_timeline_event_ui).pack(side="left")

    # ---------- gameplay ----------
    def _build_gameplay_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4); notebook.add(panel, text="Gameplay")
        self.trigger_tree = ttk.Treeview(panel, columns=("type", "action", "target", "radius"), show="headings", height=9)
        for key, label, width in (("type", "Type", 75), ("action", "Action", 105), ("target", "Target", 85), ("radius", "Radius", 55)):
            self.trigger_tree.heading(key, text=label); self.trigger_tree.column(key, width=width)
        self.trigger_tree.pack(fill="x")
        form = ttk.LabelFrame(panel, text="Trigger node", padding=4); form.pack(fill="x", pady=4); form.columnconfigure(1, weight=1)
        self.trigger_type = tk.StringVar(value="proximity")
        self.trigger_action = tk.StringVar(value="reveal")
        self.trigger_target = tk.StringVar(value="")
        self.trigger_radius = tk.DoubleVar(value=2.0)
        self.trigger_delay = tk.DoubleVar(value=0.0)
        self.trigger_cooldown = tk.DoubleVar(value=1.3)
        self.trigger_repeat = tk.BooleanVar(value=False)
        self.trigger_position = self._vec_vars()
        ttk.Label(form, text="Type").grid(row=0, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.trigger_type, values=("proximity", "scanner", "threshold", "timer", "interaction", "damage", "wave"), state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Label(form, text="Action").grid(row=1, column=0, sticky="w")
        ttk.Combobox(
            form,
            textvariable=self.trigger_action,
            values=("reveal", "show", "hide", "alert", "spawn_proxy", "set_theme", "pulse_light", "none"),
            state="normal",
        ).grid(row=1, column=1, sticky="ew")
        self._entry(form, self.trigger_target, 2, "Target")
        self._vec_row(form, self.trigger_position, 3, "Position")
        self._entry(form, self.trigger_radius, 4, "Radius")
        self._entry(form, self.trigger_delay, 5, "Delay")
        self._entry(form, self.trigger_cooldown, 6, "Cooldown")
        ttk.Checkbutton(form, text="Repeat", variable=self.trigger_repeat).grid(row=7, column=0, sticky="w")
        row = ttk.Frame(form); row.grid(row=8, column=0, columnspan=2, sticky="ew")
        ttk.Button(row, text="Focus → Position", command=lambda: self._set_vec(self.trigger_position, self.current_focus())).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Add Trigger", command=self.add_trigger_ui).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Remove", command=self.remove_trigger_ui).pack(side="left", fill="x", expand=True)

    # ---------- placement / raid ----------
    def _build_placement_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4); notebook.add(panel, text="Placement")
        self.placement_tree = ttk.Treeview(panel, columns=("asset", "kind", "position", "scale"), show="headings", height=8)
        for key, label, width in (("asset", "Asset", 110), ("kind", "Kind", 70), ("position", "Position", 110), ("scale", "Scale", 50)):
            self.placement_tree.heading(key, text=label); self.placement_tree.column(key, width=width)
        self.placement_tree.pack(fill="x")
        form = ttk.LabelFrame(panel, text="Object / entity placement", padding=4); form.pack(fill="x", pady=4); form.columnconfigure(1, weight=1)
        self.place_asset = tk.StringVar(value="unassigned_asset")
        self.place_kind = tk.StringVar(value="object")
        self.place_position = self._vec_vars()
        self.place_rotation = self._vec_vars()
        self.place_scale = tk.DoubleVar(value=1.0)
        self.place_group = tk.StringVar(value="")
        self._entry(form, self.place_asset, 0, "Asset ID")
        ttk.Label(form, text="Kind").grid(row=1, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.place_kind, values=("object", "enemy", "boss", "mini_boss", "friendly", "kiosk", "pickup", "light"), state="readonly").grid(row=1, column=1, sticky="ew")
        self._vec_row(form, self.place_position, 2, "Position")
        self._vec_row(form, self.place_rotation, 3, "Rotation")
        self._entry(form, self.place_scale, 4, "Scale")
        self._entry(form, self.place_group, 5, "Group")
        row = ttk.Frame(form); row.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Button(row, text="Focus → Position", command=lambda: self._set_vec(self.place_position, self.current_focus())).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Add", command=self.add_placement_ui).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Remove", command=self.remove_placement_ui).pack(side="left", fill="x", expand=True)
        wave = ttk.LabelFrame(panel, text="Raid wave", padding=4); wave.pack(fill="x")
        self.wave_index = tk.IntVar(value=1); self.wave_assets = tk.StringVar(value=""); self.wave_count = tk.IntVar(value=1); self.wave_delay = tk.DoubleVar(value=0.0)
        for label, variable, width in (("Wave", self.wave_index, 4), ("Assets", self.wave_assets, 16), ("Count", self.wave_count, 4), ("Delay", self.wave_delay, 5)):
            ttk.Label(wave, text=label).pack(side="left"); ttk.Entry(wave, textvariable=variable, width=width).pack(side="left", padx=2)
        ttk.Button(wave, text="Add Wave", command=self.add_wave_ui).pack(side="right")

    # ---------- flow / theme ----------
    def _build_flow_theme_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4); notebook.add(panel, text="Flow/Theme")
        sub = ttk.Notebook(panel); sub.pack(fill="both", expand=True)
        flow = ttk.Frame(sub, padding=4); sub.add(flow, text="Flow")
        self.flow_tree = ttk.Treeview(flow, columns=("position", "direction", "strength", "viscosity"), show="headings", height=8)
        for key, label, width in (("position", "Position", 100), ("direction", "Direction", 100), ("strength", "Power", 45), ("viscosity", "Visc.", 45)):
            self.flow_tree.heading(key, text=label); self.flow_tree.column(key, width=width)
        self.flow_tree.pack(fill="x")
        form = ttk.Frame(flow); form.pack(fill="x", pady=3); form.columnconfigure(1, weight=1)
        self.flow_position = self._vec_vars(); self.flow_direction = self._vec_vars((1.0, 0.0, 0.0)); self.flow_strength = tk.DoubleVar(value=1.0); self.flow_viscosity = tk.DoubleVar(value=1.0)
        self._vec_row(form, self.flow_position, 0, "Position"); self._vec_row(form, self.flow_direction, 1, "Direction")
        self._entry(form, self.flow_strength, 2, "Strength"); self._entry(form, self.flow_viscosity, 3, "Viscosity")
        row = ttk.Frame(form); row.grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Button(row, text="Focus → Position", command=lambda: self._set_vec(self.flow_position, self.current_focus())).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Add Flow", command=self.add_flow_ui).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Remove", command=self.remove_flow_ui).pack(side="left", fill="x", expand=True)
        theme = ttk.Frame(sub, padding=4); sub.add(theme, text="Theme")
        self.theme_tree = ttk.Treeview(theme, columns=("semantic", "color", "brush", "preset"), show="headings", height=9)
        for key, label, width in (("semantic", "Semantic", 80), ("color", "Color", 65), ("brush", "Brush", 90), ("preset", "Preset", 90)):
            self.theme_tree.heading(key, text=label); self.theme_tree.column(key, width=width)
        self.theme_tree.pack(fill="x")
        tform = ttk.Frame(theme); tform.pack(fill="x", pady=4); tform.columnconfigure(1, weight=1)
        self.theme_semantic = tk.StringVar(value="wall"); self.theme_color = tk.StringVar(value="#D9CC94"); self.theme_brush = tk.StringVar(value="Round Soft"); self.theme_preset = tk.StringVar(value="plaster_wall")
        ttk.Label(tform, text="Semantic").grid(row=0, column=0, sticky="w"); ttk.Combobox(tform, textvariable=self.theme_semantic, values=tuple(SEMANTIC_FLAGS), state="readonly").grid(row=0, column=1, sticky="ew")
        self._entry(tform, self.theme_color, 1, "Color"); self._entry(tform, self.theme_brush, 2, "Brush"); self._entry(tform, self.theme_preset, 3, "Preset")
        row = ttk.Frame(tform); row.grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Button(row, text="Use current color", command=lambda: self.theme_color.set(self.color_hex.get().upper())).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Add / Update", command=self.add_theme_ui).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Remove", command=self.remove_theme_ui).pack(side="left", fill="x", expand=True)

    # ---------- helpers ----------
    def authoring(self) -> dict[str, Any]:
        return ensure_authoring(self.document)

    def current_focus(self) -> tuple[float, float, float]:
        try:
            pane = self.pane_for_canvas(self.active_canvas)
            return self.screen_to_world(pane.width / 2.0, pane.height / 2.0, pane)
        except Exception:
            lower, upper = self.document.bounds()
            return tuple((lower[index] + upper[index]) * 0.5 for index in range(3))  # type: ignore[return-value]

    def _set_vec(self, variables: list[tk.DoubleVar], values: Any) -> None:
        for index in range(3):
            variables[index].set(float(values[index]))

    def _get_vec(self, variables: list[tk.DoubleVar]) -> list[float]:
        return [float(variable.get()) for variable in variables]

    def _format_vec(self, values: Any) -> str:
        try:
            return ",".join(f"{float(values[index]):.2f}" for index in range(3))
        except Exception:
            return "0,0,0"

    def _mutate(self, label: str, function: Callable[[], Any]) -> Any:
        self.push_history(label)
        result = function()
        self.document.metadata["advanced_authoring"] = self.authoring()
        self.document.dirty = True
        self.finish_edit(label)
        self.refresh_authoring_studio()
        return result

    def show_authoring_studio(self) -> None:
        if self.authoring_tab is not None:
            self.right_notebook.select(self.authoring_tab)
        self.refresh_authoring_studio()

    # ---------- mutation callbacks ----------
    def add_bone_ui(self) -> None:
        try:
            self._mutate("Add bone", lambda: add_bone(self.authoring(), self.bone_name.get(), self.bone_parent.get(), self._get_vec(self.bone_start), self._get_vec(self.bone_end)))
        except ValueError as exc:
            messagebox.showerror("Bone not added", str(exc), parent=self)

    def remove_bone_ui(self) -> None:
        selection = self.rig_tree.selection()
        if not selection: return
        bone_id = selection[0]
        self._mutate("Remove bone", lambda: self.authoring()["rig"].__setitem__("bones", [bone for bone in self.authoring()["rig"]["bones"] if str(bone.get("id")) != bone_id]))

    def add_anchor_ui(self) -> None:
        self._mutate("Add anchor", lambda: add_anchor(self.authoring(), self.anchor_name.get(), self.anchor_role.get(), self.current_focus()))

    def add_clip_ui(self) -> None:
        name = simpledialog.askstring("New clip", "Clip name:", parent=self)
        if not name: return
        clip = self._mutate("Add animation clip", lambda: add_clip(self.authoring(), name, self.clip_duration.get(), self.clip_fps.get(), self.clip_loop.get()))
        assert self.current_clip_name is not None
        self.current_clip_name.set(clip["name"])
        self.refresh_timeline()

    def current_clip(self) -> dict[str, Any]:
        clips = self.authoring()["timelines"]
        assert self.current_clip_name is not None
        for clip in clips:
            if isinstance(clip, dict) and str(clip.get("name")) == self.current_clip_name.get():
                return clip
        return clips[0]

    def apply_clip_settings(self) -> None:
        def update() -> None:
            clip = self.current_clip(); clip["duration"] = max(0.05, float(self.clip_duration.get())); clip["fps"] = max(1, min(240, int(self.clip_fps.get()))); clip["loop"] = bool(self.clip_loop.get())
        self._mutate("Update clip settings", update)

    def add_keyframe_ui(self) -> None:
        self._mutate("Add timeline keyframe", lambda: add_keyframe(self.current_clip(), self.key_time.get(), self.key_target.get(), self._get_vec(self.key_position), self._get_vec(self.key_rotation), self._get_vec(self.key_scale)))

    def remove_keyframe_ui(self) -> None:
        selection = self.key_tree.selection()
        if not selection: return
        key_id = selection[0]
        self._mutate("Remove timeline keyframe", lambda: self.current_clip().__setitem__("keyframes", [key for key in self.current_clip().get("keyframes", []) if str(key.get("id")) != key_id]))

    def add_timeline_event_ui(self) -> None:
        self._mutate("Add timeline event", lambda: add_timeline_event(self.current_clip(), (self.scrub_time.get() if self.scrub_time is not None else 0.0), self.event_type.get(), self.event_action.get()))

    def add_trigger_ui(self) -> None:
        self._mutate(
            "Add gameplay trigger",
            lambda: add_trigger(
                self.authoring(),
                self.trigger_type.get(),
                self._get_vec(self.trigger_position),
                self.trigger_radius.get(),
                self.trigger_action.get(),
                self.trigger_target.get(),
                self.trigger_delay.get(),
                self.trigger_repeat.get(),
                self.trigger_cooldown.get(),
            ),
        )

    def remove_trigger_ui(self) -> None:
        selection = self.trigger_tree.selection()
        if not selection: return
        record_id = selection[0]
        self._mutate("Remove gameplay trigger", lambda: self.authoring().__setitem__("triggers", [record for record in self.authoring()["triggers"] if str(record.get("id")) != record_id]))

    def add_placement_ui(self) -> None:
        self._mutate("Add asset placement", lambda: add_placement(self.authoring(), self.place_asset.get(), self.place_kind.get(), self._get_vec(self.place_position), self._get_vec(self.place_rotation), self.place_scale.get(), self.place_group.get()))

    def remove_placement_ui(self) -> None:
        selection = self.placement_tree.selection()
        if not selection: return
        record_id = selection[0]
        self._mutate("Remove asset placement", lambda: self.authoring().__setitem__("placements", [record for record in self.authoring()["placements"] if str(record.get("id")) != record_id]))

    def add_wave_ui(self) -> None:
        assets = [value.strip() for value in self.wave_assets.get().split(",")]
        self._mutate("Add raid wave", lambda: add_wave(self.authoring(), self.wave_index.get(), assets, self.wave_count.get(), self.wave_delay.get()))

    def add_flow_ui(self) -> None:
        self._mutate("Add flow node", lambda: add_flow_node(self.authoring(), self._get_vec(self.flow_position), self._get_vec(self.flow_direction), self.flow_strength.get(), self.flow_viscosity.get()))

    def remove_flow_ui(self) -> None:
        selection = self.flow_tree.selection()
        if not selection: return
        record_id = selection[0]
        self._mutate("Remove flow node", lambda: self.authoring()["flow"].__setitem__("nodes", [record for record in self.authoring()["flow"]["nodes"] if str(record.get("id")) != record_id]))

    def add_theme_ui(self) -> None:
        self._mutate("Add theme slot", lambda: add_theme_slot(self.authoring(), self.theme_semantic.get(), self.theme_color.get(), self.theme_brush.get(), self.theme_preset.get()))

    def remove_theme_ui(self) -> None:
        selection = self.theme_tree.selection()
        if not selection: return
        record_id = selection[0]
        self._mutate("Remove theme slot", lambda: self.authoring()["theme"].__setitem__("slots", [record for record in self.authoring()["theme"]["slots"] if str(record.get("id")) != record_id]))

    # ---------- rig guide geometry ----------
    def _find_or_create_layer(self, name: str, semantic: str, group: str) -> Layer:
        for layer in self.document.layers:
            if layer.name == name:
                return layer
        layer = self.document.add_layer(name, semantic); layer.group = group; return layer

    def generate_bone_guides(self) -> None:
        authoring = self.authoring(); bones = [item for item in authoring["rig"]["bones"] if isinstance(item, dict)]
        if not bones:
            messagebox.showinfo("Bone guides", "Add at least one bone first.", parent=self); return
        def generate() -> int:
            layer = self._find_or_create_layer("Bone Guides", "bone", "Rig")
            self.document.points = [point for point in self.document.points if not (point.layer_id == layer.id and point.attribute1 == 4404.0)]
            count = 0; spacing = max(0.05, self.brush_spacing.get())
            for bone_index, bone in enumerate(bones, start=1):
                start = [float(value) for value in bone.get("start", [0,0,0])]; end = [float(value) for value in bone.get("end", [0,1,0])]
                distance = math.dist(start, end); steps = max(1, min(4096, int(math.ceil(distance / spacing))))
                for step in range(steps + 1):
                    amount = step / steps
                    point = PCPPoint(
                        start[0] + (end[0] - start[0]) * amount,
                        start[1] + (end[1] - start[1]) * amount,
                        start[2] + (end[2] - start[2]) * amount,
                        self.point_radius.get(), 0.25, 0.8, 1.0, 1.0,
                        0.0, 1.0, 0.0, 1.0, layer.id, SEMANTIC_FLAGS["bone"], float(bone_index), 4404.0,
                    )
                    self.document.points.append(point); count += 1
            self.document.active_layer_id = layer.id
            return count
        count = self._mutate("Generate bone guide points", generate)
        self.update_status(f"Generated {count:,} bone guide points")

    # ---------- refresh ----------
    def refresh_authoring_studio(self) -> None:
        if not hasattr(self, "rig_tree"): return
        authoring = self.authoring(); caps = capabilities_for(self.document.environment_type); summary = authoring_summary(self.document)
        if self.authoring_status is not None:
            self.authoring_status.set(f"{self.document.environment_type.replace('_', ' ').title()} supports: {', '.join(caps)} · {summary['bones']} bones · {summary['keyframes']} keys · {summary['triggers']} triggers · {summary['placements']} placements")
        self.rig_tree.delete(*self.rig_tree.get_children())
        for bone in authoring["rig"]["bones"]:
            self.rig_tree.insert("", "end", iid=str(bone.get("id")), text=str(bone.get("name")), values=(bone.get("parent", ""), self._format_vec(bone.get("start")), self._format_vec(bone.get("end"))))
        self.refresh_timeline()
        self.trigger_tree.delete(*self.trigger_tree.get_children())
        for record in authoring["triggers"]:
            self.trigger_tree.insert("", "end", iid=str(record.get("id")), values=(record.get("type"), record.get("action"), record.get("target"), f"{float(record.get('radius',0)):.2f}"))
        self.placement_tree.delete(*self.placement_tree.get_children())
        for record in authoring["placements"]:
            self.placement_tree.insert("", "end", iid=str(record.get("id")), values=(record.get("asset_id"), record.get("kind"), self._format_vec(record.get("position")), f"{float(record.get('scale',1)):.2f}"))
        self.flow_tree.delete(*self.flow_tree.get_children())
        for record in authoring["flow"]["nodes"]:
            self.flow_tree.insert("", "end", iid=str(record.get("id")), values=(self._format_vec(record.get("position")), self._format_vec(record.get("direction")), f"{float(record.get('strength',0)):.2f}", f"{float(record.get('viscosity',0)):.2f}"))
        self.theme_tree.delete(*self.theme_tree.get_children())
        for record in authoring["theme"]["slots"]:
            self.theme_tree.insert("", "end", iid=str(record.get("id")), values=(record.get("semantic"), record.get("color"), record.get("brush"), record.get("preset")))

    def refresh_timeline(self) -> None:
        if not hasattr(self, "clip_combo"): return
        clips = self.authoring()["timelines"]; names = [str(clip.get("name", "Clip")) for clip in clips if isinstance(clip, dict)]
        assert self.current_clip_name is not None
        self.clip_combo.configure(values=names)
        if self.current_clip_name.get() not in names: self.current_clip_name.set(names[0])
        clip = self.current_clip(); self.clip_duration.set(float(clip.get("duration",1.0))); self.clip_fps.set(int(clip.get("fps",30))); self.clip_loop.set(bool(clip.get("loop",True)))
        self.scrub_scale.configure(to=max(0.05, self.clip_duration.get()))
        self.key_tree.delete(*self.key_tree.get_children())
        for key in clip.get("keyframes", []):
            self.key_tree.insert("", "end", iid=str(key.get("id")), values=(f"{float(key.get('time',0)):.3f}", key.get("target"), self._format_vec(key.get("position")), self._format_vec(key.get("rotation_degrees"))))
        self.update_timeline_sample()

    def update_timeline_sample(self) -> None:
        if not hasattr(self, "sample_text") or self.sample_text is None or self.scrub_time is None: return
        sample = sample_clip(self.current_clip(), self.scrub_time.get(), self.key_target.get() or "root")
        self.sample_text.set(f"t={self.scrub_time.get():.3f} · pos {self._format_vec(sample['position'])} · rot {self._format_vec(sample['rotation_degrees'])} · scale {self._format_vec(sample['scale'])}")

    def validate_authoring_data(self, *, show_dialog: bool = True) -> list[AuthoringIssue]:
        issues = validate_authoring(self.document)
        counts: dict[str, int] = {}
        for issue in issues: counts[issue.severity] = counts.get(issue.severity, 0) + 1
        if self.authoring_status is not None:
            self.authoring_status.set(f"Authoring validation: {counts.get('error',0)} errors · {counts.get('warning',0)} warnings · {counts.get('info',0)} notes")
        if show_dialog:
            messagebox.showinfo("Advanced authoring validation", "\n".join(f"{issue.severity.upper()}: {issue.message}" for issue in issues[:18]), parent=self)
        return issues

    # ---------- lifecycle ----------
    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document(); ensure_authoring(self.document)
        if hasattr(self, "rig_tree"): self.refresh_authoring_studio()

    def change_environment_type(self) -> None:
        super().change_environment_type(); ensure_authoring(self.document)
        if hasattr(self, "rig_tree"): self.refresh_authoring_studio()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if hasattr(self, "rig_tree"): self.refresh_authoring_studio()

    # ---------- advanced brush ----------
    def _ensure_advanced_brushes(self) -> None:
        directory = self.root_path / "content" / "pcp3_brushes"; directory.mkdir(parents=True, exist_ok=True)
        presets: list[BrushPreset] = []
        bone = BrushPreset.round_soft("Bone Weight Soft", 17); bone.metadata.update({"semantic":"bone","environment_types":["enemy","boss","mini_boss","friendly"],"tags":["rig","weight"],"authoring_channel":"bone_weight","channel_value":1.0,"stamp_role":"rig"}); presets.append(bone)
        flow = BrushPreset.round_soft("Flow Strength Soft", 17); flow.metadata.update({"semantic":"liquid_flow","environment_types":["liquid","room"],"tags":["flow","liquid"],"authoring_channel":"flow_strength","channel_value":1.0,"stamp_role":"flow"}); presets.append(flow)
        trigger = BrushPreset.cross("Trigger Marker", 13); trigger.metadata.update({"semantic":"trigger","environment_types":["room","raid","enemy","boss","friendly","environment_object"],"tags":["trigger","marker"],"authoring_channel":"trigger_mask","channel_value":1.0,"stamp_role":"trigger"}); presets.append(trigger)
        for preset in presets:
            path = directory / f"{preset.name.replace(' ', '_')}.3dbrush"
            if not path.exists(): save_brush(path, preset)

    def open_brush_editor(self) -> None:
        if self.brush_editor_window is None or not self.brush_editor_window.winfo_exists():
            self.brush_editor_window = AdvancedBrushEditorWindow(self, self.root_path, self.current_brush, self.apply_3d_brush, self.document.environment_type)
        else:
            self.brush_editor_window.current_environment = self.document.environment_type
            self.brush_editor_window.deiconify(); self.brush_editor_window.lift(); self.brush_editor_window.focus_force()

    def _apply_brush_channel(self, points: list[PCPPoint]) -> list[PCPPoint]:
        channel = str(self.current_brush.metadata.get("authoring_channel", "geometry")); value = float(self.current_brush.metadata.get("channel_value", 1.0))
        for point in points:
            if channel in {"bone_weight", "flow_strength", "trigger_mask", "light_intensity"}: point.attribute0 = value
            elif channel == "density": point.density *= max(0.0, value)
            point.attribute1 = {"bone_weight": 41.0, "flow_strength": 42.0, "trigger_mask": 43.0, "light_intensity": 44.0, "density": 45.0}.get(channel, point.attribute1)
        return points

    def brush_points(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        return self._apply_brush_channel(super().brush_points(world))

    def brush_points_3d(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        return self._apply_brush_channel(super().brush_points_3d(world))

    # ---------- export ----------
    def export_to_database(self) -> None:
        mode_issues = self.validate_mode_asset(show_dialog=False); authoring_issues = self.validate_authoring_data(show_dialog=False)
        mode_counts = validation_counts(mode_issues)
        authoring_errors = sum(1 for issue in authoring_issues if issue.severity == "error"); authoring_warnings = sum(1 for issue in authoring_issues if issue.severity == "warning")
        if mode_counts.get("error",0) or mode_counts.get("warning",0) or authoring_errors or authoring_warnings:
            if not messagebox.askyesno("Export with findings?", f"Mode: {mode_counts.get('error',0)} errors / {mode_counts.get('warning',0)} warnings\nAuthoring: {authoring_errors} errors / {authoring_warnings} warnings\n\nExport forgiving sidecars anyway?", parent=self): return
        if not self.save(): return
        try:
            self._sync_document_from_ui(); asset_name = slugify(self.document.asset_id); self.document.metadata["authoring_sidecar_file"] = f"{asset_name}.pcp3authoring.json"
            asset_dir = export_asset(self.document, self.root_path, self.project_path, self.editor_name.get())
            validation_path = asset_dir / f"{asset_name}.pcp3validation.json"; write_validation_report(validation_path, self.document, mode_issues)
            authoring_path = asset_dir / f"{asset_name}.pcp3authoring.json"; write_authoring_report(authoring_path, self.document, authoring_issues)
            python = self.python_executable(); subprocess.run([python, str(self.root_path / "tools" / "asset_doctor" / "asset_doctor.py"), str(self.root_path)], check=True, cwd=self.root_path); subprocess.run([python, str(self.root_path / "tools" / "stress_content_catalog.py"), str(self.root_path)], check=True, cwd=self.root_path)
            self.update_status("Exported PCP3 asset with validation and advanced-authoring sidecars")
            messagebox.showinfo("Export complete", f"Asset exported to:\n{asset_dir}\n\nSidecars:\n{validation_path.name}\n{authoring_path.name}", parent=self)
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)

    def show_tools_help(self) -> None:
        before = set(self.winfo_children()); super().show_tools_help(); created = [child for child in self.winfo_children() if child not in before and isinstance(child, tk.Toplevel)]
        if not created: return
        def find_text(widget: tk.Misc) -> tk.Text | None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Text): return child
                found = find_text(child)
                if found is not None: return found
            return None
        text = find_text(created[-1])
        if text is None: return
        text.configure(state="normal")
        text.insert("end", "Advanced Authoring Studio\n", "heading")
        text.insert("end", "The Authoring tab stores rig bones and anchors, animation clips/keyframes/events, gameplay triggers, asset placements, raid waves, liquid flow nodes, and theme slots. Unsupported runtime behavior is preserved in the .pcp3authoring.json sidecar for future +PCE+ support.\n\n")
        text.insert("end", "Branch 4 3D Brush Editor channels\n", "heading")
        text.insert("end", "Brush presets can target geometry, bone weight, flow strength, trigger mask, light intensity, or density. Channel values are stored in PCP3 point extension attributes while remaining compatible with the current renderer.\n\n")
        text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
