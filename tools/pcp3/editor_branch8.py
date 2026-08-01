from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from tools.pcp3 import editor_branch7r1 as branch7r1
from tools.pcp3.advanced_authoring import ensure_authoring
from tools.pcp3.brushes import BrushPreset, save_brush
from tools.pcp3.editor_branch4 import AdvancedBrushEditorWindow
from tools.pcp3.entity_runtime import (
    ENTITY_KINDS,
    MOVEMENT_PROFILES,
    STATE_NAMES,
    assign_bone_channels,
    compile_entity_runtime,
    ensure_entity_runtime,
    entity_runtime_udata,
    validate_entity_runtime,
    write_entity_runtime_files,
)
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.model import PCPPoint


class EntityBrushEditorWindow(AdvancedBrushEditorWindow):
    """Branch 8 adds explicit bone-channel selection to the layered 3D Brush Editor."""

    def __init__(self, master: tk.Misc, root_path: Path, initial: BrushPreset, on_apply: Any,
                 current_environment: str, bone_channels: list[tuple[str, int]]) -> None:
        self.bone_channels = list(bone_channels)
        super().__init__(master, root_path, initial, on_apply, current_environment)
        initial_name = str(self.brush.metadata.get("bone_name", ""))
        choices = [f"{name} · channel {channel}" for name, channel in self.bone_channels]
        if not choices:
            choices = ["root · channel 0"]
        if not initial_name or initial_name not in {name for name, _ in self.bone_channels}:
            initial_name = self.bone_channels[0][0] if self.bone_channels else "root"
        self.bone_target = tk.StringVar(value=initial_name)
        self.bone_target_display = tk.StringVar(value=next((item for item in choices if item.startswith(initial_name + " ·")), choices[0]))
        frame = ttk.LabelFrame(self, text="Branch 8 bone-weight target", padding=5)
        frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        ttk.Label(frame, text="Bone:").pack(side="left")
        combo = ttk.Combobox(frame, textvariable=self.bone_target_display, values=choices, state="readonly", width=28)
        combo.pack(side="left", fill="x", expand=True, padx=4)
        combo.bind("<<ComboboxSelected>>", self._bone_selected)
        ttk.Label(frame, text="Bone Weight stamps encode one bounded channel per point.", wraplength=340).pack(side="left", padx=4)

    def _bone_selected(self, _event: tk.Event | None = None) -> None:
        value = self.bone_target_display.get().split(" · channel ", 1)[0]
        self.bone_target.set(value)

    def _sync_mode_metadata(self) -> None:
        super()._sync_mode_metadata()
        name = self.bone_target.get().strip() if hasattr(self, "bone_target") else str(self.brush.metadata.get("bone_name", "root"))
        channel = next((channel for bone_name, channel in self.bone_channels if bone_name == name), 0)
        self.brush.metadata["bone_name"] = name or "root"
        self.brush.metadata["bone_channel"] = int(channel)
        self.brush.metadata["editor"] = "PCP3 Branch 8 Entity Behavior & Animation Runtime"


