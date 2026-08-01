#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Any


DEFAULT_HUD_GEOMETRY = "940x235"
_GEOMETRY_RE = re.compile(r"^\d+x\d+[+-]\d+[+-]\d+$")


def format_hms(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def floor_text(data: dict[str, Any]) -> str:
    floor = data.get("floor_level", 1)
    camera_y = data.get("camera_y", 0.0)
    try:
        return f"FLOOR {int(floor)} · Y {float(camera_y):.2f}m"
    except (TypeError, ValueError):
        return "FLOOR ?"


def status_alert(data: dict[str, Any]) -> str:
    explicit = str(data.get("alert", "")).strip()
    if explicit:
        return explicit
    if data.get("death_cause"):
        return f"LIVE TAPE COLLAPSE — {data['death_cause']}"
    if int(data.get("full_siren_pulses", 0) or 0):
        return f"FULL SIREN {data.get('full_siren_pulses')}/3"
    if data.get("local_siren_active"):
        return "LOCAL SIREN ACTIVE"
    if data.get("night_active"):
        return "NIGHT FLUX ACTIVE"
    thermal_state = str(data.get("thermal_state", ""))
    if thermal_state == "force-stop":
        elapsed = float(data.get("thermal_force_elapsed_seconds", 0.0) or 0.0)
        hold = float(data.get("thermal_force_hold_seconds", 0.0) or 0.0)
        return f"THERMAL FORCE THRESHOLD — {elapsed:.1f}/{hold:.1f}s"
    if thermal_state == "failed":
        return "THERMAL FAIL THRESHOLD OBSERVED"
    if thermal_state == "warning":
        return "THERMAL ABOVE USER SAFE LEVEL"
    workload = str(data.get("workload_axis", "none") or "none")
    if workload != "none":
        return f"WORKLOAD RAMP — {workload.upper()} LEVEL {int(data.get('workload_level', 0) or 0)}"
    if data.get("scanner"):
        return "SCANNER RECONSTRUCTION ACTIVE"
    return "SIGNALCLOUD ROUTE ACTIVE"


def valid_window_geometry(value: object) -> bool:
    return isinstance(value, str) and _GEOMETRY_RE.fullmatch(value.strip()) is not None


def read_hud_preferences(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_hud_preferences(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class NativeStressHud(tk.Toplevel):
    """Movable, resizable telemetry window for the engine-native stress renderer."""

    def __init__(
        self,
        master: tk.Misc,
        settings_path: Path | None = None,
        *,
        hide_on_close: bool = True,
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self.settings_path = settings_path
        self.hide_on_close = hide_on_close
        self._save_after_id: str | None = None
        self._preferences = read_hud_preferences(settings_path)

        self.title("ALMOND SIGNAL — Native Stress Live HUD")
        self.resizable(True, True)
        self.minsize(620, 175)
        self.configure(bg="#080b0c")
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.bind("<Escape>", lambda _event: self.close_window())
        self.bind("<Configure>", self._queue_geometry_save, add="+")

        self.topmost_var = tk.BooleanVar(value=bool(self._preferences.get("always_on_top", True)))
        self.attributes("-topmost", self.topmost_var.get())
        try:
            self.attributes("-alpha", 0.94)
        except tk.TclError:
            pass

        self.alert_var = tk.StringVar(value="SIGNALCLOUD HUD READY")
        self.timer_var = tk.StringVar(value="LIVE WALL 00:00:00 · ENGINE 00:00:00")
        self.stage_var = tk.StringVar(value="Waiting for native stress telemetry…")
        self.metrics_var = tk.StringVar(value="")
        self.systems_var = tk.StringVar(value="")
        self.heartbeat_var = tk.StringVar(value="HUD HEARTBEAT WAITING")

        self._build_menu()
        self._build_content()
        self.update_idletasks()
        self._restore_geometry()

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        window_menu = tk.Menu(menu, tearoff=False)
        window_menu.add_checkbutton(
            label="Always on top",
            variable=self.topmost_var,
            command=self._apply_topmost,
        )
        window_menu.add_command(label="Reset position and size", command=self.reset_geometry)
        window_menu.add_separator()
        window_menu.add_command(label="Hide HUD", command=self.close_window)
        menu.add_cascade(label="Window", menu=window_menu)
        self.configure(menu=menu)

    def _build_content(self) -> None:
        outer = tk.Frame(self, bg="#080b0c", bd=1, relief="solid")
        outer.pack(fill="both", expand=True)
        tk.Label(
            outer, textvariable=self.alert_var, bg="#080b0c", fg="#ffd56a",
            font=("Sans", 12, "bold"), padx=16, pady=5,
        ).pack(fill="x")
        tk.Label(
            outer, textvariable=self.timer_var, bg="#080b0c", fg="#ffffff",
            font=("Monospace", 15, "bold"), padx=16, pady=1,
        ).pack(fill="x")
        tk.Label(
            outer, textvariable=self.stage_var, bg="#080b0c", fg="#c9f4ff",
            font=("Sans", 10, "bold"), padx=16, pady=2,
        ).pack(fill="x")
        tk.Label(
            outer, textvariable=self.metrics_var, bg="#080b0c", fg="#d8e1d8",
            font=("Monospace", 10), padx=16, pady=1,
        ).pack(fill="x")
        tk.Label(
            outer, textvariable=self.systems_var, bg="#080b0c", fg="#b8cdbd",
            font=("Monospace", 9), padx=16, pady=1,
        ).pack(fill="x")
        self.heartbeat_label = tk.Label(
            outer, textvariable=self.heartbeat_var, bg="#080b0c", fg="#8ee39c",
            font=("Sans", 9, "bold"), padx=16, pady=2,
        )
        self.heartbeat_label.pack(fill="x")
        tk.Label(
            outer,
            text="Move or resize this window normally. Window → Always on top controls stacking.",
            bg="#080b0c", fg="#7f8b84", font=("Sans", 8), padx=16, pady=3,
        ).pack(fill="x")

    def _restore_geometry(self) -> None:
        saved = self._preferences.get("geometry")
        if valid_window_geometry(saved):
            self.geometry(str(saved))
            return
        self._place_centered(DEFAULT_HUD_GEOMETRY)

    def _place_centered(self, size: str) -> None:
        width_text, height_text = size.split("x", 1)
        width = int(width_text)
        height = int(height_text)
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(24, (self.winfo_screenheight() - height) // 8)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def reset_geometry(self) -> None:
        self._place_centered(DEFAULT_HUD_GEOMETRY)
        self._save_preferences()

    def _apply_topmost(self) -> None:
        self.attributes("-topmost", self.topmost_var.get())
        self._save_preferences()

    def _queue_geometry_save(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self.state() == "withdrawn":
            return
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except tk.TclError:
                pass
        self._save_after_id = self.after(350, self._save_preferences)

    def _save_preferences(self) -> None:
        self._save_after_id = None
        geometry = self.geometry()
        payload: dict[str, object] = {
            "geometry": geometry if valid_window_geometry(geometry) else DEFAULT_HUD_GEOMETRY + "+0+24",
            "always_on_top": bool(self.topmost_var.get()),
        }
        self._preferences = payload
        try:
            write_hud_preferences(self.settings_path, payload)
        except OSError:
            pass

    def close_window(self) -> None:
        self._save_preferences()
        if self.hide_on_close:
            self.withdraw()
        else:
            self.master.destroy()

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.attributes("-topmost", self.topmost_var.get())

    def update_telemetry(
        self,
        data: dict[str, Any],
        *,
        wall_seconds: float,
        heartbeat_age: float,
        process_running: bool,
    ) -> None:
        engine_seconds = float(data.get("runtime_seconds", 0.0) or 0.0)
        stage_elapsed = float(data.get("stage_elapsed_seconds", 0.0) or 0.0)
        stage_total = float(data.get("stage_duration_seconds", 0.0) or 0.0)
        progress = 0.0 if stage_total <= 0.0 else min(100.0, stage_elapsed / stage_total * 100.0)
        fps = float(data.get("fps", 0.0) or 0.0)
        target_fps = int(data.get("target_fps", 0) or 0)
        route_distance = float(data.get("route_distance", 0.0) or 0.0)

        self.alert_var.set(status_alert(data))
        self.timer_var.set(
            f"LIVE WALL {format_hms(wall_seconds)} · ENGINE {format_hms(engine_seconds)}"
        )
        self.stage_var.set(
            f"{str(data.get('mode', '?')).upper()} · {data.get('stage', '?')} · "
            f"{stage_elapsed:.1f}/{stage_total:.1f}s ({progress:.0f}%) · {data.get('location', '?')} · "
            f"{floor_text(data)}"
        )
        self.metrics_var.set(
            f"FPS {fps:7.1f}/{target_fps:<3d} · RES {int(data.get('resident_points', 0) or 0):,} · "
            f"DRAW {int(data.get('renderer_submitted_points', data.get('submitted_points', 0)) or 0):,} "
            f"/ SEL {int(data.get('submitted_points', 0) or 0):,} · "
            f"ROOMS {int(data.get('submitted_rooms', 0) or 0)} "
            f"(+{int(data.get('preview_rooms', 0) or 0)} preview) · ROUTE {route_distance:.1f}m"
        )
        flags: list[str] = []
        workload_axis = str(data.get("workload_axis", "none") or "none")
        if workload_axis != "none":
            flags.append(f"WORKLOAD {workload_axis} L{int(data.get('workload_level', 0) or 0)}")
            flags.append(f"OPS {int(data.get('workload_operations', 0) or 0):,}")
        if data.get("thermal_available"):
            selected_temp = float(data.get("thermal_peak_celsius", 0.0) or 0.0)
            sensor = str(data.get("thermal_sensor", "") or "selected")
            flags.append(f"THERMAL {selected_temp:.1f}C {sensor[:18]}")
            observed_temp = float(data.get("thermal_observed_peak_celsius", selected_temp) or selected_temp)
            observed_sensor = str(data.get("thermal_observed_sensor", "") or "")
            if observed_temp > selected_temp + 0.05:
                flags.append(f"OBS {observed_temp:.1f}C {observed_sensor[:18]}")
        elif "thermal_available" in data:
            flags.append("THERMAL N/A")
        cpu_peak = float(data.get("cpu_peak_percent", 0.0) or 0.0)
        if cpu_peak > 0.0:
            flags.append(f"CPU {cpu_peak:.1f}%/{float(data.get('cpu_advisory_percent', 91.0) or 91.0):.0f}%")
        gpu_pressure = float(data.get("gpu_frame_budget_peak_percent", 0.0) or 0.0)
        if gpu_pressure > 0.0:
            flags.append(f"GPU-BUDGET {gpu_pressure:.1f}%/{float(data.get('gpu_advisory_percent', 97.0) or 97.0):.0f}%")
        memory_limit = int(data.get("memory_safe_point_limit", 0) or 0)
        if memory_limit:
            flags.append(f"MEM SAFE {memory_limit:,}")
        flags.append(f"ENTITIES {int(data.get('entities', 0) or 0)}")
        flags.append("SCANNER ON" if data.get("scanner") else "SCANNER OFF")
        flags.append(
            f"PROGRESSIVE {data.get('progressive_range', 'off')}"
            if data.get("progressive") else "FULL-MAP SUBMISSION"
        )
        if data.get("balanced_full_map_cap"):
            flags.append("BALANCED CAP")
        recoveries = int(data.get("full_map_recoveries", 0) or 0)
        if recoveries:
            flags.append(f"MAP RESTORE {recoveries}")
        route_corrections = int(data.get("route_containment_corrections", 0) or 0)
        void_entries = int(data.get("signal_void_entries", 0) or 0)
        if route_corrections:
            flags.append(f"ROUTE GUARD {route_corrections}")
        if void_entries:
            flags.append(f"VOID ENTRY {void_entries}")
        raw_location = str(data.get("raw_location", "") or "")
        effective_location = str(data.get("location", "") or "")
        if raw_location and raw_location != effective_location:
            flags.append(f"RAW {raw_location}")
        if data.get("night_active"):
            flags.append("NIGHT")
        if data.get("local_siren_active"):
            flags.append("LOCAL SIREN")
        pulses = int(data.get("full_siren_pulses", 0) or 0)
        if pulses:
            flags.append(f"FULL SIREN {pulses}/3")
        if data.get("death_cause"):
            flags.append(f"DEATH {data.get('death_cause')}")
        self.systems_var.set(" · ".join(flags))

        if process_running and heartbeat_age > 2.0:
            self.heartbeat_var.set(f"HUD HEARTBEAT STALE — {heartbeat_age:.1f}s since engine update")
            self.heartbeat_label.configure(fg="#ff7d72")
        elif process_running:
            self.heartbeat_var.set(f"HUD HEARTBEAT LIVE — {heartbeat_age:.1f}s")
            self.heartbeat_label.configure(fg="#8ee39c")
        else:
            final_state = str(data.get("campaign_final_state", "unknown") or "unknown").upper()
            final_reason = str(data.get("campaign_final_reason", "") or "")
            stopped = " · WALL TIMER STOPPED" if data.get("wall_timer_stopped") else ""
            if final_state == "COMPLETED":
                self.heartbeat_var.set(f"CAMPAIGN COMPLETE{stopped} — final telemetry retained")
                self.heartbeat_label.configure(fg="#ffd56a")
            else:
                suffix = f" · {final_reason}" if final_reason else ""
                self.heartbeat_var.set(f"CAMPAIGN {final_state}{suffix}{stopped} — partial telemetry retained")
                self.heartbeat_label.configure(fg="#ff9b85")


def standalone_main() -> int:
    root_path = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    live_path = root_path / "reports" / "native_stress_live.json"
    settings_path = root_path / "config" / "native_stress_hud.json"
    root = tk.Tk()
    root.withdraw()
    hud = NativeStressHud(root, settings_path, hide_on_close=False)
    hud.show()
    wall_started = time.monotonic()
    last_data: dict[str, Any] = {}

    def poll() -> None:
        nonlocal last_data
        heartbeat_age = 999.0
        if live_path.exists():
            try:
                last_data = json.loads(live_path.read_text(encoding="utf-8"))
                heartbeat_age = max(0.0, time.time() - live_path.stat().st_mtime)
            except (OSError, json.JSONDecodeError):
                pass
        hud.update_telemetry(
            last_data,
            wall_seconds=time.monotonic() - wall_started,
            heartbeat_age=heartbeat_age,
            process_running=True,
        )
        root.after(250, poll)

    root.bind_all("<Control-Shift-Escape>", lambda _event: root.destroy())
    poll()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(standalone_main())
