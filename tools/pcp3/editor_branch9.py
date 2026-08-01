from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from tools.pcp3 import editor_branch8 as branch8
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.world_assembly import (
    PORTAL_KINDS,
    RESET_POLICIES,
    add_portal,
    add_spawn_point,
    compile_world_assembly,
    discover_exported_assets,
    ensure_world_assembly,
    validate_world_assembly,
    world_assembly_udata,
    write_world_assembly_files,
    write_world_reference_report,
)


class PCP3Editor(branch8.PCP3Editor):
    def __init__(self, root_path: Path) -> None:
        self.world_panel: ttk.Frame | None = None
        self.world_vars: dict[str, tk.Variable] = {}
        self.world_status: tk.StringVar | None = None
        self.world_findings: tk.Text | None = None
        self.world_portal_tree: ttk.Treeview | None = None
        self.world_spawn_tree: ttk.Treeview | None = None
        self.world_reference_tree: ttk.Treeview | None = None
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch9"
        ensure_world_assembly(self.document)
        self.refresh_world_panel()
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 9 World Assembly & Portal/Liquid Runtime")
        self.update_status("Branch 9 active · room bundles · guarded portal handoff · theme inheritance · liquid visual runtime · reference audit")

    def _build_toolbar(self) -> None:
        super()._build_toolbar()
        shell = getattr(self, "command_toolbar", None)
        if shell is None:
            return
        command_row = None
        for child in shell.winfo_children():
            try:
                if int(child.grid_info().get("row", -1)) == 0:
                    command_row = child
                    break
            except (tk.TclError, TypeError, ValueError):
                continue
        if command_row is not None:
            ttk.Button(command_row, text="World Assembly", command=self.show_world_assembly).pack(side="left", padx=2)

    def _insert_authoring_tab(self) -> None:
        super()._insert_authoring_tab()
        self._build_world_panel(self.authoring_notebook)

    def _build_world_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4)
        notebook.add(panel, text="World")
        self.world_panel = panel
        world = ensure_world_assembly(self.document)
        self.world_status = tk.StringVar(master=self, value="World Assembly pending")
        ttk.Label(panel, textvariable=self.world_status, wraplength=310, font=("Sans", 9, "bold")).pack(fill="x")

        self.world_vars = {
            "enabled": tk.BooleanVar(master=self, value=world["enabled"]),
            "game_enabled": tk.BooleanVar(master=self, value=world["game_enabled"]),
            "stress_enabled": tk.BooleanVar(master=self, value=world["stress_enabled"]),
            "world_id": tk.StringVar(master=self, value=world["world_id"]),
            "room_id": tk.StringVar(master=self, value=world["room_id"]),
            "room_name": tk.StringVar(master=self, value=world["room_name"]),
            "host_zone": tk.StringVar(master=self, value=world["host_zone"]),
            "safe_room": tk.BooleanVar(master=self, value=world["safe_room"]),
            "logical_level": tk.IntVar(master=self, value=world["logical_level"]),
            "theme_asset_id": tk.StringVar(master=self, value=world["theme_asset_id"]),
            "apply_theme": tk.BooleanVar(master=self, value=world["apply_theme"]),
            "execute_portals": tk.BooleanVar(master=self, value=world["execute_portals"]),
            "portal_interaction_required": tk.BooleanVar(master=self, value=world["portal_interaction_required"]),
            "portal_cooldown": tk.DoubleVar(master=self, value=world["portal_cooldown"]),
            "show_portal_debug": tk.BooleanVar(master=self, value=world["show_portal_debug"]),
            "show_bounds_debug": tk.BooleanVar(master=self, value=world["show_bounds_debug"]),
            "liquid_runtime": tk.BooleanVar(master=self, value=world["liquid_runtime"]),
            "liquid_type": tk.StringVar(master=self, value=world["liquid_type"]),
            "liquid_color": tk.StringVar(master=self, value=world["liquid_color"]),
            "liquid_opacity": tk.DoubleVar(master=self, value=world["liquid_opacity"]),
            "wave_amplitude": tk.DoubleVar(master=self, value=world["wave_amplitude"]),
            "wave_frequency": tk.DoubleVar(master=self, value=world["wave_frequency"]),
            "flow_scale": tk.DoubleVar(master=self, value=world["flow_scale"]),
            "max_portals": tk.IntVar(master=self, value=world["max_portals"]),
            "max_placements": tk.IntVar(master=self, value=world["max_placements"]),
            "max_liquid_points": tk.IntVar(master=self, value=world["max_liquid_points"]),
            "reset_policy": tk.StringVar(master=self, value=world["reset_policy"]),
        }

        sub = ttk.Notebook(panel)
        sub.pack(fill="both", expand=True, pady=4)
        self._build_world_room_page(sub)
        self._build_world_portal_page(sub)
        self._build_world_liquid_page(sub)
        self._build_world_reference_page(sub)

        actions = ttk.Frame(panel)
        actions.pack(fill="x")
        ttk.Button(actions, text="Enable Safe World Chain", command=self.enable_safe_world_chain).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Validate", command=self.validate_world).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="Compile Dry Run", command=self.compile_world_dry_run).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Reference Audit", command=self.audit_world_references).pack(side="left", fill="x", expand=True, padx=(2, 0))
        self.world_findings = tk.Text(panel, height=7, wrap="word", state="disabled")
        self.world_findings.pack(fill="both", expand=True, pady=(4, 0))

    def _world_entry(self, master: tk.Misc, row: int, label: str, key: str) -> ttk.Entry:
        ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=2, pady=2)
        entry = ttk.Entry(master, textvariable=self.world_vars[key])
        entry.grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        entry.bind("<FocusOut>", lambda _event: self.world_changed())
        return entry

    def _build_world_room_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Room")
        targets = ttk.LabelFrame(page, text="Explicit guarded world targets", padding=4)
        targets.pack(fill="x")
        ttk.Checkbutton(targets, text="Enable World Assembly", variable=self.world_vars["enabled"], command=self.world_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(targets, text="Game", variable=self.world_vars["game_enabled"], command=self.world_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(targets, text="Stress", variable=self.world_vars["stress_enabled"], command=self.world_changed).grid(row=1, column=1, sticky="w")
        targets.columnconfigure(1, weight=1)

        identity = ttk.LabelFrame(page, text="Room identity and host", padding=4)
        identity.pack(fill="x", pady=4)
        identity.columnconfigure(1, weight=1)
        self._world_entry(identity, 0, "World ID", "world_id")
        self._world_entry(identity, 1, "Room ID", "room_id")
        self._world_entry(identity, 2, "Room name", "room_name")
        ttk.Label(identity, text="Host zone").grid(row=3, column=0, sticky="w")
        ttk.Combobox(identity, textvariable=self.world_vars["host_zone"], values=self._known_host_zones(), width=24).grid(row=3, column=1, sticky="ew", padx=2, pady=2)
        ttk.Checkbutton(identity, text="Safe Room", variable=self.world_vars["safe_room"], command=self.world_changed).grid(row=4, column=0, sticky="w")
        ttk.Label(identity, text="Logical level").grid(row=4, column=1, sticky="w")
        ttk.Spinbox(identity, from_=-4096, to=4096, textvariable=self.world_vars["logical_level"], command=self.world_changed, width=8).grid(row=4, column=1, sticky="e")
        ttk.Label(identity, text="Reset policy").grid(row=5, column=0, sticky="w")
        ttk.Combobox(identity, textvariable=self.world_vars["reset_policy"], values=RESET_POLICIES, state="readonly").grid(row=5, column=1, sticky="ew", padx=2, pady=2)

        theme = ttk.LabelFrame(page, text="Theme inheritance", padding=4)
        theme.pack(fill="x", pady=4)
        theme.columnconfigure(1, weight=1)
        ttk.Checkbutton(theme, text="Apply authored/local theme slots", variable=self.world_vars["apply_theme"], command=self.world_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        self._world_entry(theme, 1, "Theme asset ID", "theme_asset_id")
        ttk.Button(theme, text="Use selected exported theme", command=self.pick_theme_asset).grid(row=2, column=0, columnspan=2, sticky="ew", pady=2)

        limits = ttk.LabelFrame(page, text="Bounded assembly limits", padding=4)
        limits.pack(fill="x", pady=4)
        fields = (("Max portals", "max_portals", 1, 32), ("Max placements", "max_placements", 1, 64), ("Max liquid points", "max_liquid_points", 1000, 500000))
        for row, (label, key, low, high) in enumerate(fields):
            ttk.Label(limits, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(limits, from_=low, to=high, increment=1 if high < 1000 else 1000, textvariable=self.world_vars[key], command=self.world_changed).grid(row=row, column=1, sticky="ew", padx=2)
        limits.columnconfigure(1, weight=1)

    def _known_host_zones(self) -> tuple[str, ...]:
        defaults = (
            "Reception Tape", "Service Loop", "Almond Concourse", "Hum Hall", "Corridor Junction",
            "Nested Room Matrix", "Long Signal Hall", "Traversal & Water Lab", "Vertical Flood Shaft",
            "Submerged Service Tunnel", "Open Pressure Cavity", "Submerged Boundary Lab",
            "Scavenger Exchange", "Live-Fire Signal Range", "Fallen Office",
        )
        current = str(self.document.runtime.get("preview_zone", "Reception Tape"))
        return tuple(dict.fromkeys((current, *defaults)))

    def _build_world_portal_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Portals")
        options = ttk.Frame(page)
        options.pack(fill="x")
        ttk.Checkbutton(options, text="Execute guarded portal handoff", variable=self.world_vars["execute_portals"], command=self.world_changed).pack(anchor="w")
        ttk.Checkbutton(options, text="Interaction required by default", variable=self.world_vars["portal_interaction_required"], command=self.world_changed).pack(anchor="w")
        ttk.Checkbutton(options, text="Show portal debug", variable=self.world_vars["show_portal_debug"], command=self.world_changed).pack(anchor="w")
        ttk.Checkbutton(options, text="Show room bounds", variable=self.world_vars["show_bounds_debug"], command=self.world_changed).pack(anchor="w")
        cooldown = ttk.Frame(options); cooldown.pack(fill="x")
        ttk.Label(cooldown, text="Portal cooldown").pack(side="left")
        ttk.Spinbox(cooldown, from_=0.1, to=30.0, increment=0.1, textvariable=self.world_vars["portal_cooldown"], command=self.world_changed, width=8).pack(side="right")

        self.world_portal_tree = ttk.Treeview(page, columns=("kind", "position", "destination", "target", "active"), show="tree headings", height=8)
        self.world_portal_tree.heading("#0", text="Portal ID")
        for key, label, width in (("kind", "Kind", 62), ("position", "Position", 100), ("destination", "Asset", 92), ("target", "Target", 72), ("active", "On", 36)):
            self.world_portal_tree.heading(key, text=label); self.world_portal_tree.column(key, width=width)
        self.world_portal_tree.column("#0", width=90)
        self.world_portal_tree.pack(fill="x", pady=4)
        row = ttk.Frame(page); row.pack(fill="x")
        ttk.Button(row, text="Add at View Focus", command=self.add_world_portal_dialog).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Duplicate", command=self.duplicate_world_portal).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Remove", command=self.remove_world_portal).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Link Pair", command=self.link_world_portal_pair).pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.world_spawn_tree = ttk.Treeview(page, columns=("role", "position", "yaw"), show="tree headings", height=5)
        self.world_spawn_tree.heading("#0", text="Spawn ID")
        self.world_spawn_tree.heading("role", text="Role"); self.world_spawn_tree.heading("position", text="Position"); self.world_spawn_tree.heading("yaw", text="Yaw")
        self.world_spawn_tree.column("#0", width=90); self.world_spawn_tree.column("role", width=75); self.world_spawn_tree.column("position", width=110); self.world_spawn_tree.column("yaw", width=55)
        self.world_spawn_tree.pack(fill="x", pady=(8, 3))
        row = ttk.Frame(page); row.pack(fill="x")
        ttk.Button(row, text="Add Spawn at Focus", command=self.add_world_spawn).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Remove Spawn", command=self.remove_world_spawn).pack(side="left", fill="x", expand=True, padx=(2, 0))

    def _build_world_liquid_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Liquid")
        ttk.Checkbutton(page, text="Enable bounded liquid visual runtime", variable=self.world_vars["liquid_runtime"], command=self.world_changed).pack(anchor="w")
        form = ttk.LabelFrame(page, text="Visual liquid behavior", padding=4)
        form.pack(fill="x", pady=4)
        form.columnconfigure(1, weight=1)
        self._world_entry(form, 0, "Liquid type", "liquid_type")
        self._world_entry(form, 1, "Liquid color", "liquid_color")
        for row, (label, key, low, high, step) in enumerate((
            ("Opacity", "liquid_opacity", 0.0, 1.0, 0.05),
            ("Wave amplitude", "wave_amplitude", 0.0, 5.0, 0.01),
            ("Wave frequency", "wave_frequency", 0.01, 20.0, 0.05),
            ("Flow scale", "flow_scale", 0.0, 100.0, 0.1),
        ), start=2):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(form, from_=low, to=high, increment=step, textvariable=self.world_vars[key], command=self.world_changed).grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        row = ttk.Frame(page); row.pack(fill="x")
        ttk.Button(row, text="Use current color", command=self.use_current_liquid_color).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Open Flow Authoring", command=self.open_flow_authoring).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Count Liquid Semantics", command=self.report_liquid_semantics).pack(side="left", fill="x", expand=True)
        ttk.Label(page, text="Phase 9 applies bounded wave/tint visuals to water semantic points. Physical force, buoyancy, collision-volume generation, and dynamic navigation remain deferred.", wraplength=310).pack(fill="x", pady=5)

    def _build_world_reference_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="References")
        ttk.Label(page, text="Exported PCP3 assets available to placements, themes, and portal links.", wraplength=310).pack(fill="x")
        self.world_reference_tree = ttk.Treeview(page, columns=("kind", "zone", "path"), show="tree headings", height=12)
        self.world_reference_tree.heading("#0", text="Asset ID")
        self.world_reference_tree.heading("kind", text="Kind")
        self.world_reference_tree.heading("zone", text="Host zone")
        self.world_reference_tree.heading("path", text="Database path")
        self.world_reference_tree.column("#0", width=100); self.world_reference_tree.column("kind", width=90); self.world_reference_tree.column("zone", width=105); self.world_reference_tree.column("path", width=180)
        self.world_reference_tree.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(page); row.pack(fill="x")
        ttk.Button(row, text="Refresh Database", command=self.refresh_world_references).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Copy Asset ID", command=self.copy_world_reference_id).pack(side="left", fill="x", expand=True, padx=(2, 0))

    def sync_world_from_ui(self) -> dict[str, Any]:
        world = ensure_world_assembly(self.document)
        for key, variable in self.world_vars.items():
            world[key] = variable.get()
        world = ensure_world_assembly(self.document)
        self.document.runtime["preview_zone"] = world["host_zone"]
        return world

    def world_changed(self) -> None:
        self.sync_world_from_ui()
        self.mark_dirty("World Assembly settings")
        self.refresh_world_panel()

    def show_world_assembly(self) -> None:
        if getattr(self, "right_notebook", None) is not None and getattr(self, "authoring_tab", None) is not None:
            self.right_notebook.select(self.authoring_tab)
        if getattr(self, "authoring_notebook", None) is not None and self.world_panel is not None:
            self.authoring_notebook.select(self.world_panel)
        self.refresh_world_panel()

    def enable_safe_world_chain(self) -> None:
        world = ensure_world_assembly(self.document)
        world["enabled"] = True
        if not (world["game_enabled"] or world["stress_enabled"]):
            world["stress_enabled"] = True
        self.document.runtime["enabled"] = True
        self.document.runtime["preview_zone"] = world["host_zone"]
        self.mark_dirty("Enabled guarded World Assembly chain")
        self.refresh_world_panel()
        self.update_status("World Assembly enabled with explicit targets and host-zone normalization")

    def add_world_portal_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add guarded world portal")
        dialog.transient(self); dialog.grab_set()
        body = ttk.Frame(dialog, padding=8); body.pack(fill="both", expand=True); body.columnconfigure(1, weight=1)
        world = ensure_world_assembly(self.document)
        asset_ids = tuple(sorted(discover_exported_assets(self.root_path)))
        portal_id = tk.StringVar(value=f"portal_{len(world['portals']) + 1}")
        kind = tk.StringVar(value="door")
        destination = tk.StringVar(value="")
        destination_portal = tk.StringVar(value="")
        width = tk.DoubleVar(value=1.2); height = tk.DoubleVar(value=2.2); depth = tk.DoubleVar(value=0.4)
        interaction = tk.BooleanVar(value=bool(world["portal_interaction_required"]))
        one_way = tk.BooleanVar(value=False)
        focus = self.current_focus()
        ttk.Label(body, text="Portal ID").grid(row=0, column=0, sticky="w"); ttk.Entry(body, textvariable=portal_id).grid(row=0, column=1, sticky="ew")
        ttk.Label(body, text="Kind").grid(row=1, column=0, sticky="w"); ttk.Combobox(body, textvariable=kind, values=PORTAL_KINDS, state="readonly").grid(row=1, column=1, sticky="ew")
        ttk.Label(body, text="Destination asset").grid(row=2, column=0, sticky="w"); ttk.Combobox(body, textvariable=destination, values=asset_ids).grid(row=2, column=1, sticky="ew")
        ttk.Label(body, text="Destination portal").grid(row=3, column=0, sticky="w"); ttk.Entry(body, textvariable=destination_portal).grid(row=3, column=1, sticky="ew")
        dims = ttk.Frame(body); dims.grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)
        for label, var in (("W", width), ("H", height), ("D", depth)):
            ttk.Label(dims, text=label).pack(side="left"); ttk.Spinbox(dims, from_=0.05, to=100.0, increment=0.1, textvariable=var, width=7).pack(side="left", padx=(1, 5))
        ttk.Label(body, text=f"Position from active view focus: {focus[0]:.2f}, {focus[1]:.2f}, {focus[2]:.2f}").grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(body, text="Interaction required", variable=interaction).grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(body, text="One way", variable=one_way).grid(row=6, column=1, sticky="w")
        buttons = ttk.Frame(body); buttons.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        def accept() -> None:
            try:
                add_portal(self.document, portal_id=portal_id.get(), kind=kind.get(), position=focus,
                           size=(width.get(), height.get(), depth.get()), destination_asset_id=destination.get(),
                           destination_portal_id=destination_portal.get(), interaction_required=interaction.get(),
                           one_way=one_way.get())
            except Exception as exc:
                messagebox.showerror("Portal", str(exc), parent=dialog); return
            dialog.destroy(); self.mark_dirty("Added world portal"); self.refresh_world_panel()
        ttk.Button(buttons, text="Add Portal", command=accept).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", fill="x", expand=True, padx=(3, 0))

    def duplicate_world_portal(self) -> None:
        if self.world_portal_tree is None or not self.world_portal_tree.selection():
            return
        portal_id = self.world_portal_tree.selection()[0]
        world = ensure_world_assembly(self.document)
        source = next((item for item in world["portals"] if str(item.get("id")) == portal_id), None)
        if source is None:
            return
        try:
            add_portal(self.document, portal_id=f"{portal_id}_copy", kind=str(source.get("kind", "door")),
                       position=source.get("position"), size=source.get("size"),
                       destination_asset_id=str(source.get("destination_asset_id", "")),
                       destination_portal_id=str(source.get("destination_portal_id", "")),
                       arrival_offset=source.get("arrival_offset"),
                       arrival_yaw_degrees=float(source.get("arrival_yaw_degrees", 0.0)),
                       interaction_required=bool(source.get("interaction_required", True)),
                       one_way=bool(source.get("one_way", False)))
        except Exception as exc:
            messagebox.showerror("Duplicate portal", str(exc), parent=self); return
        self.mark_dirty("Duplicated world portal"); self.refresh_world_panel()

    def remove_world_portal(self) -> None:
        if self.world_portal_tree is None or not self.world_portal_tree.selection():
            return
        selected = set(self.world_portal_tree.selection())
        world = ensure_world_assembly(self.document)
        world["portals"] = [item for item in world["portals"] if str(item.get("id", "")) not in selected]
        self.mark_dirty("Removed world portal"); self.refresh_world_panel()

    def link_world_portal_pair(self) -> None:
        if self.world_portal_tree is None or len(self.world_portal_tree.selection()) != 2:
            messagebox.showinfo("Link portal pair", "Select exactly two local portals to link them in both directions.", parent=self); return
        left_id, right_id = self.world_portal_tree.selection()
        world = ensure_world_assembly(self.document)
        by_id = {str(item.get("id", "")): item for item in world["portals"] if isinstance(item, dict)}
        if left_id not in by_id or right_id not in by_id:
            return
        by_id[left_id]["destination_asset_id"] = self.document.asset_id
        by_id[left_id]["destination_portal_id"] = right_id
        by_id[right_id]["destination_asset_id"] = self.document.asset_id
        by_id[right_id]["destination_portal_id"] = left_id
        self.mark_dirty("Linked local portal pair"); self.refresh_world_panel()

    def add_world_spawn(self) -> None:
        world = ensure_world_assembly(self.document)
        try:
            add_spawn_point(self.document, f"spawn_{len(world['spawn_points']) + 1}", "default", self.current_focus(), 0.0)
        except Exception as exc:
            messagebox.showerror("Spawn point", str(exc), parent=self); return
        self.mark_dirty("Added world spawn point"); self.refresh_world_panel()

    def remove_world_spawn(self) -> None:
        if self.world_spawn_tree is None or not self.world_spawn_tree.selection():
            return
        selected = set(self.world_spawn_tree.selection())
        world = ensure_world_assembly(self.document)
        world["spawn_points"] = [item for item in world["spawn_points"] if str(item.get("id", "")) not in selected]
        self.mark_dirty("Removed world spawn point"); self.refresh_world_panel()

    def pick_theme_asset(self) -> None:
        assets = discover_exported_assets(self.root_path)
        themes = [asset_id for asset_id, data in assets.items() if data.get("environment_type") == "environment_theme"]
        if not themes:
            messagebox.showinfo("Theme asset", "No exported Environment Theme assets were found.", parent=self); return
        chooser = tk.Toplevel(self); chooser.title("Select exported theme"); chooser.transient(self); chooser.grab_set()
        value = tk.StringVar(value=themes[0]); ttk.Combobox(chooser, textvariable=value, values=themes, state="readonly", width=36).pack(fill="x", padx=8, pady=8)
        def apply() -> None:
            self.world_vars["theme_asset_id"].set(value.get()); chooser.destroy(); self.world_changed()
        ttk.Button(chooser, text="Use Theme", command=apply).pack(fill="x", padx=8, pady=(0, 8))

    def use_current_liquid_color(self) -> None:
        self.world_vars["liquid_color"].set(self.color_hex.get().upper())
        self.world_changed()

    def open_flow_authoring(self) -> None:
        self.show_authoring_studio()
        try:
            self.authoring_notebook.select(4)
        except tk.TclError:
            pass

    def report_liquid_semantics(self) -> None:
        surface = sum(1 for point in self.document.points if point.flags == 6)
        volume = sum(1 for point in self.document.points if point.flags == 7)
        messagebox.showinfo("Liquid semantics", f"Water Surface points: {surface:,}\nWater Volume points: {volume:,}", parent=self)

    def refresh_world_references(self) -> None:
        if self.world_reference_tree is None:
            return
        assets = discover_exported_assets(self.root_path)
        self.world_reference_tree.delete(*self.world_reference_tree.get_children())
        for asset_id, data in sorted(assets.items()):
            path = Path(data["udata_path"])
            try:
                display_path = str(path.relative_to(self.root_path))
            except ValueError:
                display_path = str(path)
            self.world_reference_tree.insert("", "end", iid=asset_id, text=asset_id,
                                             values=(data.get("environment_type", ""), data.get("preview_zone", ""), display_path))

    def copy_world_reference_id(self) -> None:
        if self.world_reference_tree is None or not self.world_reference_tree.selection():
            return
        value = self.world_reference_tree.selection()[0]
        self.clipboard_clear(); self.clipboard_append(value)
        self.update_status(f"Copied world asset reference: {value}")

    def audit_world_references(self) -> None:
        payload = compile_world_assembly(self.document, self.root_path)
        refs = payload["references"]
        messagebox.showinfo(
            "World reference audit",
            f"Known exported assets: {refs['known_asset_count']}\n"
            f"Referenced: {len(refs['referenced_asset_ids'])}\n"
            f"Resolved: {len(refs['resolved_asset_ids'])}\n"
            f"Missing: {len(refs['missing_asset_ids'])}\n\n"
            + ("Missing IDs:\n" + "\n".join(refs["missing_asset_ids"][:20]) if refs["missing_asset_ids"] else "All current references resolve."),
            parent=self,
        )
        self.refresh_world_panel()

    def validate_world(self) -> list[Any]:
        self.sync_world_from_ui()
        issues = validate_world_assembly(self.document, self.root_path)
        messagebox.showinfo("World Assembly validation", "\n".join(f"{issue.severity.upper()}: {issue.message}" for issue in issues[:28]), parent=self)
        self.refresh_world_panel()
        return issues

    def compile_world_dry_run(self) -> None:
        self.sync_world_from_ui()
        payload = compile_world_assembly(self.document, self.root_path)
        target = self.root_path / "user_data" / "pcp3" / "world_dry_runs" / slugify(self.document.asset_id)
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "world_assembly.pcp3world.json"
        udata_path = target / "world_assembly.pcp3world.udata"
        audit_path = target / "world_reference_audit.json"
        atomic_write_text(json_path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
        atomic_write_text(udata_path, world_assembly_udata(payload))
        write_world_reference_report(audit_path, self.document, self.root_path)
        self.update_status("World Assembly dry run compiled without installing into the database")
        messagebox.showinfo("World Assembly dry run", f"Created:\n{json_path}\n{udata_path}\n{audit_path}", parent=self)

    def refresh_world_panel(self) -> None:
        if self.world_panel is None:
            return
        world = ensure_world_assembly(self.document)
        for key, variable in self.world_vars.items():
            if key in world and variable.get() != world[key]:
                variable.set(world[key])
        if self.world_portal_tree is not None:
            self.world_portal_tree.delete(*self.world_portal_tree.get_children())
            for portal in world["portals"]:
                pos = ",".join(f"{float(value):.1f}" for value in portal.get("position", [0, 0, 0]))
                self.world_portal_tree.insert("", "end", iid=str(portal.get("id", "portal")), text=str(portal.get("id", "portal")),
                                              values=(portal.get("kind", "door"), pos, portal.get("destination_asset_id", ""), portal.get("destination_portal_id", ""), "yes" if portal.get("enabled", True) else "no"))
        if self.world_spawn_tree is not None:
            self.world_spawn_tree.delete(*self.world_spawn_tree.get_children())
            for spawn in world["spawn_points"]:
                pos = ",".join(f"{float(value):.1f}" for value in spawn.get("position", [0, 0, 0]))
                self.world_spawn_tree.insert("", "end", iid=str(spawn.get("id", "spawn")), text=str(spawn.get("id", "spawn")),
                                             values=(spawn.get("role", "default"), pos, f"{float(spawn.get('yaw_degrees', 0.0)):.1f}"))
        self.refresh_world_references()
        issues = validate_world_assembly(self.document, self.root_path)
        counts = {name: sum(1 for issue in issues if issue.severity == name) for name in ("error", "warning", "info", "pass")}
        if self.world_status is not None:
            state = "ENABLED" if world["enabled"] else "disabled"
            targets = "/".join(name for name, on in (("game", world["game_enabled"]), ("stress", world["stress_enabled"])) if on) or "none"
            self.world_status.set(
                f"World {state} · {world['room_id']} · host {world['host_zone']} · targets {targets} · "
                f"{len(world['portals'])} portals · {counts['error']} errors · {counts['warning']} warnings"
            )
        if self.world_findings is not None:
            self.world_findings.configure(state="normal"); self.world_findings.delete("1.0", "end")
            for issue in issues:
                self.world_findings.insert("end", f"{issue.severity.upper()}: {issue.message}\n")
            self.world_findings.configure(state="disabled")

    def export_to_database(self) -> None:
        self.sync_world_from_ui()
        asset_name = slugify(self.document.asset_id)
        self.document.metadata["world_json_file"] = f"{asset_name}.pcp3world.json"
        self.document.metadata["world_udata_file"] = f"{asset_name}.pcp3world.udata"
        self.document.metadata["world_reference_file"] = f"{asset_name}.pcp3world.references.json"
        super().export_to_database()
        asset_dir = self.root_path / "content" / "pcp3_assets" / self.document.environment_type / asset_name
        if not asset_dir.exists():
            return
        try:
            paths = write_world_assembly_files(asset_dir, self.document, self.root_path)
            audit = write_world_reference_report(asset_dir / f"{asset_name}.pcp3world.references.json", self.document, self.root_path)
            self.update_status("Exported PCP3 asset with guarded World Assembly sidecars")
            if ensure_world_assembly(self.document)["enabled"]:
                messagebox.showinfo("World Assembly exported", f"Created:\n{paths['json'].name}\n{paths['udata'].name}\n{audit.name}", parent=self)
        except Exception as exc:
            messagebox.showwarning("World Assembly warning", str(exc), parent=self)

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        ensure_world_assembly(self.document)
        if self.world_panel is not None:
            self.refresh_world_panel()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if self.world_panel is not None:
            self.refresh_world_panel()

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
            text.insert("end", "Branch 9 World Assembly & Portal/Liquid Runtime\n", "heading")
            text.insert("end", "Authoring → World packages a PCP3 room, bounded one-level placements, local or referenced themes, portal links, spawn points, and visual liquid behavior. Game portal handoff is explicit, distance-bounded, cooldown-guarded, and never executes arbitrary code. Collision mesh generation, navigation rebuilding, liquid physics, and deep world nesting remain deferred.\n\n")
            text.insert("end", "3D Brush Editor note\n", "heading")
            text.insert("end", "Branch 9 does not add a new Brush Editor window. Existing semantic, flow-strength, light-intensity, trigger-mask, density, and bone-weight channels feed World Assembly where supported.\n\n")
            text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
