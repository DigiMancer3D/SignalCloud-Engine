from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from tools.pcp3 import editor_branch6 as branch6
from tools.pcp3.advanced_authoring import add_trigger, ensure_authoring
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.runtime_factory import ALLOWED_ACTIONS, ALLOWED_TRIGGER_TYPES, ensure_runtime_factory
from tools.pcp3.runtime_interaction import (
    InteractionSimulator,
    compile_runtime_interaction,
    ensure_runtime_interaction,
    runtime_interaction_udata,
    validate_runtime_interaction,
    write_runtime_interaction_files,
)


class SafeTriggerDialog(tk.Toplevel):
    """Compact authoring bridge for approved Branch 7 trigger records."""

    def __init__(self, parent: tk.Misc, focus: tuple[float, float, float], default_cooldown: float) -> None:
        super().__init__(parent)
        self.title("Add guarded interaction trigger")
        self.transient(parent)
        self.resizable(False, False)
        self.result: dict[str, Any] | None = None
        self.trigger_type = tk.StringVar(master=self, value="interaction")
        self.action = tk.StringVar(master=self, value="pulse_light")
        self.target = tk.StringVar(master=self, value="")
        self.radius = tk.DoubleVar(master=self, value=2.0)
        self.delay = tk.DoubleVar(master=self, value=0.0)
        self.cooldown = tk.DoubleVar(master=self, value=max(0.05, float(default_cooldown)))
        self.repeat = tk.BooleanVar(master=self, value=False)
        self.position = tuple(float(value) for value in focus)

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="This creates an approved trigger at the current 3D viewport focus.", wraplength=380).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 7))
        ttk.Label(body, text="Type").grid(row=1, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self.trigger_type, values=tuple(sorted(ALLOWED_TRIGGER_TYPES)), state="readonly", width=18).grid(row=1, column=1, sticky="ew")
        ttk.Label(body, text="Action").grid(row=2, column=0, sticky="w")
        ttk.Combobox(body, textvariable=self.action, values=tuple(sorted(ALLOWED_ACTIONS - {"none"})), state="readonly", width=18).grid(row=2, column=1, sticky="ew")
        ttk.Label(body, text="Target / theme").grid(row=3, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.target).grid(row=3, column=1, sticky="ew")
        for row, label, variable in (
            (4, "Radius", self.radius),
            (5, "Delay", self.delay),
            (6, "Cooldown", self.cooldown),
        ):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(body, from_=0.0 if label != "Cooldown" else 0.05, to=10000.0 if label == "Radius" else 60.0, increment=0.1, textvariable=variable, width=12).grid(row=row, column=1, sticky="ew")
        ttk.Checkbutton(body, text="Repeat after cooldown", variable=self.repeat).grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text=f"Position: X {self.position[0]:.3f} · Y {self.position[1]:.3f} · Z {self.position[2]:.3f}").grid(row=8, column=0, columnspan=2, sticky="w", pady=(5, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(9, 0))
        ttk.Button(buttons, text="Add Trigger", command=self._accept).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", fill="x", expand=True, padx=(4, 0))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Return>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _accept(self) -> None:
        try:
            radius = max(0.05, float(self.radius.get()))
            delay = max(0.0, float(self.delay.get()))
            cooldown = max(0.05, min(60.0, float(self.cooldown.get())))
        except (tk.TclError, TypeError, ValueError):
            messagebox.showwarning("Invalid trigger values", "Radius, delay, and cooldown must be valid numbers.", parent=self)
            return
        self.result = {
            "type": self.trigger_type.get(),
            "action": self.action.get(),
            "target": self.target.get().strip(),
            "radius": radius,
            "delay": delay,
            "cooldown": cooldown,
            "repeat": bool(self.repeat.get()),
            "position": self.position,
        }
        self.destroy()


class PCP3Editor(branch6.PCP3Editor):
    def __init__(self, root_path: Path) -> None:
        self.interaction_panel: ttk.Frame | None = None
        self.interaction_vars: dict[str, tk.Variable] = {}
        self.interaction_status: tk.StringVar | None = None
        self.interaction_trigger_summary: tk.StringVar | None = None
        self.interaction_findings: tk.Text | None = None
        self.interaction_ledger: tk.Text | None = None
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 7 Guarded Interaction Runtime")
        self.document.metadata["editor_branch"] = "ISL_plus_branch7"
        ensure_runtime_interaction(self.document)
        self.refresh_interaction_panel()
        self.update_status("Branch 7 active · reversible trigger actions · bounded event ledger · no arbitrary gameplay mutation")

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
            except (tk.TclError, ValueError, TypeError):
                continue
        if row is not None:
            ttk.Button(row, text="Interaction Runtime", command=self.show_interaction_runtime).pack(side="left", padx=2)

    def _insert_authoring_tab(self) -> None:
        super()._insert_authoring_tab()
        self._build_interaction_panel(self.authoring_notebook)

    def _build_interaction_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=5)
        notebook.add(panel, text="Interaction")
        self.interaction_panel = panel
        settings = ensure_runtime_interaction(self.document)
        self.interaction_status = tk.StringVar(master=self, value="Guarded Interaction Runtime ready")
        self.interaction_trigger_summary = tk.StringVar(master=self, value="No gameplay triggers authored yet")
        bridge = ttk.LabelFrame(panel, text="Authoring bridge", padding=4)
        bridge.pack(fill="x", pady=(0, 4))
        ttk.Label(bridge, textvariable=self.interaction_trigger_summary, wraplength=310).pack(fill="x")
        bridge_buttons = ttk.Frame(bridge)
        bridge_buttons.pack(fill="x", pady=(3, 0))
        ttk.Button(bridge_buttons, text="Open Gameplay Triggers", command=self.open_gameplay_trigger_authoring).pack(side="left", fill="x", expand=True)
        ttk.Button(bridge_buttons, text="Add Safe Trigger…", command=self.add_safe_trigger_from_interaction).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(bridge_buttons, text="Enable Safe Chain", command=self.enable_safe_runtime_chain).pack(side="left", fill="x", expand=True)

        types: dict[str, tuple[type[tk.Variable], Any]] = {
            "enabled": (tk.BooleanVar, settings["enabled"]),
            "game_enabled": (tk.BooleanVar, settings["game_enabled"]),
            "stress_enabled": (tk.BooleanVar, settings["stress_enabled"]),
            "default_cooldown": (tk.DoubleVar, settings["default_cooldown"]),
            "alert_duration": (tk.DoubleVar, settings["alert_duration"]),
            "pulse_duration": (tk.DoubleVar, settings["pulse_duration"]),
            "proxy_lifetime": (tk.DoubleVar, settings["proxy_lifetime"]),
            "max_state_entries": (tk.IntVar, settings["max_state_entries"]),
            "max_event_ledger": (tk.IntVar, settings["max_event_ledger"]),
            "max_active_proxies": (tk.IntVar, settings["max_active_proxies"]),
            "reset_policy": (tk.StringVar, settings["reset_policy"]),
            "show_runtime_evidence": (tk.BooleanVar, settings["show_runtime_evidence"]),
            "console_event_log": (tk.BooleanVar, settings["console_event_log"]),
        }
        self.interaction_vars = {key: cls(master=self, value=value) for key, (cls, value) in types.items()}

        targets = ttk.LabelFrame(panel, text="Explicit execution targets", padding=4)
        targets.pack(fill="x")
        ttk.Checkbutton(targets, text="Enable approved trigger actions", variable=self.interaction_vars["enabled"], command=self.interaction_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(targets, text="Game", variable=self.interaction_vars["game_enabled"], command=self.interaction_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(targets, text="Stress", variable=self.interaction_vars["stress_enabled"], command=self.interaction_changed).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(targets, text="Show action evidence", variable=self.interaction_vars["show_runtime_evidence"], command=self.interaction_changed).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(targets, text="Bounded console event log", variable=self.interaction_vars["console_event_log"], command=self.interaction_changed).grid(row=2, column=1, sticky="w")

        timing = ttk.LabelFrame(panel, text="Timing and reset policy", padding=4)
        timing.pack(fill="x", pady=4)
        fields = [
            ("Default cooldown", "default_cooldown", 0.05, 60.0, 0.05),
            ("Alert duration", "alert_duration", 0.1, 60.0, 0.1),
            ("Light-pulse duration", "pulse_duration", 0.1, 30.0, 0.05),
            ("Proxy lifetime", "proxy_lifetime", 0.25, 120.0, 0.25),
        ]
        for row, (label, key, lower, upper, step) in enumerate(fields):
            ttk.Label(timing, text=label).grid(row=row, column=0, sticky="w")
            ttk.Spinbox(timing, from_=lower, to=upper, increment=step, textvariable=self.interaction_vars[key], command=self.interaction_changed, width=10).grid(row=row, column=1, sticky="ew", padx=3)
        ttk.Label(timing, text="Reset policy").grid(row=len(fields), column=0, sticky="w")
        reset = ttk.Combobox(timing, textvariable=self.interaction_vars["reset_policy"], values=("zone_exit", "session", "manual"), state="readonly")
        reset.grid(row=len(fields), column=1, sticky="ew", padx=3)
        reset.bind("<<ComboboxSelected>>", lambda _event: self.interaction_changed())
        timing.columnconfigure(1, weight=1)

        limits = ttk.LabelFrame(panel, text="Bounded state limits", padding=4)
        limits.pack(fill="x")
        limit_rows = [
            ("Trigger states", "max_state_entries", (64, 128, 256, 512, 1024)),
            ("Event ledger", "max_event_ledger", (64, 128, 256, 512, 1024)),
            ("Active proxies", "max_active_proxies", (4, 8, 16, 32, 64)),
        ]
        for row, (label, key, values) in enumerate(limit_rows):
            ttk.Label(limits, text=label).grid(row=row, column=0, sticky="w")
            box = ttk.Combobox(limits, textvariable=self.interaction_vars[key], values=values, state="readonly")
            box.grid(row=row, column=1, sticky="ew", padx=3)
            box.bind("<<ComboboxSelected>>", lambda _event: self.interaction_changed())
        limits.columnconfigure(1, weight=1)

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="Validate", command=self.validate_interaction).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Compile Dry Run", command=self.compile_interaction_dry_run).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="Simulate Triggers", command=self.simulate_interactions).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Reset Safe Defaults", command=self.reset_interaction_defaults).pack(side="left", fill="x", expand=True, padx=(2, 0))

        ttk.Label(panel, textvariable=self.interaction_status, wraplength=310, font=("Sans", 9, "bold")).pack(fill="x")
        notebook2 = ttk.Notebook(panel)
        notebook2.pack(fill="both", expand=True, pady=(3, 0))
        findings_tab = ttk.Frame(notebook2)
        ledger_tab = ttk.Frame(notebook2)
        notebook2.add(findings_tab, text="Findings")
        notebook2.add(ledger_tab, text="Dry-run ledger")
        self.interaction_findings = tk.Text(findings_tab, height=8, wrap="word", state="disabled")
        self.interaction_findings.pack(fill="both", expand=True)
        self.interaction_ledger = tk.Text(ledger_tab, height=8, wrap="word", state="disabled")
        self.interaction_ledger.pack(fill="both", expand=True)

    def sync_interaction_from_ui(self) -> dict[str, Any]:
        settings = ensure_runtime_interaction(self.document)
        for key, variable in self.interaction_vars.items():
            settings[key] = variable.get()
        return ensure_runtime_interaction(self.document)

    def interaction_changed(self) -> None:
        self.sync_interaction_from_ui()
        self.mark_dirty("Guarded Interaction Runtime settings")
        self.refresh_interaction_panel()

    def open_gameplay_trigger_authoring(self) -> None:
        self.right_notebook.select(self.authoring_tab)
        for index in range(int(self.authoring_notebook.index("end"))):
            if str(self.authoring_notebook.tab(index, "text")) == "Gameplay":
                self.authoring_notebook.select(index)
                break
        self.update_status("Gameplay trigger authoring opened · choose an approved type/action, then Add Trigger")

    def add_safe_trigger_from_interaction(self) -> None:
        settings = ensure_runtime_interaction(self.document)
        dialog = SafeTriggerDialog(self, self.current_focus(), float(settings["default_cooldown"]))
        self.wait_window(dialog)
        if not dialog.result:
            return
        data = dialog.result
        self._mutate(
            "Add guarded interaction trigger",
            lambda: add_trigger(
                ensure_authoring(self.document),
                data["type"],
                data["position"],
                data["radius"],
                data["action"],
                data["target"],
                data["delay"],
                data["repeat"],
                data["cooldown"],
            ),
        )
        self.refresh_authoring_studio()
        self.refresh_interaction_panel()
        self.update_status(f"Added guarded {data['type']} → {data['action']} trigger")

    def enable_safe_runtime_chain(self) -> None:
        settings = self.sync_interaction_from_ui()
        settings["enabled"] = True
        if not (settings["game_enabled"] or settings["stress_enabled"]):
            settings["stress_enabled"] = True
        factory = ensure_runtime_factory(self.document)
        factory["enabled"] = True
        factory["game_enabled"] = bool(settings["game_enabled"])
        factory["stress_enabled"] = bool(settings["stress_enabled"])
        self.mark_dirty("Enabled guarded Factory + Interaction chain")
        self.refresh_factory_panel()
        self.refresh_interaction_panel()

    def refresh_interaction_panel(self) -> None:
        if self.interaction_panel is None:
            return
        settings = ensure_runtime_interaction(self.document)
        for key, variable in self.interaction_vars.items():
            if key in settings and variable.get() != settings[key]:
                variable.set(settings[key])
        issues = validate_runtime_interaction(self.document)
        counts = {name: sum(1 for issue in issues if issue.severity == name) for name in ("error", "warning", "info", "pass")}
        compiled = compile_runtime_interaction(self.document)
        authored = len(compiled["triggers"])
        approved = sum(1 for trigger in compiled["triggers"] if trigger["runtime_status"] == "approved" and trigger["action"] != "none")
        deferred = authored - approved
        if self.interaction_trigger_summary is not None:
            if authored:
                self.interaction_trigger_summary.set(f"Authored triggers: {authored} · approved: {approved} · telemetry-only: {deferred}")
            else:
                self.interaction_trigger_summary.set("No triggers are stored in this project. Open Gameplay Triggers or add a safe trigger here.")
        if self.interaction_status is not None:
            state = "ENABLED" if settings["enabled"] else "disabled"
            targets = "/".join(name for name, on in (("game", settings["game_enabled"]), ("stress", settings["stress_enabled"])) if on) or "none"
            factory = ensure_runtime_factory(self.document)
            blocked = settings["enabled"] and not factory["enabled"]
            prefix = "BLOCKED: Factory disabled · " if blocked else ""
            self.interaction_status.set(f"{prefix}Interaction {state} · targets {targets} · {approved} approved actions · {counts['warning']} warnings")
        if self.interaction_findings is not None:
            self.interaction_findings.configure(state="normal")
            self.interaction_findings.delete("1.0", "end")
            for issue in issues:
                self.interaction_findings.insert("end", f"{issue.severity.upper()}: {issue.message}\n")
            self.interaction_findings.configure(state="disabled")

    def validate_interaction(self) -> list[Any]:
        self.sync_interaction_from_ui()
        issues = validate_runtime_interaction(self.document)
        messagebox.showinfo("Guarded Interaction validation", "\n".join(f"{item.severity.upper()}: {item.message}" for item in issues[:22]), parent=self)
        self.refresh_interaction_panel()
        return issues

    def compile_interaction_dry_run(self) -> None:
        try:
            self.sync_interaction_from_ui()
            payload = compile_runtime_interaction(self.document)
            folder = self.root_path / "user_data" / "pcp3" / "interaction_dry_runs" / slugify(self.document.asset_id)
            folder.mkdir(parents=True, exist_ok=True)
            atomic_write_text(folder / "runtime_interaction.pcp3interaction.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
            atomic_write_text(folder / "runtime_interaction.pcp3interaction.udata", runtime_interaction_udata(payload))
            self.interaction_status.set(f"Interaction dry run compiled · {len(payload['triggers'])} trigger policies")
            messagebox.showinfo("Interaction dry run", f"Compiled bounded interaction files under:\n{folder}\n\nNo game state was changed.", parent=self)
        except Exception as exc:
            messagebox.showerror("Interaction compile failed", str(exc), parent=self)

    def simulate_interactions(self) -> None:
        self.sync_interaction_from_ui()
        payload = compile_runtime_interaction(self.document)
        simulator = InteractionSimulator(payload)
        events: list[dict[str, Any]] = []
        # Exercise scanner, proximity, timer, and an explicit interaction without mutating the document.
        for step in range(12):
            now = step * 0.5
            events.extend(simulator.update(
                now=now,
                viewer=(0.0, 0.0, 0.0),
                scanner=step >= 2,
                interaction_pressed=step in {4, 8},
                zone="Dry Run",
            ))
        lines = [
            f"{event['time']:.2f}s · trigger {event['trigger'] + 1} · {event['action']} · {event['target'] or '(no target)'}"
            for event in events
        ]
        lines += [
            "",
            f"Final visible: {simulator.visible}",
            f"Revealed: {simulator.revealed}",
            f"Theme target: {simulator.theme_target or '(none)'}",
            f"Active proxies: {len(simulator.proxies)}",
        ]
        if self.interaction_ledger is not None:
            self.interaction_ledger.configure(state="normal")
            self.interaction_ledger.delete("1.0", "end")
            self.interaction_ledger.insert("end", "\n".join(lines) if lines else "No approved trigger action fired in the six-second dry run.")
            self.interaction_ledger.configure(state="disabled")
        self.update_status(f"Interaction dry-run simulation complete · {len(events)} events")

    def reset_interaction_defaults(self) -> None:
        self.document.metadata.pop("runtime_interaction", None)
        ensure_runtime_interaction(self.document)
        self.refresh_interaction_panel()
        self.mark_dirty("Reset Guarded Interaction Runtime")

    def show_interaction_runtime(self) -> None:
        self.right_notebook.select(self.authoring_tab)
        self.authoring_notebook.select(self.interaction_panel)
        self.refresh_interaction_panel()

    def export_to_database(self) -> None:
        self.sync_interaction_from_ui()
        asset_name = slugify(self.document.asset_id)
        self.document.metadata["interaction_json_file"] = f"{asset_name}.pcp3interaction.json"
        self.document.metadata["interaction_udata_file"] = f"{asset_name}.pcp3interaction.udata"
        super().export_to_database()
        asset_dir = self.root_path / "content" / "pcp3_assets" / self.document.environment_type / asset_name
        if asset_dir.exists():
            try:
                paths = write_runtime_interaction_files(asset_dir, self.document)
                self.update_status("Exported PCP3 asset with guarded interaction sidecars")
                if ensure_runtime_interaction(self.document)["enabled"]:
                    messagebox.showinfo("Interaction Runtime exported", f"Guarded interaction policy compiled:\n{paths['json'].name}\n{paths['udata'].name}", parent=self)
            except Exception as exc:
                messagebox.showwarning("Interaction Runtime warning", str(exc), parent=self)

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        ensure_runtime_interaction(self.document)
        if self.interaction_panel is not None:
            self.refresh_interaction_panel()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if self.interaction_panel is not None:
            self.refresh_interaction_panel()

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
                result = find_text(child)
                if result is not None:
                    return result
            return None

        text = find_text(created[-1])
        if text is not None:
            text.configure(state="normal")
            text.insert("end", "Branch 7 Guarded Interaction Runtime\n", "heading")
            text.insert(
                "end",
                "Authoring → Interaction enables a bounded reversible state machine for approved show, hide, reveal, alert, spawn-proxy, theme, and light-pulse actions. Trigger state and event history are capped. Damage, inventory, economy, saves, teleportation, external programs, and arbitrary scripts remain blocked.\n\n",
            )
            text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
