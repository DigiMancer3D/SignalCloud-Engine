from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from tools.pcp3 import editor_branch5 as branch5
from tools.pcp3.advanced_authoring import ensure_authoring
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.runtime_factory import (
    compile_runtime_factory,
    ensure_runtime_factory,
    runtime_factory_udata,
    validate_runtime_factory,
    write_runtime_factory_files,
)


class PCP3Editor(branch5.PCP3Editor):
    def __init__(self, root_path: Path) -> None:
        self.factory_panel: ttk.Frame | None = None
        self.factory_vars: dict[str, tk.Variable] = {}
        self.factory_status: tk.StringVar | None = None
        self.factory_findings: tk.Text | None = None
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 6 Runtime Factory Bridge")
        self.document.metadata["editor_branch"] = "ISL_plus_branch6"
        ensure_runtime_factory(self.document)
        self.refresh_factory_panel()
        self.update_status("Branch 6 active · guarded Runtime Factory Bridge · no arbitrary code execution")

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
            ttk.Button(row, text="Runtime Factory", command=self.show_runtime_factory).pack(side="left", padx=2)

    def _insert_authoring_tab(self) -> None:
        super()._insert_authoring_tab()
        self._build_factory_panel(self.authoring_notebook)

    def _build_factory_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=5)
        notebook.add(panel, text="Factory")
        self.factory_panel = panel
        factory = ensure_runtime_factory(self.document)
        self.factory_status = tk.StringVar(master=self, value="Runtime Factory ready")
        types: dict[str, tuple[type[tk.Variable], Any]] = {
            "enabled": (tk.BooleanVar, factory["enabled"]),
            "game_enabled": (tk.BooleanVar, factory["game_enabled"]),
            "stress_enabled": (tk.BooleanVar, factory["stress_enabled"]),
            "root_motion": (tk.BooleanVar, factory["root_motion"]),
            "scanner_gate": (tk.BooleanVar, factory["scanner_gate"]),
            "proximity_gate": (tk.BooleanVar, factory["proximity_gate"]),
            "proximity_radius": (tk.DoubleVar, factory["proximity_radius"]),
            "nested_placements": (tk.BooleanVar, factory["nested_placements"]),
            "trigger_debug": (tk.BooleanVar, factory["trigger_debug"]),
            "flow_debug": (tk.BooleanVar, factory["flow_debug"]),
            "theme_runtime": (tk.BooleanVar, factory["theme_runtime"]),
            "max_nested_points": (tk.IntVar, factory["max_nested_points"]),
            "selected_clip": (tk.StringVar, factory["selected_clip"]),
            "event_policy": (tk.StringVar, factory["event_policy"]),
        }
        self.factory_vars = {key: cls(master=self, value=value) for key, (cls, value) in types.items()}

        target = ttk.LabelFrame(panel, text="Factory targets", padding=4)
        target.pack(fill="x")
        ttk.Checkbutton(target, text="Enable guarded runtime factory", variable=self.factory_vars["enabled"], command=self.factory_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(target, text="Game", variable=self.factory_vars["game_enabled"], command=self.factory_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(target, text="Stress", variable=self.factory_vars["stress_enabled"], command=self.factory_changed).grid(row=1, column=1, sticky="w")

        systems = ttk.LabelFrame(panel, text="Approved runtime systems", padding=4)
        systems.pack(fill="x", pady=4)
        labels = [
            ("root_motion", "Root-motion timeline"), ("nested_placements", "One-level PCP3 placements"),
            ("scanner_gate", "Scanner visibility gate"), ("proximity_gate", "Proximity visibility gate"),
            ("trigger_debug", "Trigger evidence"), ("flow_debug", "Flow evidence"),
            ("theme_runtime", "Theme runtime tint"),
        ]
        for index, (key, label) in enumerate(labels):
            ttk.Checkbutton(systems, text=label, variable=self.factory_vars[key], command=self.factory_changed).grid(row=index // 2, column=index % 2, sticky="w", padx=2)

        values = ttk.LabelFrame(panel, text="Limits and clip", padding=4)
        values.pack(fill="x")
        ttk.Label(values, text="Clip").grid(row=0, column=0, sticky="w")
        self.factory_clip_combo = ttk.Combobox(values, textvariable=self.factory_vars["selected_clip"], state="readonly", width=19)
        self.factory_clip_combo.grid(row=0, column=1, sticky="ew", padx=3)
        self.factory_clip_combo.bind("<<ComboboxSelected>>", lambda _event: self.factory_changed())
        ttk.Label(values, text="Proximity radius").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(values, from_=0.1, to=10000.0, increment=0.5, textvariable=self.factory_vars["proximity_radius"], command=self.factory_changed).grid(row=1, column=1, sticky="ew", padx=3)
        ttk.Label(values, text="Nested point cap").grid(row=2, column=0, sticky="w")
        ttk.Combobox(values, textvariable=self.factory_vars["max_nested_points"], values=(10_000, 25_000, 50_000, 100_000, 250_000, 500_000), state="readonly").grid(row=2, column=1, sticky="ew", padx=3)
        ttk.Label(values, text="Event policy").grid(row=3, column=0, sticky="w")
        ttk.Combobox(values, textvariable=self.factory_vars["event_policy"], values=("telemetry_only", "disabled"), state="readonly").grid(row=3, column=1, sticky="ew", padx=3)
        values.columnconfigure(1, weight=1)

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="Validate", command=self.validate_factory).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Compile Dry Run", command=self.compile_factory_dry_run).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="Reset Safe Defaults", command=self.reset_factory_defaults).pack(side="left", fill="x", expand=True)
        ttk.Label(panel, textvariable=self.factory_status, wraplength=310, font=("Sans", 9, "bold")).pack(fill="x")
        self.factory_findings = tk.Text(panel, height=9, wrap="word", state="disabled")
        self.factory_findings.pack(fill="both", expand=True, pady=(3, 0))

    def sync_factory_from_ui(self) -> dict[str, Any]:
        factory = ensure_runtime_factory(self.document)
        for key, variable in self.factory_vars.items():
            factory[key] = variable.get()
        return ensure_runtime_factory(self.document)

    def factory_changed(self) -> None:
        self.sync_factory_from_ui()
        self.mark_dirty("Runtime Factory settings")
        self.refresh_factory_panel()

    def refresh_factory_panel(self) -> None:
        if self.factory_panel is None:
            return
        factory = ensure_runtime_factory(self.document)
        authoring = ensure_authoring(self.document)
        clips = [str(clip.get("name", "Default")) for clip in authoring.get("timelines", []) if isinstance(clip, dict)] or ["Default"]
        self.factory_clip_combo.configure(values=clips)
        if str(factory.get("selected_clip")) not in clips:
            factory["selected_clip"] = clips[0]
        for key, variable in self.factory_vars.items():
            if key in factory and variable.get() != factory[key]:
                variable.set(factory[key])
        issues = validate_runtime_factory(self.document)
        counts = {name: sum(1 for issue in issues if issue.severity == name) for name in ("error", "warning", "info", "pass")}
        if self.factory_status is not None:
            state = "ENABLED" if factory["enabled"] else "disabled"
            targets = "/".join(name for name, on in (("game", factory["game_enabled"]), ("stress", factory["stress_enabled"])) if on) or "none"
            self.factory_status.set(f"Factory {state} · targets {targets} · {counts['error']} errors · {counts['warning']} warnings")
        if self.factory_findings is not None:
            self.factory_findings.configure(state="normal")
            self.factory_findings.delete("1.0", "end")
            for issue in issues:
                self.factory_findings.insert("end", f"{issue.severity.upper()}: {issue.message}\n")
            self.factory_findings.configure(state="disabled")

    def validate_factory(self) -> list[Any]:
        self.sync_factory_from_ui()
        issues = validate_runtime_factory(self.document)
        messagebox.showinfo("Runtime Factory validation", "\n".join(f"{item.severity.upper()}: {item.message}" for item in issues[:20]), parent=self)
        self.refresh_factory_panel()
        return issues

    def compile_factory_dry_run(self) -> None:
        try:
            self.sync_factory_from_ui()
            payload = compile_runtime_factory(self.document)
            folder = self.root_path / "user_data" / "pcp3" / "factory_dry_runs" / slugify(self.document.asset_id)
            folder.mkdir(parents=True, exist_ok=True)
            atomic_write_text(folder / "runtime_factory.pcp3factory.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
            atomic_write_text(folder / "runtime_factory.pcp3factory.udata", runtime_factory_udata(payload))
            self.factory_status.set(f"Dry run compiled · {len(payload['timeline']['keyframes'])} keys · {len(payload['nested_placements'])} placements")
            messagebox.showinfo("Runtime Factory dry run", f"Compiled guarded factory files under:\n{folder}\n\nNo game state was changed.", parent=self)
        except Exception as exc:
            messagebox.showerror("Factory compile failed", str(exc), parent=self)

    def reset_factory_defaults(self) -> None:
        self.document.metadata.pop("runtime_factory", None)
        ensure_runtime_factory(self.document)
        self.refresh_factory_panel()
        self.mark_dirty("Reset Runtime Factory")

    def show_runtime_factory(self) -> None:
        self.right_notebook.select(self.authoring_tab)
        self.authoring_notebook.select(self.factory_panel)
        self.refresh_factory_panel()

    def export_to_database(self) -> None:
        self.sync_factory_from_ui()
        asset_name = slugify(self.document.asset_id)
        self.document.metadata["factory_json_file"] = f"{asset_name}.pcp3factory.json"
        self.document.metadata["factory_udata_file"] = f"{asset_name}.pcp3factory.udata"
        super().export_to_database()
        asset_dir = self.root_path / "content" / "pcp3_assets" / self.document.environment_type / asset_name
        if asset_dir.exists():
            try:
                paths = write_runtime_factory_files(asset_dir, self.document)
                self.update_status("Exported PCP3 asset with guarded Runtime Factory sidecars")
                if ensure_runtime_factory(self.document)["enabled"]:
                    messagebox.showinfo("Runtime Factory exported", f"Guarded factory compiled:\n{paths['json'].name}\n{paths['udata'].name}", parent=self)
            except Exception as exc:
                messagebox.showwarning("Runtime Factory warning", str(exc), parent=self)

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        ensure_runtime_factory(self.document)
        if self.factory_panel is not None:
            self.refresh_factory_panel()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if self.factory_panel is not None:
            self.refresh_factory_panel()

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
            text.insert("end", "Branch 6 Runtime Factory Bridge\n", "heading")
            text.insert("end", "Authoring → Factory compiles explicitly enabled, bounded runtime behavior. Root motion, scanner/proximity gates, one-level PCP3 placements, trigger/flow evidence, and theme runtime are approved. Arbitrary scripts, damage, economy changes, raid logic, and deep nesting remain blocked.\n\n")
            text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
