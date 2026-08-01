from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from tools.pcp3 import editor_branch10r2 as branch10r2
from tools.pcp3.io import atomic_write_text, slugify
AUTHORING_SUBTAB_LABELS = (
    "Rig", "Timeline", "Gameplay", "Placement", "Flow/Theme", "Playback",
    "Factory", "Interaction", "Entity", "World", "Encounter", "Streaming",
)

from tools.pcp3.streaming_runtime import (
    LOD_POLICIES,
    PROFILES,
    apply_profile,
    build_chunk_manifest,
    compile_streaming_runtime,
    ensure_streaming_runtime,
    normalized_streaming_runtime,
    validate_streaming_runtime,
    write_streaming_runtime_files,
)


class PCP3Editor(branch10r2.PCP3Editor):
    """Branch 11: Streaming, LOD and bounded large-asset runtime authoring."""

    def __init__(self, root_path: Path) -> None:
        self.streaming_panel: ttk.Frame | None = None
        self.streaming_vars: dict[str, tk.Variable] = {}
        self.streaming_status: tk.StringVar | None = None
        self.streaming_findings: tk.Text | None = None
        self.streaming_chunk_tree: ttk.Treeview | None = None
        self.streaming_lod_tree: ttk.Treeview | None = None
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch11"
        self.document.metadata["streaming_runtime_version"] = "distance_lod_semantic_reserve_v1"
        ensure_streaming_runtime(self.document)
        self.refresh_streaming_panel()
        if self.authoring_wrapped_tabs is not None:
            self.authoring_wrapped_tabs.refresh()
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 11 Streaming, LOD & Large-Asset Runtime")
        self.update_status(
            "Branch 11 active · bounded spatial chunks · distance LOD · semantic reserve · adaptive 8M-compatible presets"
        )

    def _insert_authoring_tab(self) -> None:
        super()._insert_authoring_tab()
        self._build_streaming_panel(self.authoring_notebook)

    def _build_streaming_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4)
        notebook.add(panel, text="Streaming")
        self.streaming_panel = panel
        settings = ensure_streaming_runtime(self.document)
        self.streaming_status = tk.StringVar(master=self, value="Streaming Runtime pending")
        ttk.Label(panel, textvariable=self.streaming_status, wraplength=330, font=("Sans", 9, "bold")).pack(fill="x")

        types: dict[str, tuple[type[tk.Variable], Any]] = {
            "enabled": (tk.BooleanVar, settings["enabled"]),
            "game_enabled": (tk.BooleanVar, settings["game_enabled"]),
            "stress_enabled": (tk.BooleanVar, settings["stress_enabled"]),
            "profile": (tk.StringVar, settings["profile"]),
            "lod_policy": (tk.StringVar, settings["lod_policy"]),
            "chunk_edge": (tk.DoubleVar, settings["chunk_edge"]),
            "chunk_point_target": (tk.IntVar, settings["chunk_point_target"]),
            "near_distance": (tk.DoubleVar, settings["near_distance"]),
            "mid_distance": (tk.DoubleVar, settings["mid_distance"]),
            "far_distance": (tk.DoubleVar, settings["far_distance"]),
            "near_ratio": (tk.DoubleVar, settings["near_ratio"]),
            "mid_ratio": (tk.DoubleVar, settings["mid_ratio"]),
            "far_ratio": (tk.DoubleVar, settings["far_ratio"]),
            "very_far_ratio": (tk.DoubleVar, settings["very_far_ratio"]),
            "minimum_points": (tk.IntVar, settings["minimum_points"]),
            "maximum_points": (tk.IntVar, settings["maximum_points"]),
            "max_resident_chunks": (tk.IntVar, settings["max_resident_chunks"]),
            "background_loading": (tk.BooleanVar, settings["background_loading"]),
            "preload_adjacent": (tk.BooleanVar, settings["preload_adjacent"]),
            "preserve_semantic_points": (tk.BooleanVar, settings["preserve_semantic_points"]),
            "semantic_reserve_ratio": (tk.DoubleVar, settings["semantic_reserve_ratio"]),
            "frame_upload_budget_points": (tk.IntVar, settings["frame_upload_budget_points"]),
            "stability_hysteresis": (tk.DoubleVar, settings["stability_hysteresis"]),
            "show_debug": (tk.BooleanVar, settings["show_debug"]),
        }
        self.streaming_vars = {key: cls(master=self, value=value) for key, (cls, value) in types.items()}

        sub = ttk.Notebook(panel)
        sub.pack(fill="both", expand=True, pady=4)
        self._build_stream_setup_page(sub)
        self._build_stream_lod_page(sub)
        self._build_stream_chunks_page(sub)
        self._build_stream_audit_page(sub)

        actions = ttk.Frame(panel)
        actions.pack(fill="x")
        ttk.Button(actions, text="Apply Profile", command=self.apply_streaming_profile).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Validate", command=self.validate_streaming).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(actions, text="Compile Dry Run", command=self.compile_streaming_dry_run).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Refresh", command=self.refresh_streaming_panel).pack(side="left", fill="x", expand=True, padx=(2, 0))

        self.streaming_findings = tk.Text(panel, height=7, wrap="word", state="disabled")
        self.streaming_findings.pack(fill="both", expand=True, pady=(4, 0))

    def _spin(self, master: tk.Misc, row: int, label: str, key: str, low: float, high: float, increment: float = 1.0) -> None:
        ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=2, pady=2)
        widget = ttk.Spinbox(master, from_=low, to=high, increment=increment, textvariable=self.streaming_vars[key], command=self.streaming_changed)
        widget.grid(row=row, column=1, sticky="ew", padx=2, pady=2)
        widget.bind("<FocusOut>", lambda _event: self.streaming_changed())

    def _build_stream_setup_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Setup")
        targets = ttk.LabelFrame(page, text="Explicit streaming targets", padding=4)
        targets.pack(fill="x")
        ttk.Checkbutton(targets, text="Enable Streaming Runtime", variable=self.streaming_vars["enabled"], command=self.streaming_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(targets, text="Game", variable=self.streaming_vars["game_enabled"], command=self.streaming_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(targets, text="Stress", variable=self.streaming_vars["stress_enabled"], command=self.streaming_changed).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(targets, text="Streaming debug evidence", variable=self.streaming_vars["show_debug"], command=self.streaming_changed).grid(row=2, column=0, columnspan=2, sticky="w")

        profile = ttk.LabelFrame(page, text="Hardware/profile preset", padding=4)
        profile.pack(fill="x", pady=4)
        profile.columnconfigure(1, weight=1)
        ttk.Label(profile, text="Profile").grid(row=0, column=0, sticky="w")
        combo = ttk.Combobox(profile, values=PROFILES, state="readonly", textvariable=self.streaming_vars["profile"])
        combo.grid(row=0, column=1, sticky="ew", padx=2)
        combo.bind("<<ComboboxSelected>>", lambda _event: self.streaming_changed())
        ttk.Label(profile, text="Adaptive 8M preserves the verified Intel/Mesa resident baseline while bounding each authored asset.", wraplength=310).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))

        loading = ttk.LabelFrame(page, text="Bounded loading intent", padding=4)
        loading.pack(fill="x")
        ttk.Checkbutton(loading, text="Background loading", variable=self.streaming_vars["background_loading"], command=self.streaming_changed).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(loading, text="Preload adjacent chunks", variable=self.streaming_vars["preload_adjacent"], command=self.streaming_changed).grid(row=0, column=1, sticky="w")
        loading.columnconfigure(1, weight=1)
        self._spin(loading, 1, "Max resident chunks", "max_resident_chunks", 1, 4096, 1)
        self._spin(loading, 2, "Frame upload budget", "frame_upload_budget_points", 1000, 2_000_000, 1000)
        ttk.Label(loading, text="Background loading is compiled as bounded intent and telemetry. Current live execution performs deterministic distance LOD without a free-running worker thread.", wraplength=320).grid(row=3, column=0, columnspan=2, sticky="w", pady=(3, 0))

    def _build_stream_lod_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="LOD")
        policy = ttk.LabelFrame(page, text="Distance detail policy", padding=4)
        policy.pack(fill="x")
        policy.columnconfigure(1, weight=1)
        ttk.Label(policy, text="LOD policy").grid(row=0, column=0, sticky="w")
        combo = ttk.Combobox(policy, values=LOD_POLICIES, state="readonly", textvariable=self.streaming_vars["lod_policy"])
        combo.grid(row=0, column=1, sticky="ew", padx=2)
        combo.bind("<<ComboboxSelected>>", lambda _event: self.streaming_changed())
        for row, values in enumerate((
            ("Near distance", "near_distance", 0.1, 10_000.0, 0.5),
            ("Mid distance", "mid_distance", 0.1, 20_000.0, 0.5),
            ("Far distance", "far_distance", 0.1, 50_000.0, 1.0),
            ("Near ratio", "near_ratio", 0.0, 1.0, 0.01),
            ("Mid ratio", "mid_ratio", 0.0, 1.0, 0.01),
            ("Far ratio", "far_ratio", 0.0, 1.0, 0.01),
            ("Very-far ratio", "very_far_ratio", 0.0, 1.0, 0.005),
            ("Stability hysteresis", "stability_hysteresis", 0.0, 1.0, 0.01),
        ), start=1):
            self._spin(policy, row, *values)

        bounds = ttk.LabelFrame(page, text="Per-asset point bounds", padding=4)
        bounds.pack(fill="x", pady=4)
        bounds.columnconfigure(1, weight=1)
        self._spin(bounds, 0, "Minimum points", "minimum_points", 1, 500_000, 128)
        self._spin(bounds, 1, "Maximum points", "maximum_points", 1, 500_000, 1000)
        ttk.Checkbutton(bounds, text="Preserve structural/semantic points", variable=self.streaming_vars["preserve_semantic_points"], command=self.streaming_changed).grid(row=2, column=0, columnspan=2, sticky="w")
        self._spin(bounds, 3, "Semantic reserve ratio", "semantic_reserve_ratio", 0.0, 1.0, 0.01)

        columns = ("tier", "distance", "ratio", "points")
        tree = ttk.Treeview(page, columns=columns, show="headings", height=5)
        for column, heading, width in zip(columns, ("Tier", "Starts after", "Ratio", "Planned points"), (75, 90, 70, 105)):
            tree.heading(column, text=heading)
            tree.column(column, width=width, stretch=True)
        tree.pack(fill="x")
        self.streaming_lod_tree = tree

    def _build_stream_chunks_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Chunks")
        controls = ttk.LabelFrame(page, text="Spatial chunk manifest", padding=4)
        controls.pack(fill="x")
        controls.columnconfigure(1, weight=1)
        self._spin(controls, 0, "Chunk edge", "chunk_edge", 1.0, 128.0, 0.5)
        self._spin(controls, 1, "Target points/chunk", "chunk_point_target", 1024, 500_000, 1024)
        ttk.Label(controls, text="Chunk manifests are deterministic authoring metadata. They do not split or rewrite the sealed PCP3 source cloud.", wraplength=315).grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

        columns = ("id", "grid", "points", "important", "radius")
        tree = ttk.Treeview(page, columns=columns, show="headings", height=10)
        for column, heading, width in zip(columns, ("Chunk", "Grid", "Points", "Priority", "Radius"), (90, 100, 70, 70, 70)):
            tree.heading(column, text=heading)
            tree.column(column, width=width, stretch=True)
        tree.pack(fill="both", expand=True, pady=(4, 0))
        self.streaming_chunk_tree = tree

    def _build_stream_audit_page(self, notebook: ttk.Notebook) -> None:
        page = ttk.Frame(notebook, padding=4)
        notebook.add(page, text="Audit")
        ttk.Label(page, text=(
            "The Streaming Audit compares source points, deterministic chunks, semantic reserves, LOD tiers, resident-chunk intent, and upload budgets. "
            "It never mutates project geometry, certificates, saves, or game economy state."
        ), wraplength=325).pack(fill="x")
        ttk.Button(page, text="Build / Refresh Chunk Audit", command=self.refresh_streaming_panel).pack(fill="x", pady=4)
        ttk.Button(page, text="Write Dry-Run Sidecars", command=self.compile_streaming_dry_run).pack(fill="x")

    def sync_streaming_from_ui(self) -> dict[str, Any]:
        settings = ensure_streaming_runtime(self.document)
        for key, variable in self.streaming_vars.items():
            try:
                settings[key] = variable.get()
            except tk.TclError:
                continue
        normalized = normalized_streaming_runtime(self.document)
        settings.update(normalized)
        return settings

    def streaming_changed(self) -> None:
        if not self.streaming_vars:
            return
        self.sync_streaming_from_ui()
        self.mark_dirty("Streaming Runtime settings")
        self.refresh_streaming_panel(sync_ui=False)

    def apply_streaming_profile(self) -> None:
        settings = self.sync_streaming_from_ui()
        apply_profile(settings, str(self.streaming_vars["profile"].get()))
        ensure_streaming_runtime(self.document).update(settings)
        self._load_streaming_vars(settings)
        self.mark_dirty("Streaming profile")
        self.refresh_streaming_panel(sync_ui=False)

    def _load_streaming_vars(self, settings: dict[str, Any]) -> None:
        for key, variable in self.streaming_vars.items():
            if key not in settings:
                continue
            try:
                variable.set(settings[key])
            except tk.TclError:
                pass

    def refresh_streaming_panel(self, sync_ui: bool = True) -> None:
        if self.streaming_panel is None:
            return
        settings = normalized_streaming_runtime(self.document)
        if sync_ui:
            self._load_streaming_vars(settings)
        payload = compile_streaming_runtime(self.document)
        if self.streaming_status is not None:
            targets = []
            if settings["game_enabled"]:
                targets.append("game")
            if settings["stress_enabled"]:
                targets.append("stress")
            self.streaming_status.set(
                f"Streaming {'enabled' if settings['enabled'] else 'disabled'} · targets {','.join(targets) or 'none'} · "
                f"profile {settings['profile']} · {payload['chunk_count']} chunks · source {len(self.document.points):,} points"
            )
        if self.streaming_lod_tree is not None:
            self.streaming_lod_tree.delete(*self.streaming_lod_tree.get_children())
            for sample in payload["lod_samples"]:
                self.streaming_lod_tree.insert("", "end", values=(
                    sample["tier"], f"{sample['distance']:.2f}", f"{sample['ratio']:.3f}", f"{sample['planned_points']:,}",
                ))
        if self.streaming_chunk_tree is not None:
            manifest = build_chunk_manifest(self.document, settings)
            self.streaming_chunk_tree.delete(*self.streaming_chunk_tree.get_children())
            for chunk in manifest["chunks"][:500]:
                self.streaming_chunk_tree.insert("", "end", values=(
                    chunk["id"], ",".join(str(v) for v in chunk["grid"]), f"{chunk['point_count']:,}",
                    f"{chunk['important_points']:,}", f"{chunk['radius']:.2f}",
                ))
        self._show_streaming_findings(payload["findings"])

    def _show_streaming_findings(self, findings: list[dict[str, str]]) -> None:
        if self.streaming_findings is None:
            return
        self.streaming_findings.configure(state="normal")
        self.streaming_findings.delete("1.0", "end")
        for finding in findings:
            self.streaming_findings.insert("end", f"{finding['severity'].upper()}: {finding['message']}\n")
        self.streaming_findings.configure(state="disabled")

    def validate_streaming(self) -> None:
        self.sync_streaming_from_ui()
        findings = validate_streaming_runtime(self.document)
        self._show_streaming_findings(findings)
        errors = sum(1 for finding in findings if finding["severity"] == "error")
        self.update_status(f"Streaming validation: {errors} error(s), {len(findings)} finding(s)")

    def compile_streaming_dry_run(self) -> None:
        self.sync_streaming_from_ui()
        payload = compile_streaming_runtime(self.document)
        manifest = build_chunk_manifest(self.document)
        folder = self.root_path / "user_data" / "pcp3" / "streaming_dry_runs" / slugify(self.document.asset_id)
        folder.mkdir(parents=True, exist_ok=True)
        json_path = folder / "runtime_streaming.pcp3stream.json"
        chunk_path = folder / "runtime_streaming.pcp3chunks.json"
        atomic_write_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        atomic_write_text(chunk_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        self.update_status(f"Streaming dry run compiled · {payload['chunk_count']} chunks")
        messagebox.showinfo("Streaming dry run", f"Created:\n{json_path}\n{chunk_path}", parent=self)

    def show_streaming_runtime(self) -> None:
        self.show_authoring_studio()
        if self.streaming_panel is not None:
            self.authoring_notebook.select(self.streaming_panel)
            if self.authoring_wrapped_tabs is not None:
                self.authoring_wrapped_tabs.refresh()

    def export_to_database(self) -> None:
        self.sync_streaming_from_ui()
        asset_name = slugify(self.document.asset_id)
        self.document.metadata["streaming_json_file"] = f"{asset_name}.pcp3stream.json"
        self.document.metadata["streaming_udata_file"] = f"{asset_name}.pcp3stream.udata"
        self.document.metadata["streaming_chunks_file"] = f"{asset_name}.pcp3chunks.json"
        super().export_to_database()
        asset_dir = self.root_path / "content" / "pcp3_assets" / self.document.environment_type / asset_name
        if not asset_dir.exists():
            return
        try:
            paths = write_streaming_runtime_files(asset_dir, self.document)
            self.update_status("Exported PCP3 asset with Streaming/LOD sidecars")
            if ensure_streaming_runtime(self.document)["enabled"]:
                messagebox.showinfo(
                    "Streaming Runtime exported",
                    f"Created:\n{paths['json'].name}\n{paths['udata'].name}\n{paths['chunks'].name}",
                    parent=self,
                )
        except Exception as exc:
            messagebox.showwarning("Streaming Runtime warning", str(exc), parent=self)

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        ensure_streaming_runtime(self.document)
        if self.streaming_panel is not None:
            self.refresh_streaming_panel()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if self.streaming_panel is not None:
            self.refresh_streaming_panel()

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
            text.insert("end", "\n\nBRANCH 11 — STREAMING, LOD & LARGE-ASSET RUNTIME\nUse Authoring → Streaming to compile deterministic spatial chunk manifests, distance LOD tiers, semantic priority reserves, per-asset point limits, upload budgets, and adaptive hardware presets. The verified 8M Intel/Mesa environment baseline remains unchanged; Streaming bounds authored PCP3 assets inside that larger world budget.\n\nDOCUMENTATION PHASE NOTE\nThe future Authoring Help Guide must include Streaming profiles, LOD distances/ratios, chunk audits, semantic preservation, dry-run files, live telemetry, pop-in troubleshooting, and the distinction between bounded loading intent and currently active deterministic LOD execution.\n")
            text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
