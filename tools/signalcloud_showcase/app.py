from __future__ import annotations

import json
import math
import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tools.asset_doctor.content_abi import scan_content

from .catalog import CatalogEntry, load_catalog_asset, scan_catalog
from .exporter import export_managed_asset
from .importers import import_source
from .model import PhysicsProfile, ShowcaseAsset, VisualizationProfile
from .preview import collision_wire_points, project_points, write_snapshot_ppm
from .simulation import LOOP_SECONDS, run_test, sample_test


class ShowcaseApp(tk.Tk):
    def __init__(self, root_path: Path, initial: Path | None = None) -> None:
        super().__init__()
        self.root_path = Path(root_path).resolve()
        self.current: ShowcaseAsset | None = None
        self.catalog_entries: dict[str, CatalogEntry] = {}
        self.preview_yaw = -38.0
        self.preview_pitch = 24.0
        self.preview_zoom = 0.84
        self.preview_drag: tuple[int, int] | None = None
        self._redraw_after: str | None = None
        self.active_test: str | None = None
        self.test_started = 0.0

        self.title("SignalCloud 3D Environment & Physics Showcase — A7a2r2")
        self.geometry("1380x860")
        self.minsize(1050, 680)

        self.source_var = tk.StringVar(value="Select a starter asset or import a source")
        self.asset_id = tk.StringVar(value="showcase_asset")
        self.shape = tk.StringVar(value="box")
        self.mass = tk.DoubleVar(value=4.0)
        self.friction = tk.DoubleVar(value=0.55)
        self.restitution = tk.DoubleVar(value=0.28)
        self.gravity = tk.DoubleVar(value=1.0)
        self.drag = tk.DoubleVar(value=0.04)
        self.break_threshold = tk.DoubleVar(value=18.0)
        self.collision_half_x = tk.DoubleVar(value=0.5)
        self.collision_half_y = tk.DoubleVar(value=0.5)
        self.collision_half_z = tk.DoubleVar(value=0.5)
        self.collision_radius = tk.DoubleVar(value=0.5)
        self.view_mode = tk.StringVar(value="source")
        self.lod_label = tk.StringVar(value="100%")
        self.point_scale = tk.DoubleVar(value=1.0)
        self.collision_outline = tk.BooleanVar(value=True)
        self.actor_preview = tk.BooleanVar(value=False)
        self.playbook_id = tk.StringVar(value="")
        self.test_loop = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="A7a2r2 live motion and portable export ready")
        self.bounds_text = tk.StringVar(value="Bounds: —")
        self._build()
        self.refresh_catalog()
        self._bind_live_updates()
        if initial is not None:
            self.after(50, lambda: self.import_path(initial))
        else:
            self.after(100, self.open_first_starter)

    def _build(self) -> None:
        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")
        title_row = ttk.Frame(top)
        title_row.pack(fill="x")
        ttk.Label(title_row, text="3D Environment & Physics Showcase", font=("Sans", 17, "bold")).pack(side="left")
        ttk.Label(title_row, text="A7a2r2 · shared motion transform · visible tests · portable reload", foreground="#44606a").pack(side="right")
        ttk.Label(top, text="Catalog/import → inspect points and bounds → tune physics → run bounded tests → native stage → managed export").pack(anchor="w")

        toolbar = ttk.Frame(top)
        toolbar.pack(fill="x", pady=(9, 0))
        for text, command in (
            ("Import Source…", self.choose_source),
            ("Refresh Catalog", self.refresh_catalog),
            ("Native Stage", self.launch_native),
            ("Snapshot PPM", self.export_snapshot),
            ("Export & Reload", self.export_current),
            ("Asset Doctor", self.asset_doctor),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 5))
        ttk.Label(toolbar, textvariable=self.status).pack(side="right")
        ttk.Label(top, textvariable=self.source_var).pack(anchor="w", pady=(7, 0))

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        catalog_panel = ttk.Frame(main, padding=(0, 8, 8, 0))
        preview_panel = ttk.Frame(main, padding=(0, 8, 8, 0))
        inspector_panel = ttk.Frame(main, padding=(0, 8, 0, 0))
        main.add(catalog_panel, weight=1)
        main.add(preview_panel, weight=3)
        main.add(inspector_panel, weight=2)
        self._build_catalog(catalog_panel)
        self._build_preview(preview_panel)
        self._build_inspector(inspector_panel)

    def _build_catalog(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Managed Showcase Catalog", font=("Sans", 11, "bold")).pack(anchor="w")
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self.catalog_tree = ttk.Treeview(frame, show="tree", selectmode="browse")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.catalog_tree.yview)
        self.catalog_tree.configure(yscrollcommand=scroll.set)
        self.catalog_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.catalog_tree.bind("<<TreeviewSelect>>", self._catalog_selected)
        self.catalog_tree.bind("<Double-1>", self._catalog_selected)
        ttk.Label(parent, text="Starter assets are original CC0 SignalCloud data. User exports stay self-contained.", wraplength=240, foreground="#52636a").pack(fill="x", pady=(8, 0))

    def _build_preview(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent)
        controls.pack(fill="x")
        ttk.Label(controls, text="Live Point Preview", font=("Sans", 11, "bold")).pack(side="left")
        ttk.Label(controls, text="View").pack(side="left", padx=(16, 4))
        ttk.Combobox(controls, textvariable=self.view_mode, values=("source", "density", "material", "light"), state="readonly", width=10).pack(side="left")
        ttk.Label(controls, text="LOD").pack(side="left", padx=(12, 4))
        ttk.Combobox(controls, textvariable=self.lod_label, values=("100%", "50%", "25%", "12.5%"), state="readonly", width=7).pack(side="left")
        ttk.Checkbutton(controls, text="Collision", variable=self.collision_outline).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(controls, text="Actor/Playbook", variable=self.actor_preview).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Stop Motion", command=self.stop_motion).pack(side="right", padx=(5, 0))
        ttk.Button(controls, text="Reset View", command=self.reset_preview).pack(side="right")

        self.preview = tk.Canvas(parent, background="#081018", highlightthickness=1, highlightbackground="#30434b")
        self.preview.pack(fill="both", expand=True, pady=(6, 0))
        self.preview.bind("<Configure>", lambda _event: self.schedule_redraw())
        self.preview.bind("<ButtonPress-1>", self._preview_press)
        self.preview.bind("<B1-Motion>", self._preview_drag)
        self.preview.bind("<ButtonRelease-1>", lambda _event: setattr(self, "preview_drag", None))
        self.preview.bind("<MouseWheel>", self._preview_wheel)
        self.preview.bind("<Button-4>", lambda _event: self._zoom_preview(1.12))
        self.preview.bind("<Button-5>", lambda _event: self._zoom_preview(0.89))
        footer = ttk.Frame(parent)
        footer.pack(fill="x", pady=(5, 0))
        ttk.Label(footer, textvariable=self.bounds_text).pack(side="left")
        ttk.Label(footer, text="Drag to orbit · wheel to zoom · native S saves a rendered PPM", foreground="#52636a").pack(side="right")

    def _build_inspector(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill="both", expand=True)
        inspector = ttk.Frame(notebook, padding=10)
        tests = ttk.Frame(notebook, padding=10)
        notebook.add(inspector, text="Inspector")
        notebook.add(tests, text="Tests / Evidence")

        identity = ttk.LabelFrame(inspector, text="Managed asset", padding=9)
        identity.pack(fill="x")
        ttk.Label(identity, text="Asset ID").grid(row=0, column=0, sticky="w")
        ttk.Entry(identity, textvariable=self.asset_id).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        identity.columnconfigure(1, weight=1)

        physics = ttk.LabelFrame(inspector, text="Physics profile", padding=9)
        physics.pack(fill="x", pady=(8, 0))
        fields = [
            ("Shape", self.shape, ("box", "sphere", "capsule", "hull", "compound"), 0.0),
            ("Mass", self.mass, None, 0.10),
            ("Friction", self.friction, None, 0.05),
            ("Restitution", self.restitution, None, 0.05),
            ("Gravity scale", self.gravity, None, 0.05),
            ("Drag", self.drag, None, 0.01),
            ("Break threshold", self.break_threshold, None, 1.0),
        ]
        for row, (label, variable, choices, increment) in enumerate(fields):
            ttk.Label(physics, text=label).grid(row=row, column=0, sticky="w", pady=2)
            if choices:
                widget = ttk.Combobox(physics, textvariable=variable, values=choices, state="readonly", width=15)
            else:
                widget = ttk.Spinbox(physics, textvariable=variable, from_=-100000, to=1000000, increment=increment, width=15)
            widget.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
        physics.columnconfigure(1, weight=1)

        collision = ttk.LabelFrame(inspector, text="Visible collision profile", padding=9)
        collision.pack(fill="x", pady=(8, 0))
        for row, (label, variable) in enumerate((
            ("Half X", self.collision_half_x),
            ("Half Y", self.collision_half_y),
            ("Half Z", self.collision_half_z),
            ("Radius", self.collision_radius),
        )):
            ttk.Label(collision, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Spinbox(collision, textvariable=variable, from_=0.02, to=2000, increment=0.05, width=15).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=2)
        ttk.Button(collision, text="Auto-fit to points", command=self.auto_fit_collision).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        collision.columnconfigure(1, weight=1)

        visual = ttk.LabelFrame(inspector, text="Native visual profile", padding=9)
        visual.pack(fill="x", pady=(8, 0))
        ttk.Label(visual, text="Point scale").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(visual, textvariable=self.point_scale, from_=0.25, to=4.0, increment=0.05, width=15).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(visual, text="Playbook ID").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(visual, textvariable=self.playbook_id).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(4, 0))
        visual.columnconfigure(1, weight=1)

        test_buttons = ttk.Frame(tests)
        test_buttons.pack(fill="x")
        for name in ("drop", "bounce", "slide", "throw", "break"):
            ttk.Button(test_buttons, text=f"Animate {name.title()}", command=lambda value=name: self.run_simulation(value)).pack(side="left", padx=(0, 4))
        ttk.Checkbutton(test_buttons, text="Loop", variable=self.test_loop, command=self.schedule_redraw).pack(side="right")
        self.output = tk.Text(tests, wrap="word", padx=10, pady=10, font=("Monospace", 10))
        self.output.pack(fill="both", expand=True, pady=(8, 0))
        self.write(
            "A7a2r2 evidence surface\n"
            "• collision extents are exported and used by native floor contact\n"
            "• LOD is deterministic and bounded\n"
            "• material/light views are data-only visual probes\n"
            "• actor preview is a bounded playbook motion envelope\n"
            "• snapshots export as portable PPM without third-party libraries\n"
        )

    def _bind_live_updates(self) -> None:
        variables = (
            self.view_mode, self.lod_label, self.point_scale, self.collision_outline,
            self.actor_preview, self.shape, self.collision_half_x, self.collision_half_y,
            self.collision_half_z, self.collision_radius,
        )
        for variable in variables:
            variable.trace_add("write", lambda *_args: self.schedule_redraw())

    def write(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def refresh_catalog(self) -> None:
        selected_asset = self.current.document.asset_id if self.current is not None else None
        self.catalog_tree.delete(*self.catalog_tree.get_children())
        self.catalog_entries.clear()
        roots = {
            ("starter", "architecture"): self.catalog_tree.insert("", "end", text="Starter Pack A — Architecture", open=True),
            ("starter", "systems"): self.catalog_tree.insert("", "end", text="Starter Pack B — Systems", open=True),
            ("user", "user"): self.catalog_tree.insert("", "end", text="User Managed Assets", open=True),
        }
        fallback_roots: dict[tuple[str, str], str] = {}
        for entry in scan_catalog(self.root_path):
            parent = roots.get((entry.pack, entry.category))
            if parent is None:
                key = (entry.pack, entry.category)
                parent = fallback_roots.get(key)
                if parent is None:
                    parent = self.catalog_tree.insert("", "end", text=f"{entry.pack.title()} — {entry.category.title()}", open=True)
                    fallback_roots[key] = parent
            iid = f"asset::{entry.pack}::{entry.asset_id}"
            self.catalog_entries[iid] = entry
            self.catalog_tree.insert(parent, "end", iid=iid, text=f"{entry.display_name}  [{entry.point_count:,}]")
            if entry.asset_id == selected_asset:
                self.catalog_tree.selection_set(iid)
        self.status.set(f"Catalog: {len(self.catalog_entries)} managed Showcase assets")

    def open_first_starter(self) -> None:
        for iid, entry in self.catalog_entries.items():
            if entry.pack == "starter":
                self.catalog_tree.selection_set(iid)
                self.catalog_tree.see(iid)
                self.open_catalog_entry(entry)
                break

    def _catalog_selected(self, _event: object = None) -> None:
        selection = self.catalog_tree.selection()
        if not selection:
            return
        entry = self.catalog_entries.get(selection[0])
        if entry is not None:
            self.open_catalog_entry(entry)

    def open_catalog_entry(self, entry: CatalogEntry) -> None:
        try:
            self.current = load_catalog_asset(entry)
            self._load_variables_from_current()
            self.source_var.set(f"{entry.pack}/{entry.category}: {entry.display_name} · {entry.point_count:,} points · {entry.physics_shape}")
            self.status.set("Managed asset loaded")
            self.write(f"\nCATALOG LOAD: {entry.directory.relative_to(self.root_path)}\n")
            self.schedule_redraw()
        except Exception as exc:
            messagebox.showerror("Showcase catalog load failed", str(exc))

    def choose_source(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import into SignalCloud Showcase",
            filetypes=[
                ("Showcase sources", "*.pcp3 *.pcp3cloud *.ply *.obj *.png *.bmp *.udata *.script"),
                ("All files", "*"),
            ],
        )
        if selected:
            self.import_path(Path(selected))

    def import_path(self, path: Path) -> None:
        try:
            self.current = import_source(path, self.profile())
            self._load_variables_from_current()
            self.source_var.set(f"{self.current.source_kind}: {self.current.source_path.name} · {len(self.current.document.points):,} points")
            self.status.set("Import validated and collision auto-fitted")
            self.write("\nIMPORT PASS\n" + json.dumps(self.current.provenance, indent=2, sort_keys=True) + "\n")
            for warning in self.current.warnings:
                self.write(f"WARNING: {warning}\n")
            self.schedule_redraw()
        except Exception as exc:
            self.status.set("Import failed")
            messagebox.showerror("Showcase import failed", str(exc))

    def _load_variables_from_current(self) -> None:
        if self.current is None:
            return
        p = self.current.physics.normalize()
        v = self.current.visualization.normalize()
        self.asset_id.set(self.current.document.asset_id)
        self.shape.set(p.shape)
        self.mass.set(p.mass)
        self.friction.set(p.friction)
        self.restitution.set(p.restitution)
        self.gravity.set(p.gravity_scale)
        self.drag.set(p.drag)
        self.break_threshold.set(p.break_threshold)
        self.collision_half_x.set(p.collision_half_x)
        self.collision_half_y.set(p.collision_half_y)
        self.collision_half_z.set(p.collision_half_z)
        self.collision_radius.set(p.collision_radius)
        self.view_mode.set(v.view_mode)
        self.lod_label.set({1.0: "100%", 0.5: "50%", 0.25: "25%", 0.125: "12.5%"}.get(v.lod_fraction, "100%"))
        self.point_scale.set(v.point_scale)
        self.collision_outline.set(v.collision_outline)
        self.actor_preview.set(v.actor_preview)
        self.playbook_id.set(v.playbook_id)
        self._update_bounds_text()

    def profile(self) -> PhysicsProfile:
        return PhysicsProfile(
            profile_id=f"showcase.{self.asset_id.get().strip() or 'asset'}",
            shape=self.shape.get(), mass=self.mass.get(), friction=self.friction.get(),
            restitution=self.restitution.get(), gravity_scale=self.gravity.get(), drag=self.drag.get(),
            break_threshold=self.break_threshold.get(),
            collision_half_x=self.collision_half_x.get(), collision_half_y=self.collision_half_y.get(),
            collision_half_z=self.collision_half_z.get(), collision_radius=self.collision_radius.get(),
        ).normalize()

    def visualization(self) -> VisualizationProfile:
        lod = {"100%": 1.0, "50%": 0.5, "25%": 0.25, "12.5%": 0.125}.get(self.lod_label.get(), 1.0)
        return VisualizationProfile(
            view_mode=self.view_mode.get(), lod_fraction=lod, point_scale=self.point_scale.get(),
            collision_outline=self.collision_outline.get(), actor_preview=self.actor_preview.get(),
            playbook_id=self.playbook_id.get(),
        ).normalize()

    def auto_fit_collision(self) -> None:
        if self.current is None:
            return
        fitted = self.profile().auto_fit(self.current.document.points)
        self.collision_half_x.set(fitted.collision_half_x)
        self.collision_half_y.set(fitted.collision_half_y)
        self.collision_half_z.set(fitted.collision_half_z)
        self.collision_radius.set(fitted.collision_radius)
        self._update_bounds_text()
        self.status.set("Collision profile fitted to point bounds")

    def _update_bounds_text(self) -> None:
        self.bounds_text.set(
            f"Collision: {self.shape.get()} · half {self.collision_half_x.get():.2f}, "
            f"{self.collision_half_y.get():.2f}, {self.collision_half_z.get():.2f} · r {self.collision_radius.get():.2f}"
        )

    def run_simulation(self, name: str) -> None:
        try:
            result = run_test(self.profile(), name)
        except Exception as exc:
            messagebox.showerror("Physics test failed", str(exc))
            return
        self.active_test = name
        self.test_started = time.monotonic()
        self.write("\n" + json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n")
        self.status.set(f"Animating {name}: {result.signature}")
        self.schedule_redraw()

    def stop_motion(self) -> None:
        self.active_test = None
        self.test_started = 0.0
        self.status.set("Motion stopped; object returned to inspection pose")
        self.schedule_redraw()

    def _motion(self):
        if self.active_test is None:
            return None, 0.0
        elapsed = max(0.0, time.monotonic() - self.test_started)
        duration = LOOP_SECONDS.get(self.active_test, 5.0)
        if not self.test_loop.get() and elapsed >= duration:
            elapsed = duration
        return sample_test(self.profile(), self.active_test, elapsed, loop=self.test_loop.get()), elapsed

    def export_current(self) -> None:
        if self.current is None:
            messagebox.showinfo("Nothing loaded", "Select a starter asset or import a source first.")
            return
        try:
            self.current.document.asset_id = self.asset_id.get().strip() or self.current.document.asset_id
            self.current.physics = self.profile().auto_fit(self.current.document.points)
            self.current.visualization = self.visualization()
            destination = export_managed_asset(self.current, self.root_path, pack="user")
            report = scan_content(self.root_path / "content")
            self.write(f"\nEXPORTED: {destination}\nAsset Doctor: {report.valid_count} valid, {report.error_count} errors, {report.warning_count} warnings\n")
            self.status.set("Managed export complete; reloading self-contained copy")
            self.refresh_catalog()
            for iid, entry in self.catalog_entries.items():
                if entry.pack == "user" and entry.asset_id == destination.name:
                    self.catalog_tree.selection_set(iid)
                    self.catalog_tree.see(iid)
                    self.open_catalog_entry(entry)
                    break
            if report.error_count:
                messagebox.showwarning("Exported with validation errors", f"Review Asset Doctor. Errors: {report.error_count}")
        except Exception as exc:
            messagebox.showerror("Showcase export failed", str(exc))

    def asset_doctor(self) -> None:
        try:
            report = scan_content(self.root_path / "content")
            self.write(f"\nAsset Doctor: {len(report.records)} assets | {report.valid_count} valid | {report.error_count} errors | {report.warning_count} warnings\n")
            self.status.set("Asset Doctor complete")
        except Exception as exc:
            messagebox.showerror("Asset Doctor failed", str(exc))

    def _prepare_native_files(self) -> tuple[Path, Path, Path]:
        if self.current is None:
            raise ValueError("Select a starter asset or import a source first.")
        asset_id = self.asset_id.get().strip() or self.current.document.asset_id
        directory = self.root_path / "content" / "user" / "showcase" / asset_id
        if self.current.source_kind.startswith("managed-starter"):
            directory = self.root_path / "content" / "starter" / "showcase" / self.current.document.asset_id
        elif self.current.source_kind.startswith("managed-user"):
            directory = self.root_path / "content" / "user" / "showcase" / self.current.document.asset_id
        cloud = directory / f"{directory.name}.pcp3cloud"
        physics = directory / f"{directory.name}.scphysics"
        visual = directory / f"{directory.name}.scshowcase"
        if not cloud.exists() or not physics.exists():
            self.current.document.asset_id = asset_id
            self.current.physics = self.profile().auto_fit(self.current.document.points)
            self.current.visualization = self.visualization()
            directory = export_managed_asset(self.current, self.root_path, pack="user")
            cloud = directory / f"{asset_id}.pcp3cloud"
            physics = directory / f"{asset_id}.scphysics"
            visual = directory / f"{asset_id}.scshowcase"
        return cloud, physics, visual

    def launch_native(self) -> None:
        try:
            cloud, physics, visual = self._prepare_native_files()
            script = self.root_path / "scripts" / "launch_showcase_native.sh"
            subprocess.Popen([
                str(script), str(cloud), str(physics), self.active_test or "drop",
                f"--visualization={visual}",
                f"--view={self.view_mode.get()}",
                f"--lod={self.visualization().lod_fraction}",
                f"--point-scale={self.point_scale.get()}",
                f"--collision={1 if self.collision_outline.get() else 0}",
                f"--actor={1 if self.actor_preview.get() else 0}",
                f"--playbook={self.playbook_id.get()}",
                f"--snapshot-dir={self.root_path / 'user_data/showcase_snapshots'}",
            ], cwd=self.root_path)
            self.status.set("Native A7a2r2 stage opened; tests loop with stage-fixed camera")
        except Exception as exc:
            messagebox.showerror("Native Showcase launch failed", str(exc))

    def export_snapshot(self) -> None:
        if self.current is None:
            messagebox.showinfo("Nothing loaded", "Select a starter asset or import a source first.")
            return
        selected = filedialog.asksaveasfilename(
            title="Export Showcase snapshot",
            defaultextension=".ppm",
            initialdir=self.root_path / "user_data" / "showcase_snapshots",
            initialfile=f"{self.asset_id.get().strip() or 'showcase'}_preview.ppm",
            filetypes=[("Portable pixmap", "*.ppm")],
        )
        if not selected:
            return
        try:
            motion, elapsed = self._motion()
            translation = (motion.x, motion.y, motion.z) if motion is not None else (0.0, 0.0, 0.0)
            yaw = motion.yaw if motion is not None else 0.0
            scene_extent = self._scene_extent() if motion is not None else None
            target = write_snapshot_ppm(
                Path(selected), self.current.document.points, self.profile(), self.visualization(),
                translation=translation, object_yaw=yaw, time_seconds=elapsed,
                scene_center=(0.0, 2.2, 0.0) if motion is not None else None, scene_extent=scene_extent,
            )
            self.write(f"\nSNAPSHOT: {target}\n")
            self.status.set("Portable PPM snapshot exported")
        except Exception as exc:
            messagebox.showerror("Snapshot export failed", str(exc))

    def _scene_extent(self) -> float:
        if self.current is None or not self.current.document.points:
            return 12.0
        points = self.current.document.points
        xs = [float(point.x) for point in points]
        ys = [float(point.y) for point in points]
        zs = [float(point.z) for point in points]
        object_extent = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 0.1)
        return max(12.0, object_extent * 2.4)

    def schedule_redraw(self) -> None:
        self._update_bounds_text()
        if self._redraw_after is not None:
            self.after_cancel(self._redraw_after)
        self._redraw_after = self.after(35, self.redraw_preview)

    def redraw_preview(self) -> None:
        self._redraw_after = None
        canvas = self.preview
        canvas.delete("all")
        width = max(10, canvas.winfo_width())
        height = max(10, canvas.winfo_height())
        for step in range(1, 10):
            x = width * step / 10
            y = height * step / 10
            canvas.create_line(x, 0, x, height, fill="#0e2029")
            canvas.create_line(0, y, width, y, fill="#0e2029")
        if self.current is None:
            canvas.create_text(width / 2, height / 2, text="Select or import an asset", fill="#85a8b4", font=("Sans", 16, "bold"))
            return

        motion, elapsed = self._motion()
        translation = (motion.x, motion.y, motion.z) if motion is not None else (0.0, 0.0, 0.0)
        object_yaw = motion.yaw if motion is not None else 0.0
        fixed_scene = motion is not None
        scene_center = (0.0, 2.2, 0.0) if fixed_scene else None
        scene_extent = self._scene_extent() if fixed_scene else None
        visual = self.visualization()
        projected = project_points(
            self.current.document.points, width, height, visual,
            yaw_degrees=self.preview_yaw, pitch_degrees=self.preview_pitch, zoom=self.preview_zoom,
            translation=translation, object_yaw=object_yaw, time_seconds=elapsed,
            scene_center=scene_center, scene_extent=scene_extent,
        )
        for point in projected:
            radius = point.radius
            canvas.create_oval(point.x - radius, point.y - radius, point.x + radius, point.y + radius,
                               fill=point.color, outline="")

        if self.collision_outline.get():
            collision_view = self.visualization()
            collision_view.view_mode = "source"
            collision_view.lod_fraction = 1.0
            collision = project_points(
                collision_wire_points(self.profile(), translation=translation, object_yaw=object_yaw),
                width, height, collision_view,
                yaw_degrees=self.preview_yaw, pitch_degrees=self.preview_pitch, zoom=self.preview_zoom,
                scene_center=scene_center, scene_extent=scene_extent, maximum_points=20_000,
            )
            for point in collision:
                radius = max(1.0, point.radius * 0.75)
                canvas.create_oval(point.x - radius, point.y - radius, point.x + radius, point.y + radius,
                                   fill="#42f0d4", outline="")

        if motion is not None:
            label = f"{self.active_test.upper()}  t={elapsed % LOOP_SECONDS.get(self.active_test, 5.0):.2f}s  " \
                    f"pos {motion.x:.2f},{motion.y:.2f},{motion.z:.2f}  yaw {math.degrees(motion.yaw):.0f}°"
            canvas.create_text(width / 2, height - 18, anchor="s", text=label,
                               fill="#ffc45c", font=("Monospace", 9, "bold"))
        canvas.create_text(12, 12, anchor="nw",
                           text=f"{self.current.document.display_name}\n{len(self.current.document.points):,} source points · {len(projected):,} preview points\n{self.view_mode.get()} · LOD {self.lod_label.get()} · shape {self.shape.get()}",
                           fill="#d9f4f5", font=("Monospace", 10, "bold"))
        canvas.create_text(width - 12, height - 12, anchor="se",
                           text="COLLISION SHARED" if self.collision_outline.get() else "COLLISION HIDDEN",
                           fill="#42f0d4" if self.collision_outline.get() else "#6a7780", font=("Monospace", 9, "bold"))

        motion_running = False
        if self.active_test is not None:
            duration = LOOP_SECONDS.get(self.active_test, 5.0)
            motion_running = self.test_loop.get() or elapsed < duration
        if motion_running or self.actor_preview.get():
            self._redraw_after = self.after(33, self.redraw_preview)

    def _preview_press(self, event: tk.Event) -> None:
        self.preview_drag = (event.x, event.y)

    def _preview_drag(self, event: tk.Event) -> None:
        if self.preview_drag is None:
            return
        previous_x, previous_y = self.preview_drag
        self.preview_yaw += (event.x - previous_x) * 0.45
        self.preview_pitch = max(-88.0, min(88.0, self.preview_pitch - (event.y - previous_y) * 0.38))
        self.preview_drag = (event.x, event.y)
        self.schedule_redraw()

    def _preview_wheel(self, event: tk.Event) -> None:
        self._zoom_preview(1.12 if event.delta > 0 else 0.89)

    def _zoom_preview(self, factor: float) -> None:
        self.preview_zoom = max(0.22, min(3.5, self.preview_zoom * factor))
        self.schedule_redraw()

    def reset_preview(self) -> None:
        self.preview_yaw = -38.0
        self.preview_pitch = 24.0
        self.preview_zoom = 0.84
        self.status.set("Preview camera reset")
        self.schedule_redraw()


def main(root_path: Path | None = None, argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SignalCloud 3D Environment & Physics Showcase")
    parser.add_argument("--root", type=Path, default=root_path or Path(__file__).resolve().parents[2])
    parser.add_argument("source", nargs="?", type=Path)
    args = parser.parse_args(argv)
    ShowcaseApp(args.root, args.source).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
