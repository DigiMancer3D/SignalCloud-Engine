from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from tools.pcp3 import editor_branch9 as branch9
from tools.pcp3.advanced_authoring import add_placement, add_wave, ensure_authoring
from tools.pcp3.encounter_runtime import (
    COMPLETION_POLICIES,
    RESET_POLICIES,
    REWARD_POLICIES,
    START_CONDITIONS,
    add_boss_phase,
    compile_encounter_runtime,
    ensure_encounter_runtime,
    simulate_encounter,
    validate_encounter_runtime,
    write_encounter_runtime_files,
)
from tools.pcp3.io import atomic_write_text, slugify


class PCP3Editor(branch9.PCP3Editor):
    def __init__(self, root_path: Path) -> None:
        self.encounter_panel: ttk.Frame | None = None
        self.encounter_vars: dict[str, tk.Variable] = {}
        self.encounter_status: tk.StringVar | None = None
        self.encounter_findings: tk.Text | None = None
        self.encounter_wave_tree: ttk.Treeview | None = None
        self.encounter_phase_tree: ttk.Treeview | None = None
        self.encounter_friendly_tree: ttk.Treeview | None = None
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch10"
        ensure_encounter_runtime(self.document)
        self.refresh_encounter_panel()
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 10 Encounter, Raid, Boss & Friendly Runtime")
        self.update_status("Branch 10 active · bounded waves · boss phases · friendly references · guarded completion and reward telemetry")

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
            ttk.Button(command_row, text="Encounter Runtime", command=self.show_encounter_runtime).pack(side="left", padx=2)

    def _insert_authoring_tab(self) -> None:
        super()._insert_authoring_tab()
        self._build_encounter_panel(self.authoring_notebook)

    def _build_encounter_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4)
        notebook.add(panel, text="Encounter")
        self.encounter_panel = panel
        settings = ensure_encounter_runtime(self.document)
        self.encounter_status = tk.StringVar(master=self, value="Encounter Runtime pending")
        ttk.Label(panel, textvariable=self.encounter_status, wraplength=315, font=("Sans", 9, "bold")).pack(fill="x")

        variable_types: dict[str, tuple[type[tk.Variable], Any]] = {
            "enabled": (tk.BooleanVar, settings["enabled"]),
            "game_enabled": (tk.BooleanVar, settings["game_enabled"]),
            "stress_enabled": (tk.BooleanVar, settings["stress_enabled"]),
            "encounter_id": (tk.StringVar, settings["encounter_id"]),
            "host_zone": (tk.StringVar, settings["host_zone"]),
            "start_condition": (tk.StringVar, settings["start_condition"]),
            "start_radius": (tk.DoubleVar, settings["start_radius"]),
            "start_delay": (tk.DoubleVar, settings["start_delay"]),
            "completion_policy": (tk.StringVar, settings["completion_policy"]),
            "completion_seconds": (tk.DoubleVar, settings["completion_seconds"]),
            "completion_delay": (tk.DoubleVar, settings["completion_delay"]),
            "inter_wave_delay": (tk.DoubleVar, settings["inter_wave_delay"]),
            "entity_lifetime": (tk.DoubleVar, settings["entity_lifetime"]),
            "reset_policy": (tk.StringVar, settings["reset_policy"]),
            "reward_policy": (tk.StringVar, settings["reward_policy"]),
            "reward_proofs": (tk.IntVar, settings["reward_proofs"]),
            "reward_xar": (tk.IntVar, settings["reward_xar"]),
            "reward_scrap": (tk.IntVar, settings["reward_scrap"]),
            "show_debug": (tk.BooleanVar, settings["show_debug"]),
            "console_events": (tk.BooleanVar, settings["console_events"]),
            "max_waves": (tk.IntVar, settings["max_waves"]),
            "max_active_entities": (tk.IntVar, settings["max_active_entities"]),
            "max_total_spawns": (tk.IntVar, settings["max_total_spawns"]),
            "max_friendlies": (tk.IntVar, settings["max_friendlies"]),
            "max_boss_phases": (tk.IntVar, settings["max_boss_phases"]),
        }
        self.encounter_vars = {key: cls(master=self, value=value) for key, (cls, value) in variable_types.items()}

        sub = ttk.Notebook(panel)
        sub.pack(fill="both", expand=True, pady=4)
        self._build_encounter_setup_page(sub)
        self._build_encounter_waves_page(sub)
        self._build_encounter_boss_page(sub)
        self._build_encounter_friendly_page(sub)
        self._build_encounter_reward_page(sub)

        actions = ttk.Frame(panel)
        actions.pack(fill="x")
        ttk.Button(actions, text="Enable Safe Chain", command=self.enable_safe_encounter_chain).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Validate", command=self.validate_encounter).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="Compile Dry Run", command=self.compile_encounter_dry_run).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Simulate", command=self.simulate_encounter_dialog).pack(side="left", fill="x", expand=True, padx=(2, 0))
        self.encounter_findings = tk.Text(panel, height=7, wrap="word", state="disabled")
        self.encounter_findings.pack(fill="both", expand=True, pady=(4, 0))

    def _encounter_entry(self, master: tk.Misc, row: int, label: str, key: str) -> ttk.Entry:
        ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=2, pady=2)
        entry = ttk.Entry(master, textvariable=self.encounter_vars[key])
        entry.grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        entry.bind("<FocusOut>", lambda _event: self.encounter_changed())
        return entry

    def _build_encounter_setup_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Setup")
        targets = ttk.LabelFrame(page, text="Explicit guarded encounter targets", padding=4)
        targets.pack(fill="x")
        ttk.Checkbutton(targets, text="Enable Encounter Runtime", variable=self.encounter_vars["enabled"], command=self.encounter_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(targets, text="Game", variable=self.encounter_vars["game_enabled"], command=self.encounter_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(targets, text="Stress", variable=self.encounter_vars["stress_enabled"], command=self.encounter_changed).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(targets, text="Show debug evidence", variable=self.encounter_vars["show_debug"], command=self.encounter_changed).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(targets, text="Console events", variable=self.encounter_vars["console_events"], command=self.encounter_changed).grid(row=2, column=1, sticky="w")
        targets.columnconfigure(1, weight=1)

        identity = ttk.LabelFrame(page, text="Identity and activation", padding=4)
        identity.pack(fill="x", pady=4)
        identity.columnconfigure(1, weight=1)
        self._encounter_entry(identity, 0, "Encounter ID", "encounter_id")
        self._encounter_entry(identity, 1, "Host zone", "host_zone")
        ttk.Label(identity, text="Start condition").grid(row=2, column=0, sticky="w")
        ttk.Combobox(identity, textvariable=self.encounter_vars["start_condition"], values=START_CONDITIONS, state="readonly").grid(row=2, column=1, sticky="ew", padx=2, pady=2)
        for row, (label, key, low, high, step) in enumerate((
            ("Start radius", "start_radius", 0.1, 500.0, 0.1),
            ("Start delay", "start_delay", 0.0, 600.0, 0.1),
            ("Inter-wave delay", "inter_wave_delay", 0.0, 60.0, 0.1),
            ("Entity lifetime", "entity_lifetime", 0.25, 600.0, 0.25),
        ), start=3):
            ttk.Label(identity, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(identity, from_=low, to=high, increment=step, textvariable=self.encounter_vars[key], command=self.encounter_changed).grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(identity, text="Use current 3D focus as activation point", command=self.use_focus_for_encounter_start).grid(row=7, column=0, columnspan=2, sticky="ew", pady=2)

        limits = ttk.LabelFrame(page, text="Bounded runtime limits", padding=4)
        limits.pack(fill="x")
        for row, (label, key, high) in enumerate((
            ("Max waves", "max_waves", 16),
            ("Max active entities", "max_active_entities", 32),
            ("Max total spawns", "max_total_spawns", 128),
            ("Max friendlies", "max_friendlies", 16),
            ("Max boss phases", "max_boss_phases", 8),
        )):
            ttk.Label(limits, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(limits, from_=0 if "friendly" in key or "phase" in key else 1, to=high, textvariable=self.encounter_vars[key], command=self.encounter_changed).grid(row=row, column=1, sticky="ew", padx=2)
        limits.columnconfigure(1, weight=1)

    def _build_encounter_waves_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Waves")
        ttk.Label(page, text="Waves use Advanced Authoring raid records and resolve exported entity asset IDs.", wraplength=310).pack(fill="x")
        self.encounter_wave_tree = ttk.Treeview(page, columns=("index", "assets", "count", "delay", "life"), show="tree headings", height=11)
        self.encounter_wave_tree.heading("#0", text="Wave ID")
        for key, label, width in (("index", "#", 35), ("assets", "Assets", 130), ("count", "Count", 50), ("delay", "Delay", 50), ("life", "Life", 50)):
            self.encounter_wave_tree.heading(key, text=label); self.encounter_wave_tree.column(key, width=width)
        self.encounter_wave_tree.column("#0", width=80)
        self.encounter_wave_tree.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(page); row.pack(fill="x")
        ttk.Button(row, text="Add Wave…", command=self.add_encounter_wave_dialog).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Remove", command=self.remove_encounter_wave).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Open Placement Authoring", command=self.open_placement_authoring).pack(side="left", fill="x", expand=True)

    def _build_encounter_boss_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Boss")
        ttk.Label(page, text="Boss phases are bounded progress-based visual/telemetry states. Damage and health mutation remain blocked.", wraplength=310).pack(fill="x")
        self.encounter_phase_tree = ttk.Treeview(page, columns=("threshold", "clip", "movement", "theme", "anchor"), show="tree headings", height=11)
        self.encounter_phase_tree.heading("#0", text="Phase")
        for key, label, width in (("threshold", "Progress", 60), ("clip", "Clip", 70), ("movement", "Movement", 85), ("theme", "Theme", 70), ("anchor", "Effect", 65)):
            self.encounter_phase_tree.heading(key, text=label); self.encounter_phase_tree.column(key, width=width)
        self.encounter_phase_tree.column("#0", width=85)
        self.encounter_phase_tree.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(page); row.pack(fill="x")
        ttk.Button(row, text="Add Phase…", command=self.add_boss_phase_dialog).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Remove", command=self.remove_boss_phase).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Open Timeline", command=self.open_timeline_authoring).pack(side="left", fill="x", expand=True)

    def _build_encounter_friendly_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Friendly")
        ttk.Label(page, text="Friendly placements are persistent one-level PCP3 references with no save, economy, or unrestricted AI mutation.", wraplength=310).pack(fill="x")
        self.encounter_friendly_tree = ttk.Treeview(page, columns=("asset", "position", "scale", "group"), show="tree headings", height=11)
        self.encounter_friendly_tree.heading("#0", text="Placement")
        for key, label, width in (("asset", "Asset", 100), ("position", "Position", 105), ("scale", "Scale", 45), ("group", "Group", 75)):
            self.encounter_friendly_tree.heading(key, text=label); self.encounter_friendly_tree.column(key, width=width)
        self.encounter_friendly_tree.column("#0", width=80)
        self.encounter_friendly_tree.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(page); row.pack(fill="x")
        ttk.Button(row, text="Add Friendly at Focus…", command=self.add_friendly_dialog).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Remove", command=self.remove_friendly).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row, text="Open Entity Runtime", command=self.show_entity_runtime).pack(side="left", fill="x", expand=True)

    def _build_encounter_reward_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Completion")
        completion = ttk.LabelFrame(page, text="Completion", padding=4)
        completion.pack(fill="x")
        completion.columnconfigure(1, weight=1)
        ttk.Label(completion, text="Policy").grid(row=0, column=0, sticky="w")
        ttk.Combobox(completion, textvariable=self.encounter_vars["completion_policy"], values=COMPLETION_POLICIES, state="readonly").grid(row=0, column=1, sticky="ew")
        for row, (label, key, low, high) in enumerate((("Timer seconds", "completion_seconds", 0.1, 3600.0), ("Completion delay", "completion_delay", 0.0, 60.0)), start=1):
            ttk.Label(completion, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(completion, from_=low, to=high, increment=0.1, textvariable=self.encounter_vars[key], command=self.encounter_changed).grid(row=row, column=1, sticky="ew")
        ttk.Label(completion, text="Reset policy").grid(row=3, column=0, sticky="w")
        ttk.Combobox(completion, textvariable=self.encounter_vars["reset_policy"], values=RESET_POLICIES, state="readonly").grid(row=3, column=1, sticky="ew")

        reward = ttk.LabelFrame(page, text="Guarded reward/proof hooks", padding=4)
        reward.pack(fill="x", pady=4)
        reward.columnconfigure(1, weight=1)
        ttk.Label(reward, text="Policy").grid(row=0, column=0, sticky="w")
        ttk.Combobox(reward, textvariable=self.encounter_vars["reward_policy"], values=REWARD_POLICIES, state="readonly").grid(row=0, column=1, sticky="ew")
        for row, (label, key, high) in enumerate((("Proofs", "reward_proofs", 999), ("XAR", "reward_xar", 99999), ("Scrap", "reward_scrap", 9999)), start=1):
            ttk.Label(reward, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(reward, from_=0, to=high, textvariable=self.encounter_vars[key], command=self.encounter_changed).grid(row=row, column=1, sticky="ew")
        ttk.Label(page, text="Branch 10 records reward requests as telemetry hooks. It does not change the player save, wallet, inventory, or proof totals.", wraplength=310).pack(fill="x", pady=5)

    def sync_encounter_from_ui(self) -> dict[str, Any]:
        settings = ensure_encounter_runtime(self.document)
        for key, variable in self.encounter_vars.items():
            settings[key] = variable.get()
        return ensure_encounter_runtime(self.document)

    def encounter_changed(self) -> None:
        self.sync_encounter_from_ui()
        self.mark_dirty("Encounter Runtime settings")
        self.refresh_encounter_panel()

    def use_focus_for_encounter_start(self) -> None:
        settings = self.sync_encounter_from_ui()
        focus = getattr(self, "view_focus", [0.0, 0.0, 0.0])
        settings["start_position"] = [float(focus[0]), float(focus[1]), float(focus[2])]
        self.mark_dirty("Encounter activation point")
        self.refresh_encounter_panel()

    def add_encounter_wave_dialog(self) -> None:
        assets = simpledialog.askstring("Add encounter wave", "Comma-separated exported entity asset IDs:", parent=self)
        if assets is None:
            return
        count = simpledialog.askinteger("Wave count", "Number of entities:", initialvalue=1, minvalue=1, maxvalue=128, parent=self)
        if count is None:
            return
        delay = simpledialog.askfloat("Wave delay", "Delay before this wave:", initialvalue=0.0, minvalue=0.0, maxvalue=600.0, parent=self)
        if delay is None:
            return
        authoring = ensure_authoring(self.document)
        index = 1 + max([int(item.get("index", 0)) for item in authoring["raid"]["waves"] if isinstance(item, dict)] or [0])
        add_wave(authoring, index, [slugify(value.strip()) for value in assets.split(",") if value.strip()], count, delay)
        self.mark_dirty("Added encounter wave")
        self.refresh_encounter_panel()

    def remove_encounter_wave(self) -> None:
        if self.encounter_wave_tree is None or not self.encounter_wave_tree.selection():
            return
        wave_id = self.encounter_wave_tree.selection()[0]
        waves = ensure_authoring(self.document)["raid"]["waves"]
        waves[:] = [item for item in waves if str(item.get("id", "")) != wave_id]
        self.mark_dirty("Removed encounter wave")
        self.refresh_encounter_panel()

    def add_boss_phase_dialog(self) -> None:
        name = simpledialog.askstring("Boss phase", "Phase name:", initialvalue="Phase 1", parent=self)
        if name is None:
            return
        threshold = simpledialog.askfloat("Boss phase", "Progress threshold from 0.0 to 1.0:", initialvalue=0.0, minvalue=0.0, maxvalue=1.0, parent=self)
        if threshold is None:
            return
        clip = simpledialog.askstring("Boss phase", "Timeline clip:", initialvalue="Default", parent=self) or "Default"
        add_boss_phase(self.document, name, threshold, clip)
        self.mark_dirty("Added boss phase")
        self.refresh_encounter_panel()

    def remove_boss_phase(self) -> None:
        if self.encounter_phase_tree is None or not self.encounter_phase_tree.selection():
            return
        phase_id = self.encounter_phase_tree.selection()[0]
        phases = ensure_encounter_runtime(self.document)["boss_phases"]
        phases[:] = [item for item in phases if str(item.get("id", "")) != phase_id]
        self.mark_dirty("Removed boss phase")
        self.refresh_encounter_panel()

    def add_friendly_dialog(self) -> None:
        asset_id = simpledialog.askstring("Add friendly", "Exported friendly asset ID:", parent=self)
        if not asset_id:
            return
        authoring = ensure_authoring(self.document)
        focus = getattr(self, "view_focus", [0.0, 0.0, 0.0])
        add_placement(authoring, slugify(asset_id), "friendly", focus, [0.0, 0.0, 0.0], 1.0, "friendlies")
        self.mark_dirty("Added friendly placement")
        self.refresh_encounter_panel()

    def remove_friendly(self) -> None:
        if self.encounter_friendly_tree is None or not self.encounter_friendly_tree.selection():
            return
        placement_id = self.encounter_friendly_tree.selection()[0]
        placements = ensure_authoring(self.document)["placements"]
        placements[:] = [item for item in placements if str(item.get("id", "")) != placement_id]
        self.mark_dirty("Removed friendly placement")
        self.refresh_encounter_panel()

    def open_placement_authoring(self) -> None:
        if getattr(self, "right_notebook", None) is not None and getattr(self, "authoring_tab", None) is not None:
            self.right_notebook.select(self.authoring_tab)
        for index in range(self.authoring_notebook.index("end")):
            if self.authoring_notebook.tab(index, "text") == "Placement":
                self.authoring_notebook.select(index); return

    def open_timeline_authoring(self) -> None:
        if getattr(self, "right_notebook", None) is not None and getattr(self, "authoring_tab", None) is not None:
            self.right_notebook.select(self.authoring_tab)
        for index in range(self.authoring_notebook.index("end")):
            if self.authoring_notebook.tab(index, "text") == "Timeline":
                self.authoring_notebook.select(index); return

    def enable_safe_encounter_chain(self) -> None:
        settings = self.sync_encounter_from_ui()
        settings["enabled"] = True
        if not settings["game_enabled"] and not settings["stress_enabled"]:
            settings["stress_enabled"] = True
        world = ensure_world_assembly(self.document)
        world["enabled"] = True
        world["stress_enabled"] = bool(settings["stress_enabled"])
        world["game_enabled"] = bool(settings["game_enabled"])
        world["host_zone"] = settings["host_zone"]
        self.document.runtime["preview_zone"] = settings["host_zone"]
        self.mark_dirty("Enabled guarded World + Encounter chain")
        self._sync_all_from_document()

    def validate_encounter(self) -> None:
        self.sync_encounter_from_ui()
        issues = validate_encounter_runtime(self.document, self.root_path)
        messagebox.showinfo("Encounter validation", "\n".join(f"{issue.severity.upper()}: {issue.message}" for issue in issues) or "No findings.", parent=self)
        self.refresh_encounter_panel()

    def compile_encounter_dry_run(self) -> None:
        self.sync_encounter_from_ui()
        payload = compile_encounter_runtime(self.document, self.root_path)
        folder = self.root_path / "user_data" / "pcp3" / "encounter_dry_runs" / slugify(self.document.asset_id)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "runtime_encounter.pcp3encounter.json"
        atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        self.update_status(f"Encounter dry run: {path.relative_to(self.root_path)}")
        messagebox.showinfo("Encounter dry run", f"Compiled without installing into the game database:\n{path}", parent=self)

    def simulate_encounter_dialog(self) -> None:
        self.sync_encounter_from_ui()
        payload = compile_encounter_runtime(self.document, self.root_path)
        events = simulate_encounter(payload, 60.0)
        text = "\n".join(f"{event['time']:7.2f}s · {event['kind']} · wave {event.get('wave', '-')}{' · ' + event.get('asset_id', '') if event.get('asset_id') else ''}" for event in events)
        messagebox.showinfo("Encounter simulation", text or "No events fired under the default deterministic scenario.", parent=self)

    def show_encounter_runtime(self) -> None:
        if getattr(self, "right_notebook", None) is not None and getattr(self, "authoring_tab", None) is not None:
            self.right_notebook.select(self.authoring_tab)
        if self.encounter_panel is not None:
            self.authoring_notebook.select(self.encounter_panel)

    def refresh_encounter_panel(self) -> None:
        if self.encounter_panel is None:
            return
        settings = ensure_encounter_runtime(self.document)
        for key, variable in self.encounter_vars.items():
            try:
                variable.set(settings[key])
            except (tk.TclError, KeyError):
                pass
        payload = compile_encounter_runtime(self.document, self.root_path)
        issues = validate_encounter_runtime(self.document, self.root_path)
        if self.encounter_wave_tree is not None:
            self.encounter_wave_tree.delete(*self.encounter_wave_tree.get_children())
            for wave in payload["waves"]:
                self.encounter_wave_tree.insert("", "end", iid=wave["id"], text=wave["id"], values=(wave["index"], ", ".join(wave["asset_ids"]), wave["count"], wave["delay"], wave["active_seconds"]))
        if self.encounter_phase_tree is not None:
            self.encounter_phase_tree.delete(*self.encounter_phase_tree.get_children())
            for phase in payload["boss_phases"]:
                self.encounter_phase_tree.insert("", "end", iid=phase["id"], text=phase["name"], values=(f"{phase['progress_threshold']:.2f}", phase["clip"], phase["movement_profile"], phase["theme_target"], phase["effect_anchor"]))
        if self.encounter_friendly_tree is not None:
            self.encounter_friendly_tree.delete(*self.encounter_friendly_tree.get_children())
            for placement in payload["friendlies"]:
                self.encounter_friendly_tree.insert("", "end", iid=placement["id"], text=placement["id"], values=(placement["asset_id"], ",".join(f"{v:.1f}" for v in placement["position"]), placement["scale"], placement["group"]))
        counts = {level: sum(1 for issue in issues if issue.severity == level) for level in ("error", "warning", "info")}
        targets = "/".join(name for name, active in (("Game", settings["game_enabled"]), ("Stress", settings["stress_enabled"])) if active) or "none"
        if self.encounter_status is not None:
            self.encounter_status.set(f"Encounter {'ENABLED' if settings['enabled'] else 'disabled'} · targets {targets} · {len(payload['waves'])} waves · {sum(w['count'] for w in payload['waves'])} scheduled · {len(payload['friendlies'])} friendlies · {counts['error']} errors")
        if self.encounter_findings is not None:
            self.encounter_findings.configure(state="normal"); self.encounter_findings.delete("1.0", "end")
            for issue in issues:
                self.encounter_findings.insert("end", f"{issue.severity.upper()}: {issue.message}\n")
            self.encounter_findings.configure(state="disabled")

    def export_to_database(self) -> None:
        self.sync_encounter_from_ui()
        asset_name = slugify(self.document.asset_id)
        self.document.metadata["encounter_json_file"] = f"{asset_name}.pcp3encounter.json"
        self.document.metadata["encounter_udata_file"] = f"{asset_name}.pcp3encounter.udata"
        super().export_to_database()
        asset_dir = self.root_path / "content" / "pcp3_assets" / self.document.environment_type / asset_name
        if not asset_dir.exists():
            return
        try:
            paths = write_encounter_runtime_files(asset_dir, self.document, self.root_path)
            self.update_status("Exported PCP3 asset with guarded Encounter Runtime sidecars")
            if ensure_encounter_runtime(self.document)["enabled"]:
                messagebox.showinfo("Encounter Runtime exported", f"Created:\n{paths['json'].name}\n{paths['udata'].name}", parent=self)
        except Exception as exc:
            messagebox.showwarning("Encounter Runtime warning", str(exc), parent=self)

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        ensure_encounter_runtime(self.document)
        if self.encounter_panel is not None:
            self.refresh_encounter_panel()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if self.encounter_panel is not None:
            self.refresh_encounter_panel()

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
            text.insert("end", "\n\nBRANCH 10 — ENCOUNTER RUNTIME\nUse Authoring → Encounter to schedule bounded raid waves, persistent friendly references, progress-based boss phases, completion policies, and telemetry-only proof/XAR/scrap hooks. Damage, unrestricted AI, economy mutation, and save mutation remain blocked.\n\nDOCUMENTATION PHASE NOTE\nThe future Authoring Help Guide must include a complete worked Encounter workflow, wave limits, boss phases, friendly placement, reset policies, completion conditions, reward-hook approval, and troubleshooting missing references.\n")
            text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
