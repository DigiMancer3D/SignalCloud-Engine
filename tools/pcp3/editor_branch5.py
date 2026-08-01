from __future__ import annotations

import json
import subprocess
import time
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from tools.pcp3 import editor_branch4 as branch4
from tools.pcp3.advanced_authoring import ensure_authoring, sample_clip
from tools.pcp3.io import save_project, slugify, write_cloud
from tools.pcp3.runtime_bridge import (
    RuntimePreviewOptions,
    clip_by_name,
    compile_preview_document,
    events_crossed,
    runtime_summary,
    write_runtime_preview_bundle,
    write_runtime_report,
)

PLAYBACK_REFRESH_MS = 33
NATIVE_PREVIEW_WRITE_INTERVAL = 0.25


class PCP3Editor(branch4.PCP3Editor):
    def __init__(self, root_path: Path) -> None:
        self.playback_running = False
        self.playback_after: str | None = None
        self.playback_last_tick = 0.0
        self.playback_last_value = 0.0
        self.playback_last_native_write = 0.0
        self.runtime_preview_process: subprocess.Popen[Any] | None = None
        self.runtime_preview_initialized = False
        self.playback_clip: tk.StringVar | None = None
        self.playback_time: tk.DoubleVar | None = None
        self.playback_speed: tk.DoubleVar | None = None
        self.playback_loop: tk.BooleanVar | None = None
        self.playback_status: tk.StringVar | None = None
        self.playback_sample: tk.StringVar | None = None
        self.playback_option_vars: dict[str, tk.BooleanVar] = {}
        self.playback_geometry_budget: tk.IntVar | None = None
        self.playback_event_log: tk.Text | None = None
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 5 Runtime Preview & Playback Lab")
        self.document.metadata["editor_branch"] = "ISL_plus_branch5"
        self.document.metadata["documentation_phase_authoring_help_guide"] = True
        self.refresh_playback_panel()
        self.update_status("Branch 5 active · safe authoring playback · runtime preview bridge · event telemetry")

    # ---------- menus / toolbar ----------
    def _build_menu(self) -> None:
        super()._build_menu()
        try:
            menu = self.nametowidget(self.cget("menu"))
            end = menu.index("end")
            if end is None:
                return
            for index in range(end + 1):
                try:
                    label = menu.entrycget(index, "label")
                except tk.TclError:
                    continue
                if label == "Help":
                    help_menu = self.nametowidget(menu.entrycget(index, "menu"))
                    help_menu.add_separator()
                    help_menu.add_command(
                        label="Authoring Help Guide — Documentation Phase",
                        command=self.show_authoring_help_plan,
                    )
                    break
        except tk.TclError:
            pass

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
        button("Runtime Playback", self.show_runtime_playback)
        button("Tools Help", self.show_tools_help)

    # ---------- playback panel ----------
    def _insert_authoring_tab(self) -> None:
        super()._insert_authoring_tab()
        self._build_playback_panel(self.authoring_notebook)

    def _build_playback_panel(self, notebook: ttk.Notebook) -> None:
        panel = ttk.Frame(notebook, padding=4)
        notebook.add(panel, text="Playback")
        self.playback_panel = panel
        self.playback_clip = tk.StringVar(master=self, value="Default")
        self.playback_time = tk.DoubleVar(master=self, value=0.0)
        self.playback_speed = tk.DoubleVar(master=self, value=1.0)
        self.playback_loop = tk.BooleanVar(master=self, value=True)
        self.playback_status = tk.StringVar(master=self, value="Playback ready")
        self.playback_sample = tk.StringVar(master=self, value="Root sample pending")
        self.playback_geometry_budget = tk.IntVar(master=self, value=250_000)
        self.playback_option_vars = {
            key: tk.BooleanVar(master=self, value=True)
            for key in ("geometry", "rig", "anchors", "triggers", "placements", "flow", "raid", "theme", "event_markers")
        }

        top = ttk.Frame(panel)
        top.pack(fill="x")
        ttk.Label(top, text="Clip").pack(side="left")
        self.playback_clip_combo = ttk.Combobox(top, textvariable=self.playback_clip, state="readonly", width=18)
        self.playback_clip_combo.pack(side="left", fill="x", expand=True, padx=4)
        self.playback_clip_combo.bind("<<ComboboxSelected>>", lambda _event: self.playback_clip_changed())
        ttk.Label(top, text="Speed").pack(side="left")
        ttk.Combobox(top, textvariable=self.playback_speed, values=(0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0),
                     state="readonly", width=6).pack(side="left", padx=4)
        ttk.Checkbutton(top, text="Loop", variable=self.playback_loop).pack(side="left")
        ttk.Label(top, text="Budget").pack(side="left", padx=(5, 0))
        budget_box = ttk.Combobox(top, textvariable=self.playback_geometry_budget, values=(50_000, 100_000, 250_000, 500_000), state="readonly", width=8)
        budget_box.pack(side="left", padx=3)
        budget_box.bind("<<ComboboxSelected>>", lambda _event: self.schedule_runtime_preview_refresh())

        controls = ttk.Frame(panel)
        controls.pack(fill="x", pady=(5, 3))
        ttk.Button(controls, text="▶ Play", command=self.play_runtime).pack(side="left", fill="x", expand=True)
        ttk.Button(controls, text="Ⅱ Pause", command=self.pause_runtime).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(controls, text="■ Stop", command=self.stop_runtime).pack(side="left", fill="x", expand=True)

        self.playback_scrubber = ttk.Scale(panel, from_=0.0, to=1.0, variable=self.playback_time,
                                           command=lambda _value: self.playback_scrubbed())
        self.playback_scrubber.pack(fill="x", pady=3)
        ttk.Label(panel, textvariable=self.playback_sample, wraplength=300).pack(fill="x")
        ttk.Label(panel, textvariable=self.playback_status, wraplength=300, font=("Sans", 9, "bold")).pack(fill="x", pady=(2, 4))

        options = ttk.LabelFrame(panel, text="Preview systems", padding=3)
        options.pack(fill="x")
        labels = {
            "geometry": "Geometry", "rig": "Rig", "anchors": "Anchors", "triggers": "Triggers",
            "placements": "Placements", "flow": "Flow", "raid": "Raid", "theme": "Theme", "event_markers": "Event marker",
        }
        for index, key in enumerate(labels):
            ttk.Checkbutton(options, text=labels[key], variable=self.playback_option_vars[key],
                            command=self.schedule_runtime_preview_refresh).grid(row=index // 3, column=index % 3, sticky="w", padx=2)

        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="Open Native Runtime Preview", command=self.launch_runtime_preview).pack(fill="x")
        holder = ttk.Frame(actions)
        holder.pack(fill="x", pady=(2, 0))
        ttk.Button(holder, text="Refresh", command=lambda: self.refresh_runtime_preview(force=True)).pack(side="left", fill="x", expand=True)
        ttk.Button(holder, text="Bake Snapshot Copy", command=self.bake_runtime_snapshot).pack(side="left", fill="x", expand=True, padx=(2, 0))

        ttk.Label(panel, text="Timed events").pack(anchor="w")
        event_frame = ttk.Frame(panel)
        event_frame.pack(fill="both", expand=True)
        self.playback_event_log = tk.Text(event_frame, height=6, wrap="word", state="disabled")
        event_scroll = ttk.Scrollbar(event_frame, orient="vertical", command=self.playback_event_log.yview)
        self.playback_event_log.configure(yscrollcommand=event_scroll.set)
        self.playback_event_log.pack(side="left", fill="both", expand=True)
        event_scroll.pack(side="right", fill="y")

    def playback_options(self) -> RuntimePreviewOptions:
        values = {key: bool(variable.get()) for key, variable in self.playback_option_vars.items()}
        values["geometry_point_budget"] = int(self.playback_geometry_budget.get() if self.playback_geometry_budget is not None else 250_000)
        return RuntimePreviewOptions(**values)

    def current_playback_clip(self) -> dict[str, Any]:
        authoring = ensure_authoring(self.document)
        return clip_by_name(authoring, self.playback_clip.get() if self.playback_clip is not None else "Default")

    def playback_duration(self) -> float:
        try:
            return max(0.001, float(self.current_playback_clip().get("duration", 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def refresh_playback_panel(self) -> None:
        if self.playback_clip is None:
            return
        clips = [str(item.get("name", "Default")) for item in ensure_authoring(self.document).get("timelines", []) if isinstance(item, dict)]
        if not clips:
            clips = ["Default"]
        self.playback_clip_combo.configure(values=clips)
        if self.playback_clip.get() not in clips:
            self.playback_clip.set(clips[0])
        duration = self.playback_duration()
        self.playback_scrubber.configure(to=duration)
        if self.playback_time.get() > duration:
            self.playback_time.set(duration)
        summary = runtime_summary(self.document, self.playback_clip.get())
        self.playback_status.set(
            f"{summary['keyframes']} keyframes · {summary['events']} events · {summary['triggers']} triggers · "
            f"{summary['placements']} placements · {summary['flow_nodes']} flow nodes"
        )
        self.update_playback_sample()

    def playback_clip_changed(self) -> None:
        self.pause_runtime()
        self.playback_time.set(0.0)
        self.playback_last_value = 0.0
        self.refresh_playback_panel()
        self.schedule_runtime_preview_refresh()

    def update_playback_sample(self) -> None:
        clip = self.current_playback_clip()
        time_value = self.playback_time.get() if self.playback_time is not None else 0.0
        sample = sample_clip(clip, time_value, "root")
        pos = sample["position"]; rot = sample["rotation_degrees"]; scale = sample["scale"]
        self.playback_sample.set(
            f"t {time_value:.3f}/{self.playback_duration():.3f}s · root P {pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f} · "
            f"R {rot[0]:.1f},{rot[1]:.1f},{rot[2]:.1f} · S {scale[0]:.2f},{scale[1]:.2f},{scale[2]:.2f}"
        )

    def play_runtime(self) -> None:
        if self.playback_running:
            return
        self.playback_running = True
        self.playback_last_tick = time.monotonic()
        self.playback_last_value = self.playback_time.get()
        self._runtime_tick()
        self.playback_status.set("Playback running · source document remains unchanged")

    def pause_runtime(self) -> None:
        self.playback_running = False
        if self.playback_after is not None:
            try:
                self.after_cancel(self.playback_after)
            except tk.TclError:
                pass
            self.playback_after = None
        if self.playback_status is not None:
            self.playback_status.set("Playback paused")

    def stop_runtime(self) -> None:
        self.pause_runtime()
        self.playback_time.set(0.0)
        self.playback_last_value = 0.0
        self.update_playback_sample()
        self.refresh_runtime_preview(force=True)
        self.playback_status.set("Playback stopped at 0.0 seconds")

    def _runtime_tick(self) -> None:
        if not self.playback_running or not self.winfo_exists():
            return
        now = time.monotonic()
        delta = min(0.25, max(0.0, now - self.playback_last_tick))
        self.playback_last_tick = now
        previous = self.playback_time.get()
        current = previous + delta * max(0.01, self.playback_speed.get())
        duration = self.playback_duration()
        looped = False
        if current > duration:
            if self.playback_loop.get():
                current %= duration
                looped = True
            else:
                current = duration
                self.playback_running = False
        self.playback_time.set(current)
        clip = self.current_playback_clip()
        for event in events_crossed(clip, previous, current, looped):
            self.log_runtime_event(event)
        self.playback_last_value = current
        self.update_playback_sample()
        if now - self.playback_last_native_write >= NATIVE_PREVIEW_WRITE_INTERVAL:
            self.playback_last_native_write = now
            self.refresh_runtime_preview(force=False)
        if self.playback_running:
            self.playback_after = self.after(PLAYBACK_REFRESH_MS, self._runtime_tick)
        else:
            self.playback_status.set("Playback reached the clip end")

    def playback_scrubbed(self) -> None:
        self.update_playback_sample()
        self.schedule_runtime_preview_refresh()

    def log_runtime_event(self, event: dict[str, Any]) -> None:
        if self.playback_event_log is None:
            return
        line = f"{float(event.get('time', 0.0)):6.3f}s · {event.get('type', 'event')} · {event.get('action', 'none')}"
        payload = event.get("payload")
        if payload not in (None, {}, ""):
            line += " · " + json.dumps(payload, sort_keys=True)
        self.playback_event_log.configure(state="normal")
        self.playback_event_log.insert("end", line + "\n")
        self.playback_event_log.see("end")
        self.playback_event_log.configure(state="disabled")
        self.update_status("Runtime event: " + line)

    def schedule_runtime_preview_refresh(self) -> None:
        self.after(120, lambda: self.refresh_runtime_preview(force=False))

    def runtime_preview_folder(self) -> Path:
        return self.root_path / "user_data" / "pcp3" / "runtime_preview" / slugify(self.document.asset_id)

    def refresh_runtime_preview(self, *, force: bool = False) -> Path | None:
        process_live = self.runtime_preview_process is not None and self.runtime_preview_process.poll() is None
        if not force and not process_live:
            return None
        try:
            folder = self.runtime_preview_folder()
            cloud = folder / "runtime_preview.pcp3cloud"
            if not self.runtime_preview_initialized or not cloud.exists():
                paths = write_runtime_preview_bundle(
                    self.root_path, self.document, self.playback_clip.get(), self.playback_time.get(), self.playback_options()
                )
                self.runtime_preview_initialized = True
                cloud = paths["cloud"]
            else:
                preview = compile_preview_document(
                    self.document, self.playback_clip.get(), self.playback_time.get(), self.playback_options()
                )
                write_cloud(cloud, preview.points)
                write_runtime_report(folder / "runtime_preview.pcp3runtime.json", self.document,
                                     self.playback_clip.get(), self.playback_options())
            self.playback_status.set(f"Runtime preview updated · {self.playback_time.get():.3f}s · source unchanged")
            return cloud
        except Exception as exc:
            self.playback_status.set(f"Runtime preview failed: {exc}")
            if force:
                messagebox.showerror("Runtime preview failed", str(exc), parent=self)
            return None

    def launch_runtime_preview(self) -> None:
        binary = self.root_path / "build" / "almond_signal_pcp_preview"
        if not binary.exists():
            messagebox.showerror("Preview not built", "Run ./scripts/setup_dev_environment.sh first.", parent=self)
            return
        cloud = self.refresh_runtime_preview(force=True)
        if cloud is None:
            return
        if self.runtime_preview_process is not None and self.runtime_preview_process.poll() is None:
            self.update_status("Runtime preview is already running")
            return
        commands = self.runtime_preview_folder() / "runtime_preview_commands.jsonl"
        commands.write_text("", encoding="utf-8")
        try:
            self.runtime_preview_process = subprocess.Popen(
                [str(binary), f"--root={self.root_path}", f"--asset={cloud}", f"--brush-commands={commands}", "--live"],
                cwd=self.root_path,
            )
            self.update_status("Native runtime preview launched · playback changes stream into the preview")
        except OSError as exc:
            messagebox.showerror("Runtime preview launch failed", str(exc), parent=self)

    def bake_runtime_snapshot(self) -> None:
        try:
            preview = compile_preview_document(
                self.document, self.playback_clip.get(), self.playback_time.get(), self.playback_options()
            )
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            folder = self.root_path / "user_data" / "pcp3" / "runtime_snapshots"
            project = folder / f"{slugify(self.document.asset_id)}_{timestamp}.pcp3"
            preview.runtime.update({"enabled": False, "auto_preview_in_game": False})
            save_project(preview, project, editor_name="PCP3 Runtime Snapshot")
            messagebox.showinfo("Snapshot saved", f"Non-destructive runtime snapshot:\n{project}", parent=self)
        except Exception as exc:
            messagebox.showerror("Snapshot failed", str(exc), parent=self)

    def show_runtime_playback(self) -> None:
        self.right_notebook.select(self.authoring_tab)
        self.authoring_notebook.select(self.playback_panel)
        self.refresh_playback_panel()

    # ---------- export / documentation ----------
    def export_to_database(self) -> None:
        self.document.metadata["runtime_sidecar_file"] = f"{slugify(self.document.asset_id)}.pcp3runtime.json"
        super().export_to_database()
        asset_dir = self.root_path / "content" / "pcp3_assets" / self.document.environment_type / slugify(self.document.asset_id)
        if asset_dir.exists():
            try:
                write_runtime_report(
                    asset_dir / f"{slugify(self.document.asset_id)}.pcp3runtime.json",
                    self.document,
                    self.playback_clip.get() if self.playback_clip is not None else "Default",
                    self.playback_options(),
                )
                self.update_status("Exported PCP3 asset with mode, authoring, and runtime-preview sidecars")
            except Exception as exc:
                messagebox.showwarning("Runtime sidecar warning", str(exc), parent=self)

    def show_authoring_help_plan(self) -> None:
        messagebox.showinfo(
            "Authoring Help Guide — Documentation Phase",
            "Documentation milestone recorded:\n\n"
            "A dedicated Authoring Help Guide will be added to the Help dropdown during the documentation phase. "
            "It will cover Rig, Timeline, Gameplay, Placement, Flow/Theme, Runtime Playback, validation, exports, "
            "and the advanced 3D Brush Editor with worked examples.\n\n"
            "Branch 5 keeps this menu item visible so the milestone is not lost.",
            parent=self,
        )

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
        if text is None:
            return
        text.configure(state="normal")
        text.insert("end", "Branch 5 Runtime Playback\n", "heading")
        text.insert(
            "end",
            "Open Authoring → Playback to select a clip, scrub or play it, inspect root transforms, dispatch timed events "
            "to the event log, and stream a non-destructive preview into the native SignalCloud renderer. Overlay toggles "
            "control rig, anchors, trigger volumes, placement proxies, flow vectors, raid markers, theme colors, and the event marker.\n\n",
        )
        text.insert("end", "Documentation milestone\n", "heading")
        text.insert(
            "end",
            "The documentation phase must add a dedicated Authoring Help Guide to the Help dropdown with complete workflows and examples.\n\n",
        )
        text.configure(state="disabled")

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        if self.playback_clip is not None:
            self.runtime_preview_initialized = False
            self.refresh_playback_panel()

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if self.playback_clip is not None:
            self.runtime_preview_initialized = False
            self.refresh_playback_panel()

    def on_close(self) -> None:
        self.pause_runtime()
        if self.runtime_preview_process is not None and self.runtime_preview_process.poll() is None:
            self.runtime_preview_process.terminate()
        super().on_close()


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
