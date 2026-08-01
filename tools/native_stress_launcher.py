#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

try:
    from .machine_profile_manager import export_privacy_bundle, status_text
    from .native_stress_hud import NativeStressHud
    from .native_stress_watchdog import (
        CLEAN_REQUEST, HARD_REQUEST, GLOBAL_STATE, recover_orphaned_sessions,
    )
except ImportError:  # Direct script launch from tools/.
    from machine_profile_manager import export_privacy_bundle, status_text
    from native_stress_hud import NativeStressHud
    from native_stress_watchdog import (
        CLEAN_REQUEST, HARD_REQUEST, GLOBAL_STATE, recover_orphaned_sessions,
    )


# A9a3r1 restores benchmark authority: telemetry is observable by default, while fail marks and force stops are explicit user choices.
# Compatibility/acceptance marker retained from the original A9a1r1 Machine Profile promotion surface.
MODE_HELP = {
    "all": "Runs Traditional, Cloud, Game, and Hybrid engine-native campaigns using the real game level, renderer, lighting, water, enemies, kiosks, AR, and door-preview system.",
    "traditional": "Uses the real game renderer and rooms at moderate point tiers to measure a clean baseline with minimal dynamic population.",
    "cloud": "Raises the real liminal room cloud through point tiers and includes scanner reveal stages while preserving the game room/door visibility rules.",
    "game": "Keeps the real game environment near the normal baseline while increasing real Hash Dogs and Formless Shadows, economy visuals, water, AR, lighting, and navigation activity.",
    "hybrid": "Raises real room cloud points and real dynamic entity population together to expose combined CPU/GPU limits.",
    "workload": "Runs registry-driven feature ramps for authored lights, material layers, sound ripples, animated actors, Playbook evaluations, Tupd test objects, and SCUI panels.",
}


def _decode_latest_result_pointer(root: Path, raw: str) -> Path:
    """Decode current and legacy path-pointer formats without escaping the report root."""
    text = raw.strip()
    if not text:
        raise ValueError("latest-result pointer is empty")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"\"", "'"}:
        if text[0] == "\"":
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = text[1:-1]
            if not isinstance(decoded, str):
                raise ValueError("latest-result pointer is not a string")
            text = decoded
        else:
            text = text[1:-1]
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=False)
    result_root = (root / "reports" / "native_stress_runs").resolve(strict=False)
    try:
        resolved.relative_to(result_root)
    except ValueError as exc:
        raise ValueError("latest-result pointer escapes reports/native_stress_runs") from exc
    return resolved


def _write_latest_result_pointer(root: Path, directory: Path) -> None:
    pointer = root / "reports" / "native_stress_latest_path.txt"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = pointer.with_suffix(pointer.suffix + ".tmp")
    temporary.write_text(str(directory) + "\n", encoding="utf-8")
    temporary.replace(pointer)


def _latest_result_directory(root: Path) -> tuple[Path, str | None]:
    """Return a valid report directory, repairing legacy/stale pointer files when possible."""
    pointer = root / "reports" / "native_stress_latest_path.txt"
    pointer_problem: str | None = None
    if pointer.is_file():
        try:
            lines = pointer.read_text(encoding="utf-8", errors="replace").splitlines()
            if not lines:
                raise ValueError("latest-result pointer has no path")
            directory = _decode_latest_result_pointer(root, lines[0])
            report = directory / "NATIVE_STRESS_REPORT.md"
            if not directory.is_dir() or not report.is_file():
                raise FileNotFoundError(report)
            _write_latest_result_pointer(root, directory)
            return directory, None
        except (OSError, ValueError) as exc:
            pointer_problem = str(exc)

    result_root = root / "reports" / "native_stress_runs"
    candidates: list[Path] = []
    if result_root.is_dir():
        for directory in result_root.iterdir():
            if directory.is_dir() and (directory / "NATIVE_STRESS_REPORT.md").is_file():
                candidates.append(directory)
    if not candidates:
        if pointer_problem:
            raise FileNotFoundError(f"no valid stress report found; pointer error: {pointer_problem}")
        raise FileNotFoundError("no engine-native stress report has been generated yet")
    candidates.sort(key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)
    directory = candidates[0].resolve(strict=False)
    _write_latest_result_pointer(root, directory)
    note = "Recovered the newest valid stress report and repaired the latest-result pointer."
    if pointer_problem:
        note += f" Previous pointer issue: {pointer_problem}"
    return directory, note