class PCP3Editor(branch7r1.PCP3Editor):
    def __init__(self, root_path: Path) -> None:
        self.entity_panel: ttk.Frame | None = None
        self.entity_vars: dict[str, tk.Variable] = {}
        self.entity_state_vars: dict[str, tk.StringVar] = {}
        self.entity_status: tk.StringVar | None = None
        self.entity_findings: tk.Text | None = None
        self.entity_bone_tree: ttk.Treeview | None = None
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch8"
        ensure_entity_runtime(self.document)
        self._ensure_entity_brushes()
        self.refresh_entity_panel()
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 8 Entity Behavior & Animation Runtime")
        self.update_status("Branch 8 active · bone-weight deformation · entity state clips · guarded movement and anchor evidence")

    def _build_toolbar(self) -> None:
        super()._build_toolbar()
        shell = getattr(self, "command_toolbar", None)
        if shell is None:
            return
        row = None
        for child in shell.winfo_children():
            try:
                if int(child.grid_info().get("row", -1)) == 0:
                    row = child
                    break
            except (tk.TclError, TypeError, ValueError):
                continue
        if row is not None:
            ttk.Button(row, text="Entity Runtime", command=self.show_entity_runtime).pack(side="left", padx=2)

    def _insert_authoring_tab(self) -> None:
        super()._insert_authoring_tab()
        self._build_entity_panel(self.authoring_notebook)

    def _build_entity_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=5)
        notebook.add(panel, text="Entity")
        self.entity_panel = panel
        settings = ensure_entity_runtime(self.document)
        self.entity_status = tk.StringVar(master=self, value="Entity Runtime ready")
        types: dict[str, tuple[type[tk.Variable], Any]] = {
            "enabled": (tk.BooleanVar, settings["enabled"]),
            "game_enabled": (tk.BooleanVar, settings["game_enabled"]),
            "stress_enabled": (tk.BooleanVar, settings["stress_enabled"]),
            "entity_kind": (tk.StringVar, settings["entity_kind"]),
            "movement_profile": (tk.StringVar, settings["movement_profile"]),
            "movement_speed": (tk.DoubleVar, settings["movement_speed"]),
            "movement_radius": (tk.DoubleVar, settings["movement_radius"]),
            "hover_height": (tk.DoubleVar, settings["hover_height"]),
            "hover_period": (tk.DoubleVar, settings["hover_period"]),
            "detection_radius": (tk.DoubleVar, settings["detection_radius"]),
            "attack_radius": (tk.DoubleVar, settings["attack_radius"]),
            "attack_cooldown": (tk.DoubleVar, settings["attack_cooldown"]),
            "transition_seconds": (tk.DoubleVar, settings["transition_seconds"]),
            "bone_deformation": (tk.BooleanVar, settings["bone_deformation"]),
            "show_rig_debug": (tk.BooleanVar, settings["show_rig_debug"]),
            "show_anchor_debug": (tk.BooleanVar, settings["show_anchor_debug"]),
            "show_state_debug": (tk.BooleanVar, settings["show_state_debug"]),
            "max_deformed_points": (tk.IntVar, settings["max_deformed_points"]),
            "attack_anchor": (tk.StringVar, settings["attack_anchor"]),
            "effect_anchor": (tk.StringVar, settings["effect_anchor"]),
        }
        self.entity_vars = {key: cls(master=self, value=value) for key, (cls, value) in types.items()}
        self.entity_state_vars = {
            state: tk.StringVar(master=self, value=str(settings["state_clips"].get(state, "Default")))
            for state in STATE_NAMES
        }

        targets = ttk.LabelFrame(panel, text="Explicit guarded entity targets", padding=4)
        targets.pack(fill="x")
        ttk.Checkbutton(targets, text="Enable Entity Runtime", variable=self.entity_vars["enabled"], command=self.entity_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(targets, text="Game", variable=self.entity_vars["game_enabled"], command=self.entity_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(targets, text="Stress", variable=self.entity_vars["stress_enabled"], command=self.entity_changed).grid(row=1, column=1, sticky="w")
        ttk.Label(targets, text="Kind").grid(row=2, column=0, sticky="w")
        ttk.Combobox(targets, textvariable=self.entity_vars["entity_kind"], values=ENTITY_KINDS, state="readonly").grid(row=2, column=1, sticky="ew")
        targets.columnconfigure(1, weight=1)

        movement = ttk.LabelFrame(panel, text="Movement and senses", padding=4)
        movement.pack(fill="x", pady=4)
        fields = (
            ("Profile", "movement_profile", MOVEMENT_PROFILES),
            ("Speed", "movement_speed", None),
            ("Travel radius", "movement_radius", None),
            ("Hover height", "hover_height", None),
            ("Hover period", "hover_period", None),
            ("Detection radius", "detection_radius", None),
            ("Attack radius", "attack_radius", None),
            ("Attack cooldown", "attack_cooldown", None),
        )
        for row, (label, key, values) in enumerate(fields):
            ttk.Label(movement, text=label).grid(row=row, column=0, sticky="w")
            if values is not None:
                widget: tk.Widget = ttk.Combobox(movement, textvariable=self.entity_vars[key], values=values, state="readonly")
            else:
                widget = ttk.Spinbox(movement, from_=0.0, to=500.0, increment=0.1, textvariable=self.entity_vars[key], command=self.entity_changed)
            widget.grid(row=row, column=1, sticky="ew", padx=3)
        movement.columnconfigure(1, weight=1)

        clips = ttk.LabelFrame(panel, text="State clips", padding=4)
        clips.pack(fill="x", pady=4)
        for row, state in enumerate(STATE_NAMES):
            ttk.Label(clips, text=state.title()).grid(row=row, column=0, sticky="w")
            combo = ttk.Combobox(clips, textvariable=self.entity_state_vars[state], state="readonly")
            combo.grid(row=row, column=1, sticky="ew", padx=3)
            combo.bind("<<ComboboxSelected>>", lambda _event: self.entity_changed())
            setattr(self, f"entity_{state}_clip_combo", combo)
        clips.columnconfigure(1, weight=1)

        rig = ttk.LabelFrame(panel, text="Bone deformation and anchors", padding=4)
        rig.pack(fill="x", pady=4)
        ttk.Checkbutton(rig, text="Apply per-bone weighted deformation", variable=self.entity_vars["bone_deformation"], command=self.entity_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(rig, text="Rig debug", variable=self.entity_vars["show_rig_debug"], command=self.entity_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(rig, text="Anchor debug", variable=self.entity_vars["show_anchor_debug"], command=self.entity_changed).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(rig, text="State debug", variable=self.entity_vars["show_state_debug"], command=self.entity_changed).grid(row=2, column=0, sticky="w")
        ttk.Label(rig, text="Max deformed points").grid(row=3, column=0, sticky="w")
        ttk.Combobox(rig, textvariable=self.entity_vars["max_deformed_points"], values=(25_000, 50_000, 100_000, 250_000, 500_000), state="readonly").grid(row=3, column=1, sticky="ew")
        ttk.Label(rig, text="Attack anchor").grid(row=4, column=0, sticky="w")
        self.entity_attack_anchor_combo = ttk.Combobox(rig, textvariable=self.entity_vars["attack_anchor"], state="readonly")
        self.entity_attack_anchor_combo.grid(row=4, column=1, sticky="ew")
        ttk.Label(rig, text="Effect anchor").grid(row=5, column=0, sticky="w")
        self.entity_effect_anchor_combo = ttk.Combobox(rig, textvariable=self.entity_vars["effect_anchor"], state="readonly")
        self.entity_effect_anchor_combo.grid(row=5, column=1, sticky="ew")
        rig.columnconfigure(1, weight=1)

        self.entity_bone_tree = ttk.Treeview(panel, columns=("channel", "parent"), show="tree headings", height=5)
        self.entity_bone_tree.heading("#0", text="Bone")
        self.entity_bone_tree.heading("channel", text="Weight channel")
        self.entity_bone_tree.heading("parent", text="Parent")
        self.entity_bone_tree.column("#0", width=110)
        self.entity_bone_tree.column("channel", width=90)
        self.entity_bone_tree.column("parent", width=90)
        self.entity_bone_tree.pack(fill="x")

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="Assign Bone Channels", command=self.assign_entity_channels).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Validate", command=self.validate_entity).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="Compile Dry Run", command=self.compile_entity_dry_run).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Reset Safe Defaults", command=self.reset_entity_defaults).pack(side="left", fill="x", expand=True, padx=(2, 0))
        ttk.Label(panel, textvariable=self.entity_status, wraplength=310, font=("Sans", 9, "bold")).pack(fill="x")
        self.entity_findings = tk.Text(panel, height=8, wrap="word", state="disabled")
        self.entity_findings.pack(fill="both", expand=True, pady=(3, 0))

    def sync_entity_from_ui(self) -> dict[str, Any]:
        settings = ensure_entity_runtime(self.document)
        for key, variable in self.entity_vars.items():
            settings[key] = variable.get()
        settings["state_clips"] = {state: variable.get() for state, variable in self.entity_state_vars.items()}
        return ensure_entity_runtime(self.document)

    def entity_changed(self) -> None:
        self.sync_entity_from_ui()
        self.mark_dirty("Entity Runtime settings")
        self.refresh_entity_panel()

    def assign_entity_channels(self) -> None:
        mapping = assign_bone_channels(self.document)
        self.mark_dirty("Assigned bone weight channels")
        self.refresh_entity_panel()
        self.update_status(f"Assigned {len(mapping)} bounded bone-weight channels")

    def refresh_entity_panel(self) -> None:
        if self.entity_panel is None:
            return
        settings = ensure_entity_runtime(self.document)
        authoring = ensure_authoring(self.document)
        clips = [str(clip.get("name", "Default")) for clip in authoring.get("timelines", []) if isinstance(clip, dict)] or ["Default"]
        for state in STATE_NAMES:
            combo = getattr(self, f"entity_{state}_clip_combo", None)
            if combo is not None:
                combo.configure(values=clips)
            if settings["state_clips"].get(state) not in clips:
                settings["state_clips"][state] = clips[0]
            if self.entity_state_vars[state].get() != settings["state_clips"][state]:
                self.entity_state_vars[state].set(settings["state_clips"][state])
        anchors = [str(anchor.get("name", "")) for anchor in authoring["rig"]["anchors"] if isinstance(anchor, dict)]
        anchor_values = ("", *anchors)
        self.entity_attack_anchor_combo.configure(values=anchor_values)
        self.entity_effect_anchor_combo.configure(values=anchor_values)
        for key, variable in self.entity_vars.items():
            if key in settings and variable.get() != settings[key]:
                variable.set(settings[key])
        mapping = assign_bone_channels(self.document)
        if self.entity_bone_tree is not None:
            self.entity_bone_tree.delete(*self.entity_bone_tree.get_children())
            for bone in authoring["rig"]["bones"]:
                if not isinstance(bone, dict):
                    continue
                name = str(bone.get("name", "bone"))
                self.entity_bone_tree.insert("", "end", text=name, values=(mapping.get(name, 0), bone.get("parent", "")))
        issues = validate_entity_runtime(self.document)
        counts = {name: sum(1 for issue in issues if issue.severity == name) for name in ("error", "warning", "info", "pass")}
        if self.entity_status is not None:
            state = "ENABLED" if settings["enabled"] else "disabled"
            targets = "/".join(name for name, on in (("game", settings["game_enabled"]), ("stress", settings["stress_enabled"])) if on) or "none"
            weighted = sum(1 for point in self.document.points if int(round(point.attribute1)) == 41 or 1000 <= int(round(point.attribute1)) < 1064)
            self.entity_status.set(f"Entity {state} · {settings['entity_kind']} · targets {targets} · {len(mapping)} bones · {weighted} weighted points · {counts['warning']} warnings")
        if self.entity_findings is not None:
            self.entity_findings.configure(state="normal")
            self.entity_findings.delete("1.0", "end")
            for issue in issues:
                self.entity_findings.insert("end", f"{issue.severity.upper()}: {issue.message}\n")
            self.entity_findings.configure(state="disabled")

    def validate_entity(self) -> list[Any]:
        self.sync_entity_from_ui()
        issues = validate_entity_runtime(self.document)
        messagebox.showinfo("Entity Runtime validation", "\n".join(f"{issue.severity.upper()}: {issue.message}" for issue in issues[:24]), parent=self)
        self.refresh_entity_panel()
        return issues

    def compile_entity_dry_run(self) -> None:
        try:
            self.sync_entity_from_ui()
            payload = compile_entity_runtime(self.document)
            folder = self.root_path / "user_data" / "pcp3" / "entity_dry_runs" / slugify(self.document.asset_id)
            folder.mkdir(parents=True, exist_ok=True)
            atomic_write_text(folder / "entity_runtime.pcp3entity.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
            atomic_write_text(folder / "entity_runtime.pcp3entity.udata", entity_runtime_udata(payload))
            self.entity_status.set(f"Dry run compiled · {len(payload['bones'])} bones · {len(payload['bone_keyframes'])} bone keys · {len(payload['anchors'])} anchors")
            messagebox.showinfo("Entity Runtime dry run", f"Compiled guarded entity files under:\n{folder}\n\nNo game or save state was changed.", parent=self)
        except Exception as exc:
            messagebox.showerror("Entity compile failed", str(exc), parent=self)

    def reset_entity_defaults(self) -> None:
        self.document.metadata.pop("entity_runtime", None)
        ensure_entity_runtime(self.document)
        self.refresh_entity_panel()
        self.mark_dirty("Reset Entity Runtime")

    def show_entity_runtime(self) -> None:
        self.right_notebook.select(self.authoring_tab)
        self.authoring_notebook.select(self.entity_panel)
        self.refresh_entity_panel()

    def _ensure_entity_brushes(self) -> None:
        directory = self.root_path / "content" / "pcp3_brushes"
        directory.mkdir(parents=True, exist_ok=True)
        for name, size, value in (("Root Weight Soft", 17, 1.0), ("Limb Weight Soft", 13, 0.8), ("Bone Weight Hard", 9, 1.0)):
            preset = BrushPreset.round_soft(name, size)
            preset.metadata.update({
                "semantic": "bone",
                "environment_types": ["enemy", "boss", "mini_boss", "friendly"],
                "tags": ["rig", "weight", "entity"],
                "authoring_channel": "bone_weight",
                "channel_value": value,
                "stamp_role": "rig",
                "bone_name": "root",
                "bone_channel": 0,
                "editor": "PCP3 Branch 8 Entity Behavior & Animation Runtime",
            })
            path = directory / f"{name.replace(' ', '_')}.3dbrush"
            if not path.exists():
                save_brush(path, preset)

    def open_brush_editor(self) -> None:
        mapping = assign_bone_channels(self.document)
        channels = sorted(mapping.items(), key=lambda item: item[1]) or [("root", 0)]
        if self.brush_editor_window is None or not self.brush_editor_window.winfo_exists():
            self.brush_editor_window = EntityBrushEditorWindow(
                self, self.root_path, self.current_brush, self.apply_3d_brush,
                self.document.environment_type, channels,
            )
        else:
            self.brush_editor_window.current_environment = self.document.environment_type
            self.brush_editor_window.deiconify()
            self.brush_editor_window.lift()
            self.brush_editor_window.focus_force()

    def _apply_brush_channel(self, points: list[PCPPoint]) -> list[PCPPoint]:
        points = super()._apply_brush_channel(points)
        if str(self.current_brush.metadata.get("authoring_channel", "geometry")) == "bone_weight":
            try:
                channel = max(0, min(63, int(self.current_brush.metadata.get("bone_channel", 0))))
            except (TypeError, ValueError):
                channel = 0
            for point in points:
                point.attribute1 = float(1000 + channel)
        return points

    def export_to_database(self) -> None:
        self.sync_entity_from_ui()
        asset_name = slugify(self.document.asset_id)
        self.document.metadata["entity_json_file"] = f"{asset_name}.pcp3entity.json"
        self.document.metadata["entity_udata_file"] = f"{asset_name}.pcp3entity.udata"
        super().export_to_database()
        asset_dir = self.root_path / "content" / "pcp3_assets" / self.document.environment_type / asset_name
        if asset_dir.exists():
            try:
                paths = write_entity_runtime_files(asset_dir, self.document)
                self.update_status("Exported PCP3 asset with guarded Entity Runtime sidecars")
                if ensure_entity_runtime(self.document)["enabled"]:
                    messagebox.showinfo("Entity Runtime exported", f"Guarded entity runtime compiled:\n{paths['json'].name}\n{paths['udata'].name}", parent=self)
            except Exception as exc:
                messagebox.showwarning("Entity Runtime warning", str(exc), parent=self)

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        ensure_entity_runtime(self.document)
        if self.entity_panel is not None:
            self.refresh_entity_panel()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if self.entity_panel is not None:
            self.refresh_entity_panel()

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
        if text is not None:
            text.configure(state="normal")
            text.insert("end", "Branch 8 Entity Behavior & Animation Runtime\n", "heading")
            text.insert("end", "Authoring → Entity compiles four guarded distance states (idle, move, alert, attack), safe movement profiles, per-bone weighted deformation, and attack/effect anchor evidence. Damage, unrestricted AI, save mutation, and script execution remain blocked.\n\n")
            text.insert("end", "Branch 8 3D Brush Editor update\n", "heading")
            text.insert("end", "Bone Weight brushes now select a named rig bone. The selected bone is encoded as a bounded weight channel in point extension attributes while opacity remains the point weight.\n\n")
            text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