def _open_directory(directory: Path) -> None:
    opener = shutil.which("xdg-open")
    command = [opener, str(directory)] if opener else []
    if not command:
        gio = shutil.which("gio")
        if gio:
            command = [gio, "open", str(directory)]
    if not command:
        raise OSError("no desktop folder opener was found (xdg-open or gio)")
    subprocess.Popen(
        command,
        cwd=directory.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _event=None) -> None:
        if self.tip is not None:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.tip, text=self.text, wraplength=440, padding=8, relief="solid").pack()

    def hide(self, _event=None) -> None:
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class NativeStressLauncher(tk.Tk):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root_path = root
        self.binary = root / "build" / "almond_signal_native_stress"
        self.settings_path = root / "config" / "native_stress_gui.json"
        self.hud_settings_path = root / "config" / "native_stress_hud.json"
        self.live_path = root / "reports" / "native_stress_live.json"
        self.watchdog_state_path = root / "reports" / GLOBAL_STATE
        self.clean_request_path = root / "reports" / CLEAN_REQUEST
        self.hard_request_path = root / "reports" / HARD_REQUEST
        self.process: subprocess.Popen[str] | None = None
        self.hud_overlay: NativeStressHud | None = None
        self.hud_wall_started: float | None = None
        self.hud_wall_elapsed = 0.0
        self.hud_wall_finished = True
        self.hud_final_state = "previous"
        self.hud_final_reason = "NO ACTIVE CAMPAIGN"
        self.last_live_data: dict[str, object] = {}

        self.title("ALMOND SIGNAL — A9a3r2 Generation Heartbeat & Truthful HUD")
        self.geometry("1120x800")
        self.minsize(900, 660)

        self.mode = tk.StringVar(value="all")
        self.run_class = tk.StringVar(value="standard")
        self.backend = tk.StringVar(value="auto")
        self.points = tk.StringVar(value="8000000")
        self.target_fps = tk.StringVar(value="60")
        self.resolution = tk.StringVar(value="1280x720")
        self.campaign = tk.StringVar(value="120")
        self.scare_seconds = tk.StringVar(value="30")
        self.scare_finale = tk.BooleanVar(value=True)
        self.death_finale = tk.BooleanVar(value=True)
        self.progressive = tk.BooleanVar(value=True)
        self.progressive_range = tk.StringVar(value="normal")
        self.scanner = tk.BooleanVar(value=True)
        self.presentation = tk.BooleanVar(value=True)
        self.promote = tk.BooleanVar(value=False)
        self.live_hud = tk.BooleanVar(value=True)
        self.max_ram = tk.StringVar(value="88")
        self.reserve = tk.StringVar(value="4096")
        self.cpu_advisory = tk.StringVar(value="91")
        self.gpu_advisory = tk.StringVar(value="97")
        self.watchdog_timeout = tk.StringVar(value="8")
        self.watchdog_generation_timeout = tk.StringVar(value="90")
        self.workload_ramps = tk.BooleanVar(value=True)
        self.thermal_read = tk.BooleanVar(value=True)
        self.thermal_profile_fail = tk.BooleanVar(value=False)
        self.thermal_force_stop = tk.BooleanVar(value=False)
        self.thermal_sensor_policy = tk.StringVar(value="processor-gpu")
        self.thermal_safe = tk.StringVar(value="85")
        self.thermal_fail = tk.StringVar(value="100")
        self.thermal_force = tk.StringVar(value="105")
        self.thermal_hold = tk.StringVar(value="10")
        self.status = tk.StringVar(value="Ready — watchdog parent available")
        self.live_runtime = tk.StringVar(value="LIVE RUNTIME 00:00:00")
        self.live_line = tk.StringVar(value="No native stress campaign running")
        self.total_runtime = tk.StringVar(value="Selected run time: calculating…")

        recovered = recover_orphaned_sessions(self.root_path)
        self._build_ui()
        self._load_settings()
        self.mode.trace_add("write", lambda *_args: self._sync_controls())
        self.campaign.trace_add("write", lambda *_args: self._sync_controls())
        self.scare_seconds.trace_add("write", lambda *_args: self._sync_controls())
        self._sync_controls()
        if recovered:
            self.status.set(f"Recovered {len(recovered)} interrupted native stress run(s); see Results")
        self.after(250, self._poll)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="ALMOND SIGNAL: LIVE TAPE", font=("Sans", 16, "bold")).pack(anchor="w")
        ttk.Label(top, text="Engine-native benchmark: real rooms, real point renderer, real previews, real water, real enemies, real kiosks and AR").pack(anchor="w")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        setup = ttk.Frame(notebook, padding=12)
        results = ttk.Frame(notebook, padding=12)
        profiles = ttk.Frame(notebook, padding=12)
        notebook.add(setup, text="Run Setup")
        notebook.add(results, text="Results")
        notebook.add(profiles, text="Machine Profile")

        mode_box = ttk.LabelFrame(setup, text="Benchmark mode", padding=10)
        mode_box.pack(fill="x", pady=(0, 8))
        for column, mode in enumerate(("all", "traditional", "cloud", "game", "hybrid", "workload")):
            button = ttk.Radiobutton(mode_box, text=mode.replace("_", " ").title(), variable=self.mode, value=mode)
            button.grid(row=0, column=column, padx=8, sticky="w")
            ToolTip(button, MODE_HELP[mode])

        grid = ttk.LabelFrame(setup, text="Native campaign settings", padding=10)
        grid.pack(fill="x", pady=(0, 8))
        labels = [
            ("Run class", self.run_class, ("quick", "standard", "official", "developer")),
            ("Video backend", self.backend, ("auto", "x11", "wayland")),
            ("Maximum environment points", self.points, ("500000", "1000000", "2000000", "4000000", "8000000", "10000000", "12000000", "16000000", "20000000", "24000000", "32000000")),
            ("Target FPS", self.target_fps, ("30", "60", "90", "120")),
            ("Resolution", self.resolution, ("960x540", "1280x720", "1600x900", "1920x1080")),
            ("Base campaign seconds per mode", self.campaign, ("90", "120", "150", "180", "210", "240", "270")),
            ("Scare finale seconds", self.scare_seconds, ("30", "60", "90")),
            ("Progressive range", self.progressive_range, ("normal", "2x", "3x", "5x", "10x", "25x", "50x", "100x", "full-map")),
            ("Maximum RAM percent", self.max_ram, ("55", "65", "75", "80", "85", "88")),
            ("System memory reserve MiB", self.reserve, ("2048", "4096", "6144", "8192")),
            ("CPU advisory percent", self.cpu_advisory, ("75", "85", "90", "91", "95")),
            ("GPU frame-budget advisory percent", self.gpu_advisory, ("85", "90", "95", "97", "100")),
            ("Watchdog render heartbeat timeout seconds", self.watchdog_timeout, ("5", "8", "12", "20")),
            ("Point generation/upload timeout seconds", self.watchdog_generation_timeout, ("30", "60", "90", "120", "180", "300")),
            ("Thermal sensor policy", self.thermal_sensor_policy, ("processor-gpu", "all")),
            ("Thermal safe / warning °C", self.thermal_safe, ("80", "85", "90", "95")),
            ("Thermal fail-mark °C", self.thermal_fail, ("90", "95", "98", "100", "105")),
            ("Thermal force-stop °C", self.thermal_force, ("95", "100", "105", "110")),
            ("Force-stop hold seconds", self.thermal_hold, ("0", "3", "5", "10", "15", "30")),
        ]
        for index, (label, variable, values) in enumerate(labels):
            row, col = divmod(index, 2)
            col *= 2
            ttk.Label(grid, text=label + ":").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=4)
            box = ttk.Combobox(grid, textvariable=variable, values=values, state="normal", width=18)
            box.grid(row=row, column=col + 1, sticky="ew", padx=(0, 18), pady=4)
            box.bind("<<ComboboxSelected>>", lambda _event: self._sync_controls(), add="+")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

        flags = ttk.LabelFrame(setup, text="Systems", padding=10)
        flags.pack(fill="x", pady=(0, 8))
        flag_specs = (
            ("Use real progressive room/range handling", self.progressive, self._sync_controls),
            ("Include scanner stages", self.scanner, None),
            ("Presentation camera speed", self.presentation, None),
            ("Live movable HUD window", self.live_hud, self._set_hud_visibility),
            ("Night / dual-siren scare finale", self.scare_finale, self._sync_controls),
            ("Round-robin death overlay ending", self.death_finale, self._sync_controls),
            ("Promote this target only if every profile gate passes", self.promote, None),
            ("Include registry-driven feature workload ramps", self.workload_ramps, self._sync_controls),
            ("Read Linux thermal sensors (telemetry)", self.thermal_read, None),
            ("Mark profile failed at the fail temperature", self.thermal_profile_fail, None),
            ("Force stop after sustained force temperature", self.thermal_force_stop, None),
        )
        for index, (text, variable, command) in enumerate(flag_specs):
            row, column = divmod(index, 3)
            ttk.Checkbutton(flags, text=text, variable=variable, command=command).grid(
                row=row, column=column, sticky="w", padx=8, pady=3
            )
        for column in range(3):
            flags.columnconfigure(column, weight=1)
        ttk.Label(
            flags,
            text="A9a3r1 keeps watchdog and memory protection, but thermal telemetry is monitor-only unless you explicitly enable profile fail or sustained force stop. Processor/GPU sensors are selected by default; Sensor Doctor shows what is being used.",
            wraplength=980,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 2))

        actions = ttk.Frame(setup)
        actions.pack(fill="x", pady=(4, 8))
        primary = ttk.Frame(actions)
        primary.pack(fill="x")
        ttk.Button(primary, text="START ENGINE-NATIVE TEST", command=self.start).pack(side="left", padx=4)
        ttk.Button(primary, text="Clean Stop", command=self.stop).pack(side="left", padx=4)
        ttk.Button(primary, text="Force Abort + Recover", command=self.force_abort).pack(side="left", padx=4)
        ttk.Button(primary, text="Show / Move HUD", command=self.show_hud_window).pack(side="left", padx=4)
        ttk.Button(primary, text="Thermal Sensor Doctor", command=self.show_thermal_sensor_doctor).pack(side="left", padx=4)
        secondary = ttk.Frame(actions)
        secondary.pack(fill="x", pady=(5, 0))
        ttk.Button(secondary, text="Quick Profile", command=self.quick_profile).pack(side="left", padx=4)
        ttk.Button(secondary, text="Quick Route Validation", command=self.quick_validation).pack(side="left", padx=4)
        ttk.Button(secondary, text="Quick Self-Test", command=self.quick_selftest).pack(side="left", padx=4)
        ttk.Button(secondary, text="Full Regression Tests…", command=self.full_tests).pack(side="left", padx=4)

        live = ttk.LabelFrame(setup, text="Live status", padding=12)
        live.pack(fill="x")
        ttk.Label(live, textvariable=self.live_line, font=("Sans", 11, "bold")).pack(anchor="center")
        ttk.Label(live, textvariable=self.live_runtime, font=("Monospace", 13, "bold")).pack(anchor="center", pady=(5, 0))
        ttk.Label(live, textvariable=self.total_runtime).pack(anchor="center", pady=(4, 0))
        ttk.Label(live, textvariable=self.status).pack(anchor="center", pady=(4, 0))

        result_actions = ttk.Frame(results)
        result_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(result_actions, text="Refresh latest", command=self.show_latest).pack(side="left", padx=4)
        ttk.Button(result_actions, text="Open result folder", command=self.open_result_folder).pack(side="left", padx=4)
        ttk.Button(result_actions, text="Recover interrupted runs", command=self.recover_interrupted_runs).pack(side="left", padx=4)
        self.result_text = tk.Text(results, wrap="word", padx=10, pady=10)
        self.result_text.pack(fill="both", expand=True)
        self.show_latest()

        profile_actions = ttk.Frame(profiles)
        profile_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(profile_actions, text="Refresh Profile Status", command=self.show_profile_status).pack(side="left", padx=4)
        ttk.Button(profile_actions, text="Official + Promote", command=self.official_promote).pack(side="left", padx=4)
        ttk.Button(profile_actions, text="Export Privacy-Safe Bundle", command=self.export_profile_bundle).pack(side="left", padx=4)
        ttk.Button(profile_actions, text="Open Profile Folder", command=self.open_profile_folder).pack(side="left", padx=4)
        ttk.Button(profile_actions, text="Build Workload Registry", command=self.build_workload_registry).pack(side="left", padx=4)
        ttk.Label(
            profiles,
            text=(
                "Profiles are target-specific. Official + Promote benchmarks the selected resolution/FPS, "
                "then the game boots at that active profile target on its next launch."
            ),
            wraplength=980,
        ).pack(fill="x", pady=(0, 8))
        self.profile_text = tk.Text(profiles, wrap="word", padx=10, pady=10)
        self.profile_text.pack(fill="both", expand=True)
        self.show_profile_status()

    def _sync_controls(self) -> None:
        # Every visible default is passed explicitly. This prevents the startup
        # checkboxes and dropdowns from disagreeing with the native process.
        try:
            base_seconds = max(30, int(float(self.campaign.get())))
        except ValueError:
            base_seconds = 120
        mode_count = (5 if self.workload_ramps.get() else 4) if self.mode.get() == "all" else 1
        finale_seconds = int(self.scare_seconds.get()) if self.scare_finale.get() else 0
        if self.death_finale.get():
            finale_seconds += 3
        total = base_seconds * mode_count + finale_seconds
        minutes, seconds = divmod(total, 60)
        self.total_runtime.set(
            f"Estimated selected runtime: {minutes}m {seconds:02d}s "
            f"({mode_count} campaign{'s' if mode_count != 1 else ''} + finale)"
        )
        state = "Progressive handling ON" if self.progressive.get() else "Progressive handling OFF: balanced full-map comparison"
        self.status.set(state)

    def _load_settings(self) -> None:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key, variable in {
            "mode": self.mode, "run_class": self.run_class,
            "backend": self.backend, "points": self.points,
            "target_fps": self.target_fps, "resolution": self.resolution,
            "campaign": self.campaign, "scare_seconds": self.scare_seconds,
            "progressive_range": self.progressive_range,
            "max_ram": self.max_ram, "reserve": self.reserve,
            "cpu_advisory": self.cpu_advisory, "gpu_advisory": self.gpu_advisory,
            "watchdog_timeout": self.watchdog_timeout,
            "watchdog_generation_timeout": self.watchdog_generation_timeout,
            "thermal_sensor_policy": self.thermal_sensor_policy,
            "thermal_safe": self.thermal_safe, "thermal_fail": self.thermal_fail,
            "thermal_force": self.thermal_force, "thermal_hold": self.thermal_hold,
            "progressive": self.progressive, "scanner": self.scanner,
            "presentation": self.presentation, "scare_finale": self.scare_finale,
            "death_finale": self.death_finale, "promote": self.promote,
            "live_hud": self.live_hud, "workload_ramps": self.workload_ramps,
            "thermal_read": self.thermal_read,
            "thermal_profile_fail": self.thermal_profile_fail,
            "thermal_force_stop": self.thermal_force_stop,
        }.items():
            if key in data:
                variable.set(data[key])

    def _save_settings(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "mode": self.mode.get(), "run_class": self.run_class.get(),
            "backend": self.backend.get(), "points": self.points.get(),
            "target_fps": self.target_fps.get(), "resolution": self.resolution.get(),
            "campaign": self.campaign.get(), "scare_seconds": self.scare_seconds.get(),
            "progressive_range": self.progressive_range.get(),
            "max_ram": self.max_ram.get(), "reserve": self.reserve.get(),
            "cpu_advisory": self.cpu_advisory.get(), "gpu_advisory": self.gpu_advisory.get(),
            "watchdog_timeout": self.watchdog_timeout.get(),
            "watchdog_generation_timeout": self.watchdog_generation_timeout.get(),
            "thermal_sensor_policy": self.thermal_sensor_policy.get(),
            "thermal_safe": self.thermal_safe.get(), "thermal_fail": self.thermal_fail.get(),
            "thermal_force": self.thermal_force.get(), "thermal_hold": self.thermal_hold.get(),
            "progressive": self.progressive.get(), "scanner": self.scanner.get(),
            "presentation": self.presentation.get(), "scare_finale": self.scare_finale.get(),
            "death_finale": self.death_finale.get(), "promote": self.promote.get(),
            "live_hud": self.live_hud.get(), "workload_ramps": self.workload_ramps.get(),
            "thermal_read": self.thermal_read.get(),
            "thermal_profile_fail": self.thermal_profile_fail.get(),
            "thermal_force_stop": self.thermal_force_stop.get(),
        }
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp.replace(self.settings_path)

    def command(self, mode: str | None = None, campaign: str | None = None,
                points: str | None = None, include_finales: bool = True) -> list[str]:
        command = [
            str(self.binary), f"--root={self.root_path}", f"--video={self.backend.get()}",
            f"--mode={mode or self.mode.get()}", f"--run-class={self.run_class.get()}",
            f"--max-points={points or self.points.get()}",
            f"--target-fps={self.target_fps.get()}", f"--resolution={self.resolution.get()}",
            f"--campaign-seconds={campaign or self.campaign.get()}",
            f"--scare-seconds={self.scare_seconds.get()}",
            f"--progressive-range={self.progressive_range.get()}",
            f"--max-ram-percent={self.max_ram.get()}", f"--memory-reserve-mib={self.reserve.get()}",
            f"--cpu-advisory-percent={self.cpu_advisory.get()}",
            f"--gpu-advisory-percent={self.gpu_advisory.get()}",
            f"--thermal-sensor-policy={self.thermal_sensor_policy.get()}",
            f"--thermal-safe-c={self.thermal_safe.get()}",
            f"--thermal-fail-c={self.thermal_fail.get()}",
            f"--thermal-force-stop-c={self.thermal_force.get()}",
            f"--thermal-force-hold-seconds={self.thermal_hold.get()}",
            "--progressive" if self.progressive.get() else "--no-progressive",
            "--scanner-stages" if self.scanner.get() else "--no-scanner-stages",
            "--presentation" if self.presentation.get() else "--no-presentation",
            "--scare-finale" if include_finales and self.scare_finale.get() else "--no-scare-finale",
            "--death-finale" if include_finales and self.death_finale.get() else "--no-death-finale",
            "--workload-ramps" if self.workload_ramps.get() else "--no-workload-ramps",
            "--thermal-read" if self.thermal_read.get() else "--no-thermal-read",
            "--thermal-profile-fail" if self.thermal_profile_fail.get() else "--no-thermal-profile-fail",
            "--thermal-force-stop" if self.thermal_force_stop.get() else "--no-thermal-force-stop",
        ]
        if self.promote.get():
            command.append("--promote-profile")
        return command

    def watchdog_command(self, child_command: list[str]) -> list[str]:
        try:
            timeout = max(2.0, float(self.watchdog_timeout.get()))
        except ValueError:
            timeout = 8.0
        try:
            generation_timeout = max(timeout, float(self.watchdog_generation_timeout.get()))
        except ValueError:
            generation_timeout = 90.0
        return [
            sys.executable,
            str(self.root_path / "tools" / "native_stress_watchdog.py"),
            str(self.root_path),
            f"--heartbeat-timeout={timeout:g}",
            f"--generation-timeout={generation_timeout:g}",
            "--startup-timeout=45",
            "--clean-stop-grace=8",
            "--",
            *child_command,
        ]

    def _ensure_hud(self) -> None:
        if self.hud_overlay is None or not self.hud_overlay.winfo_exists():
            self.hud_overlay = NativeStressHud(self, self.hud_settings_path)
        self.hud_overlay.show()

    def show_hud_window(self) -> None:
        self.live_hud.set(True)
        self._ensure_hud()
        self._save_settings()

    def _set_hud_visibility(self) -> None:
        if self.live_hud.get():
            self._ensure_hud()
        elif self.hud_overlay is not None and self.hud_overlay.winfo_exists():
            self.hud_overlay.withdraw()

    def _begin_hud_run(self) -> None:
        self.hud_wall_started = time.monotonic()
        self.hud_wall_elapsed = 0.0
        self.hud_wall_finished = False
        self.hud_final_state = ""
        self.hud_final_reason = ""
        self.last_live_data = {}
        try:
            self.live_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # A stale snapshot is informational only; failure to remove it must not block a run.
            pass
        if self.live_hud.get():
            self._ensure_hud()

    def _hud_wall_seconds(self) -> float:
        if self.hud_wall_started is None:
            return self.hud_wall_elapsed
        if self.hud_wall_finished:
            return self.hud_wall_elapsed
        return max(0.0, time.monotonic() - self.hud_wall_started)

    def _finish_hud_run(self, state: str, reason: str) -> None:
        self.hud_wall_elapsed = self._hud_wall_seconds()
        self.hud_wall_finished = True
        self.hud_final_state = state
        self.hud_final_reason = reason
        self.last_live_data["campaign_final_state"] = state
        self.last_live_data["campaign_final_reason"] = reason
        self.last_live_data["wall_timer_stopped"] = True

    @staticmethod
    def _read_sensor_value(path: Path) -> float | None:
        try:
            raw = float(path.read_text(encoding="utf-8", errors="replace").strip())
        except (OSError, ValueError):
            return None
        value = raw / 1000.0 if abs(raw) > 250.0 else raw
        return value if -20.0 <= value <= 150.0 else None

    @staticmethod
    def _is_processor_gpu_sensor(source: str, label: str) -> bool:
        key = f"{source} {label}".lower()
        excluded = ("nvme", "ssd", "composite", "iwlwifi", "wifi", "wireless", "battery", "bat0", "bat1", "pch", "ambient", "inlet", "dimm")
        selected = ("coretemp", "k10temp", "zenpower", "x86_pkg_temp", "package", "cpu", "core", "tctl", "tdie", "soc", "gpu", "amdgpu", "radeon", "nouveau", "nvidia", "junction", "edge")
        return not any(token in key for token in excluded) and any(token in key for token in selected)

    def _thermal_sensor_rows(self) -> list[tuple[bool, str, str, float]]:
        rows: list[tuple[bool, str, str, float]] = []
        thermal_root = Path("/sys/class/thermal")
        for zone in sorted(thermal_root.glob("thermal_zone*")):
            value = self._read_sensor_value(zone / "temp")
            if value is None:
                continue
            try:
                label = (zone / "type").read_text(encoding="utf-8", errors="replace").strip() or "unlabelled"
            except OSError:
                label = "unlabelled"
            rows.append((self._is_processor_gpu_sensor("thermal", label), zone.name, label, value))
        hwmon_root = Path("/sys/class/hwmon")
        for hwmon in sorted(hwmon_root.glob("hwmon*")):
            try:
                source = (hwmon / "name").read_text(encoding="utf-8", errors="replace").strip() or hwmon.name
            except OSError:
                source = hwmon.name
            for input_path in sorted(hwmon.glob("temp*_input")):
                value = self._read_sensor_value(input_path)
                if value is None:
                    continue
                prefix = input_path.name.removesuffix("_input")
                try:
                    label = (hwmon / f"{prefix}_label").read_text(encoding="utf-8", errors="replace").strip() or prefix
                except OSError:
                    label = prefix
                rows.append((self._is_processor_gpu_sensor(source, label), source, label, value))
        return rows

    def show_thermal_sensor_doctor(self) -> None:
        window = tk.Toplevel(self)
        window.title("SignalCloud Thermal Sensor Doctor")
        window.geometry("780x430")
        outer = ttk.Frame(window, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=("Processor/GPU policy guards only sensors marked SELECTED. Other sensors remain visible as observed telemetry. "
                  "Choose policy 'all' only when you intentionally want every detected sensor to control thermal thresholds."),
            wraplength=740,
        ).pack(fill="x", pady=(0, 8))
        text = tk.Text(outer, wrap="none", font=("Monospace", 10))
        ybar = ttk.Scrollbar(outer, orient="vertical", command=text.yview)
        xbar = ttk.Scrollbar(outer, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        text.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        rows = self._thermal_sensor_rows()
        if not rows:
            text.insert("end", "No readable Linux thermal sensors were found. Thermal telemetry will be unavailable.\n")
        else:
            policy_all = self.thermal_sensor_policy.get() == "all"
            text.insert("end", "USE       SOURCE                  LABEL                         TEMP\n")
            text.insert("end", "---------  ----------------------  ----------------------------  --------\n")
            for selected, source, label, value in rows:
                use = "SELECTED" if policy_all or selected else "OBSERVED"
                text.insert("end", f"{use:<9}  {source[:22]:<22}  {label[:28]:<28}  {value:6.1f} C\n")
        text.configure(state="disabled")

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Already running", "An engine-native campaign is already running.")
            return
        if not self.binary.exists():
            messagebox.showerror("Not built", "Run scripts/setup_dev_environment.sh first.")
            return
        self._save_settings()
        try:
            self._refresh_workload_registry(silent=True)
            self.live_path.unlink(missing_ok=True)
            self.clean_request_path.unlink(missing_ok=True)
            self.hard_request_path.unlink(missing_ok=True)
            self._begin_hud_run()
            self.process = subprocess.Popen(self.watchdog_command(self.command()), cwd=self.root_path, text=True)
            self.status.set("Engine-native stress campaign started under A9a3r1 watchdog, memory guard, and user-owned thermal policy")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.clean_request_path.parent.mkdir(parents=True, exist_ok=True)
            self.clean_request_path.write_text("clean-stop\n", encoding="utf-8")
            self.status.set("Clean stop requested; watchdog will preserve completed stage evidence")

    def force_abort(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno(
                "Force abort benchmark",
                "Immediately stop the benchmark child and recover a partial report? The active machine profile will not change.",
            ):
                return
            self.hard_request_path.parent.mkdir(parents=True, exist_ok=True)
            self.hard_request_path.write_text("hard-abort\n", encoding="utf-8")
            self.status.set("Hard abort requested; watchdog recovery is in progress")

    def quick_profile(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Already running", "A benchmark campaign is already running.")
            return
        previous = (self.run_class.get(), self.mode.get(), self.campaign.get(), self.points.get())
        self.run_class.set("quick")
        self.mode.set("all")
        self.campaign.set("60")
        self.points.set("8000000")
        self.promote.set(False)
        self.start()
        self.status.set("Quick profile started; a validated candidate will be written but not auto-promoted")
        # Preserve the user's preferred setup for the next manual run.
        self.run_class.set(previous[0])
        self.mode.set(previous[1])
        self.campaign.set(previous[2])
        self.points.set(previous[3])
        self._save_settings()

    def official_promote(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Already running", "A benchmark campaign is already running.")
            return
        target = f"{self.resolution.get()} @ {self.target_fps.get()} FPS"
        if not messagebox.askyesno(
            "Official profile promotion",
            "Run all native stress modes for the selected target and promote only if every protected "
            f"gate passes?\n\nTarget: {target}\nMaximum environment points: {self.points.get()}",
        ):
            return
        previous = (self.run_class.get(), self.mode.get(), self.promote.get(), self.workload_ramps.get())
        self.run_class.set("official")
        self.mode.set("all")
        self.promote.set(True)
        self.workload_ramps.set(True)
        self.start()
        self.status.set(
            f"Official profile run started for {target}; thermal fail/force-stop authority remains exactly as selected"
        )
        self.run_class.set(previous[0])
        self.mode.set(previous[1])
        self.promote.set(previous[2])
        self.workload_ramps.set(previous[3])
        self._save_settings()

    def quick_validation(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.live_path.unlink(missing_ok=True)
        self._begin_hud_run()
        child = self.command(mode="traditional", campaign="30", points="500000", include_finales=False)
        self.process = subprocess.Popen(self.watchdog_command(child), cwd=self.root_path, text=True)
        self.status.set("30-second real-room route validation started")

    def quick_selftest(self) -> None:
        subprocess.Popen([str(self.root_path / "scripts" / "run_native_stress_quick_tests.sh")], cwd=self.root_path)
        self.status.set("Quick non-blocking native stress tests started")

    def full_tests(self) -> None:
        if not messagebox.askyesno("Full regression tests", "This recompiles and runs every Pivot 0–13 test and may heavily use the machine for several minutes. Continue?"):
            return
        subprocess.Popen(["konsole", "-e", str(self.root_path / "scripts" / "run_selftests.sh")], cwd=self.root_path)

    def recover_interrupted_runs(self) -> None:
        recovered = recover_orphaned_sessions(self.root_path, stale_after=0.0)
        if recovered:
            self.status.set(f"Recovered {len(recovered)} interrupted run(s)")
            self.show_latest()
        else:
            self.status.set("No unrecovered interrupted run was found")

    def show_latest(self) -> None:
        self.result_text.delete("1.0", "end")
        try:
            directory, note = _latest_result_directory(self.root_path)
            if note:
                self.result_text.insert("end", note + "\n\n")
            report = directory / "NATIVE_STRESS_REPORT.md"
            self.result_text.insert("end", report.read_text(encoding="utf-8", errors="replace"))
            self.status.set(f"Latest stress report: {directory.name}")
        except (OSError, ValueError) as exc:
            self.result_text.insert("end", f"Could not open latest report: {exc}\n")

    def open_result_folder(self) -> None:
        try:
            directory, note = _latest_result_directory(self.root_path)
            _open_directory(directory)
            suffix = " (pointer repaired)" if note else ""
            self.status.set(f"Opened result folder: {directory.name}{suffix}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open result folder failed", str(exc))

    def show_profile_status(self) -> None:
        if not hasattr(self, "profile_text"):
            return
        self.profile_text.delete("1.0", "end")
        try:
            self.profile_text.insert("end", status_text(self.root_path))
            registry = self.root_path / "reports" / "stress_workload_registry.json"
            if registry.exists():
                data = json.loads(registry.read_text(encoding="utf-8"))
                self.profile_text.insert(
                    "end",
                    f"\nWorkload registry: {data.get('enabled_asset_count', 0)} enabled assets · "
                    f"{len(data.get('feature_channels', {}))} feature channels · "
                    f"hash {data.get('registry_sha256', 'none')}\n",
                )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.profile_text.insert("end", f"Could not read machine profile status: {exc}\n")

    def export_profile_bundle(self) -> None:
        try:
            path = export_privacy_bundle(self.root_path)
            self.status.set(f"Privacy-safe profile bundle exported: {path.name}")
            messagebox.showinfo("Profile bundle exported", str(path))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Profile export failed", str(exc))

    def open_profile_folder(self) -> None:
        directory = self.root_path / "user_data" / "machine_profiles"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            _open_directory(directory.resolve(strict=False))
            self.status.set("Opened machine-profile folder")
        except OSError as exc:
            messagebox.showerror("Open failed", str(exc))

    def _refresh_workload_registry(self, silent: bool = False) -> None:
        command = [sys.executable, str(self.root_path / "tools" / "stress_workload_registry.py"), str(self.root_path)]
        completed = subprocess.run(command, cwd=self.root_path, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            if not silent:
                messagebox.showerror("Registry failed", completed.stderr or completed.stdout)
            return
        if not silent:
            self.status.set("Stress workload registry refreshed")
        self.show_profile_status()

    def build_workload_registry(self) -> None:
        self._refresh_workload_registry(silent=False)

    def _poll(self) -> None:
        watchdog_data: dict[str, object] = {}
        if self.watchdog_state_path.exists():
            try:
                loaded = json.loads(self.watchdog_state_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    watchdog_data = loaded
            except (OSError, json.JSONDecodeError):
                watchdog_data = {}
        if self.live_path.exists():
            try:
                data = json.loads(self.live_path.read_text(encoding="utf-8"))
                if self.hud_wall_finished:
                    data["campaign_final_state"] = self.hud_final_state or "finished"
                    data["campaign_final_reason"] = self.hud_final_reason
                    data["wall_timer_stopped"] = True
                self.last_live_data = data
                seconds = int(float(data.get("runtime_seconds", 0)))
                hours, remain = divmod(seconds, 3600)
                minutes, secs = divmod(remain, 60)
                self.live_runtime.set(f"LIVE RUNTIME {hours:02d}:{minutes:02d}:{secs:02d}")
                finale = data.get("finale_phase", "")
                sirens = []
                if data.get("night_active"):
                    sirens.append("NIGHT")
                if data.get("local_siren_active"):
                    sirens.append("LOCAL SIREN")
                if int(data.get("full_siren_pulses", 0)):
                    sirens.append(f"FULL SIREN {data.get('full_siren_pulses')}/3")
                if data.get("death_cause"):
                    sirens.append(f"DEATH {data.get('death_cause')}")
                suffix = f" · {' · '.join(sirens)}" if sirens else ""
                if finale:
                    suffix += f" · {finale}"
                route_guard = int(data.get("route_containment_corrections", 0) or 0)
                guard_suffix = f" · route guard {route_guard}" if route_guard else ""
                workload_axis = str(data.get("workload_axis", "none") or "none")
                workload_suffix = ""
                if workload_axis != "none":
                    workload_suffix = f" · {workload_axis} L{int(data.get('workload_level', 0) or 0)}"
                thermal_suffix = ""
                if data.get("thermal_available"):
                    thermal_suffix = f" · {float(data.get('thermal_peak_celsius', 0.0) or 0.0):.1f}°C"
                elif self.thermal_read.get():
                    thermal_suffix = " · thermal unavailable"
                watchdog_age = watchdog_data.get("heartbeat_age_seconds")
                watchdog_suffix = ""
                if isinstance(watchdog_age, (int, float)):
                    watchdog_suffix = f" · watchdog {float(watchdog_age):.1f}s"
                self.live_line.set(
                    f"{data.get('mode', '?').upper()} · {data.get('location', '?')} · "
                    f"{data.get('resident_points', 0):,} resident · "
                    f"{data.get('renderer_submitted_points', data.get('submitted_points', 0)):,} drawn · "
                    f"{data.get('entities', 0)} entities · {data.get('progressive_range', 'off')}"
                    f"{workload_suffix}{thermal_suffix}{guard_suffix}{suffix}{watchdog_suffix}"
                )
                if self.live_hud.get():
                    if self.hud_overlay is None or not self.hud_overlay.winfo_exists():
                        self._ensure_hud()
                    wall_seconds = self._hud_wall_seconds()
                    heartbeat_age = max(0.0, time.time() - self.live_path.stat().st_mtime)
                    self.hud_overlay.update_telemetry(
                        data, wall_seconds=wall_seconds, heartbeat_age=heartbeat_age,
                        process_running=self.process is not None and self.process.poll() is None,
                    )
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        if self.process and self.process.poll() is not None:
            code = self.process.returncode
            final_watchdog_data = watchdog_data
            if self.watchdog_state_path.exists():
                try:
                    refreshed = json.loads(self.watchdog_state_path.read_text(encoding="utf-8"))
                    if isinstance(refreshed, dict):
                        final_watchdog_data = refreshed
                except (OSError, json.JSONDecodeError):
                    pass
            final_state = str(final_watchdog_data.get("state", "finished"))
            reason = str(final_watchdog_data.get("reason", ""))
            self._finish_hud_run(final_state, reason or f"exit-{code}")
            self.process = None
            if final_state == "completed" and code == 0:
                self.status.set("Campaign completed under watchdog; final report and profile evidence preserved")
            elif final_state == "interrupted":
                self.status.set(f"Campaign interrupted and recovered: {reason or 'see Results'}")
            else:
                self.status.set(f"Watchdog finished with exit code {code}")
            if self.live_hud.get() and self.hud_overlay is not None and self.hud_overlay.winfo_exists():
                wall_seconds = self._hud_wall_seconds()
                heartbeat_age = 0.0
                if self.live_path.exists():
                    heartbeat_age = max(0.0, time.time() - self.live_path.stat().st_mtime)
                self.hud_overlay.update_telemetry(
                    self.last_live_data, wall_seconds=wall_seconds, heartbeat_age=heartbeat_age, process_running=False
                )
            self.show_latest()
            self.show_profile_status()
        self.after(250, self._poll)


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    NativeStressLauncher(root).mainloop()
