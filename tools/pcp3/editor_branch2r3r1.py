from __future__ import annotations

import copy
import json
import math
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from tools.pcp3 import editor_branch2 as branch2
from tools.pcp3 import editor_branch2r3 as r3
from tools.pcp3.editor_branch2r2 import PaneState
from tools.pcp3.model import PCPDocument

SYNC_DELAY_MS = 1300
DEFAULT_ZOOM = 28.0
MAX_SAVED_CENTER = 1000.0
MAX_SAVED_DEPTH = 1000.0
MAX_ABS_PAN = 100000.0
MAX_PERSPECTIVE_DISTANCE = 5000.0
MIN_PERSPECTIVE_DISTANCE = 0.5


def _finite(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _pane_center_from_state(projection: str, state: dict[str, Any]) -> tuple[float, float, float]:
    zoom = max(2.0, min(400.0, _finite(state.get("zoom"), DEFAULT_ZOOM)))
    pan_x = _finite(state.get("pan_x"))
    pan_y = _finite(state.get("pan_y"))
    depth = _finite(state.get("depth"))
    if projection == "Top X/Z":
        return (-pan_x / zoom, depth, pan_y / zoom)
    if projection == "Front X/Y":
        return (-pan_x / zoom, pan_y / zoom, depth)
    if projection == "Side Z/Y":
        return (depth, pan_y / zoom, -pan_x / zoom)
    return (0.0, 0.0, 0.0)


def sanitize_workspace_data(value: Any) -> tuple[dict[str, Any], list[str]]:
    """Return safe persisted viewport data while preserving valid window/layout choices."""
    data = copy.deepcopy(value) if isinstance(value, dict) else {}
    reasons: list[str] = []
    pane_values = data.get("pane_states")
    if not isinstance(pane_values, dict):
        pane_values = {}
        data["pane_states"] = pane_values

    reset_navigation = False
    for projection in ("Top X/Z", "Front X/Y", "Side Z/Y", "Perspective 3D"):
        raw = pane_values.get(projection, {})
        if not isinstance(raw, dict):
            reset_navigation = True
            reasons.append(f"{projection}: invalid pane record")
            continue
        depth = _finite(raw.get("depth"), float("nan"))
        zoom = _finite(raw.get("zoom"), float("nan"))
        pan_x = _finite(raw.get("pan_x"), float("nan"))
        pan_y = _finite(raw.get("pan_y"), float("nan"))
        if not all(math.isfinite(item) for item in (depth, zoom, pan_x, pan_y)):
            reset_navigation = True
            reasons.append(f"{projection}: non-finite navigation value")
            continue
        if not (2.0 <= zoom <= 400.0) or abs(depth) > MAX_SAVED_DEPTH or abs(pan_x) > MAX_ABS_PAN or abs(pan_y) > MAX_ABS_PAN:
            reset_navigation = True
            reasons.append(f"{projection}: navigation outside safety bounds")
            continue
        if projection != "Perspective 3D":
            center = _pane_center_from_state(projection, raw)
            if any(abs(component) > MAX_SAVED_CENTER for component in center):
                reset_navigation = True
                reasons.append(f"{projection}: saved center outside PCP3 editing envelope")

    target = data.get("np_target", [0.0, 0.0, 0.0])
    if not isinstance(target, (list, tuple)) or len(target) < 3:
        reset_navigation = True
        reasons.append("NP target is malformed")
    else:
        target_values = [_finite(item, float("nan")) for item in target[:3]]
        if not all(math.isfinite(item) for item in target_values) or any(abs(item) > MAX_SAVED_CENTER for item in target_values):
            reset_navigation = True
            reasons.append("NP target is outside PCP3 editing envelope")

    distance = _finite(data.get("perspective_distance", 14.0), float("nan"))
    if not math.isfinite(distance) or not (MIN_PERSPECTIVE_DISTANCE <= distance <= MAX_PERSPECTIVE_DISTANCE):
        reset_navigation = True
        reasons.append("Perspective distance is invalid")

    if reset_navigation:
        data["pane_states"] = {
            projection: {"depth": 0.0, "zoom": DEFAULT_ZOOM, "pan_x": 0.0, "pan_y": 0.0}
            for projection in ("Top X/Z", "Front X/Y", "Side Z/Y", "Perspective 3D")
        }
        data["np_target"] = [0.0, 0.0, 0.0]
        data["perspective_distance"] = 14.0
        data["active_projection"] = "Top X/Z"

    data["schema"] = "pcp3_workspace_v3"
    data["window_sync_mode"] = "buffered_one_shot"
    data["window_sync_delay_ms"] = SYNC_DELAY_MS
    return data, reasons


def clamp_sync_target(
    target: tuple[float, float, float],
    lower: tuple[float, float, float],
    upper: tuple[float, float, float],
) -> tuple[tuple[float, float, float], bool]:
    """Clamp a sync target to a forgiving envelope around the actual document."""
    center = tuple((lower[index] + upper[index]) * 0.5 for index in range(3))
    span = max(max(0.0, upper[index] - lower[index]) for index in range(3))
    radius = max(25.0, min(1000.0, span * 4.0 + 10.0))
    safe: list[float] = []
    changed = False
    for index, raw in enumerate(target):
        value = _finite(raw, center[index])
        bounded = max(center[index] - radius, min(center[index] + radius, value))
        if not math.isclose(value, bounded, rel_tol=0.0, abs_tol=1e-9):
            changed = True
        safe.append(bounded)
    return (safe[0], safe[1], safe[2]), changed


class PCP3Editor(r3.PCP3Editor):
    """R3 R1 safety repair: buffered one-shot Window Sync and recoverable viewport state."""

    def __init__(self, root_path: Path) -> None:
        self._pending_sync_after: str | None = None
        self._pending_sync_candidate: tuple[float, float, float] | None = None
        self._pending_sync_projection: str | None = None
        self._pending_sync_zoom: float = DEFAULT_ZOOM
        self._sync_drag_origin: tuple[float, float] | None = None
        self._workspace_repair_reasons = self._repair_workspace_before_start(Path(root_path).resolve())
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 2 R3 R1 Sync Safety")
        self.document.metadata["editor_branch"] = "ISL_plus_branch2_R3_R1"
        if self._workspace_repair_reasons:
            self.update_status(
                "Recovered unsafe viewport memory · Window Sync is now buffered one-shot · Reset Viewports is available"
            )
        else:
            self.update_status("R3 R1 active · buffered Window Sync · guarded viewport memory · Reset Viewports")

    @classmethod
    def _repair_workspace_before_start(cls, root_path: Path) -> list[str]:
        path = root_path / "config" / "pcp3_workspace.json"
        try:
            original = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError, TypeError):
            original = {}
        repaired, reasons = sanitize_workspace_data(original)
        if not reasons and repaired == original:
            return []
        archive = root_path / "user_data" / "pcp3" / "workspace_archive"
        archive.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        try:
            if path.exists():
                path.replace(archive / f"pcp3_workspace_pre_R3_R1_{timestamp}.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(repaired, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(path)
        except OSError:
            pass
        return reasons

    def _build_toolbar(self) -> None:
        super()._build_toolbar()
        toolbar = self.active_tool_label.master
        ttk.Button(toolbar, text="Reset Viewports", command=self.prompt_reset_viewports).grid(
            row=1, column=7, columnspan=4, sticky="e", pady=(5, 0), padx=(4, 8)
        )

    # ---------- Window Sync safety ----------
    def _cancel_pending_sync(self, *, announce: bool = False) -> None:
        if self._pending_sync_after is not None:
            try:
                self.after_cancel(self._pending_sync_after)
            except tk.TclError:
                pass
        had_pending = self._pending_sync_candidate is not None
        self._pending_sync_after = None
        self._pending_sync_candidate = None
        self._pending_sync_projection = None
        self._sync_drag_origin = None
        if announce and had_pending:
            self.update_status("Pending Window Sync canceled")

    def _capture_sync_candidate(self, event: tk.Event) -> None:
        canvas = event.widget if isinstance(event.widget, tk.Canvas) else self.active_canvas
        if canvas is None:
            return
        pane = self.pane_for_canvas(canvas)
        world = self.screen_to_world(float(event.x), float(event.y), pane)
        lower, upper = self.document.bounds()
        safe, clamped = clamp_sync_target(world, lower, upper)
        state = self.state_for_pane(pane)
        if pane.projection == "Perspective 3D":
            zoom = 420.0 / max(1.0, float(self.perspective_distance.get()))
        else:
            zoom = state.zoom
        self._pending_sync_candidate = safe
        self._pending_sync_projection = pane.projection
        self._pending_sync_zoom = max(2.0, min(160.0, _finite(zoom, DEFAULT_ZOOM)))
        suffix = " · target clamped to safe document envelope" if clamped else ""
        self.update_status(
            f"Window Sync target x {safe[0]:.2f}, y {safe[1]:.2f}, z {safe[2]:.2f}{suffix} · release to queue 1.3s"
        )

    def canvas_press(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        if self.tool.get() == "window_sync":
            self._cancel_pending_sync()
            self._sync_drag_origin = (float(event.x), float(event.y))
            self._capture_sync_candidate(event)
            return
        super().canvas_press(event)

    def canvas_drag(self, event: tk.Event) -> None:
        self._activate_canvas(event.widget, redraw=False)
        if self.tool.get() == "window_sync":
            # Preview only. Do not mutate any pane while the mouse is moving.
            self._capture_sync_candidate(event)
            return
        super().canvas_drag(event)

    def canvas_release(self, event: tk.Event) -> None:
        if self.tool.get() == "window_sync":
            self._capture_sync_candidate(event)
            self._queue_window_sync()
            return
        super().canvas_release(event)

    def sync_windows_from_event(self, event: tk.Event) -> None:
        """Compatibility entry point: queue a single guarded sync instead of live propagation."""
        self._activate_canvas(event.widget, redraw=False)
        self._capture_sync_candidate(event)
        self._queue_window_sync()

    def _queue_window_sync(self) -> None:
        if self._pending_sync_candidate is None:
            return
        if self._pending_sync_after is not None:
            try:
                self.after_cancel(self._pending_sync_after)
            except tk.TclError:
                pass
        self._pending_sync_after = self.after(SYNC_DELAY_MS, self._apply_pending_window_sync)
        self.update_status("Window Sync queued · views remain unchanged for 1.3 seconds · use Pan or middle-drag to move")

    def _apply_pending_window_sync(self) -> None:
        self._pending_sync_after = None
        target = self._pending_sync_candidate
        if target is None:
            return
        x, y, z = target
        common_zoom = max(2.0, min(160.0, self._pending_sync_zoom))
        self.perspective_distance.set(max(2.0, min(5000.0, 420.0 / common_zoom)))
        for projection, state in self.pane_states.items():
            state.zoom = common_zoom
            if projection == "Top X/Z":
                state.depth = y
                state.pan_x = -x * common_zoom
                state.pan_y = z * common_zoom
            elif projection == "Front X/Y":
                state.depth = z
                state.pan_x = -x * common_zoom
                state.pan_y = y * common_zoom
            elif projection == "Side Z/Y":
                state.depth = x
                state.pan_x = -z * common_zoom
                state.pan_y = y * common_zoom
            else:
                state.depth = 0.0
                state.pan_x = 0.0
                state.pan_y = 0.0
        self.np_target = target
        active = self.pane_states[self.active_projection]
        self._syncing_depth = True
        self.depth_value.set(active.depth)
        self.zoom.set(active.zoom)
        self._syncing_depth = False
        self._pending_sync_candidate = None
        self._pending_sync_projection = None
        self._sync_drag_origin = None
        self.redraw()
        self.schedule_layout_save()
        self.update_status(f"Window Sync applied once at x {x:.2f}, y {y:.2f}, z {z:.2f}")

    # ---------- reset and framing ----------
    def prompt_reset_viewports(self) -> None:
        if messagebox.askyesno(
            "Reset viewports",
            "Return every X/Y/Z/NP pane to a safe centered view?\n\nThis changes only viewport navigation, not asset points.",
            parent=self,
        ):
            self.reset_viewports()

    def reset_viewports(self, *, announce: bool = True) -> None:
        self._cancel_pending_sync()
        lower, upper = self.document.bounds()
        center = tuple((lower[index] + upper[index]) * 0.5 for index in range(3))
        extents = tuple(max(1.0, upper[index] - lower[index]) for index in range(3))
        pane_by_projection = {projection: canvas for canvas, projection in self.canvas_projection.items()}
        for projection, state in self.pane_states.items():
            canvas = pane_by_projection.get(projection)
            width = max(320.0, float(canvas.winfo_width())) if canvas is not None else 640.0
            height = max(240.0, float(canvas.winfo_height())) if canvas is not None else 480.0
            if projection == "Top X/Z":
                size_h, size_v = extents[0], extents[2]
                state.depth = center[1]
                horizontal, vertical = center[0], center[2]
            elif projection == "Front X/Y":
                size_h, size_v = extents[0], extents[1]
                state.depth = center[2]
                horizontal, vertical = center[0], center[1]
            elif projection == "Side Z/Y":
                size_h, size_v = extents[2], extents[1]
                state.depth = center[0]
                horizontal, vertical = center[2], center[1]
            else:
                state.depth = 0.0
                state.zoom = DEFAULT_ZOOM
                state.pan_x = 0.0
                state.pan_y = 0.0
                continue
            state.zoom = max(2.0, min(160.0, 0.72 * min(width / size_h, height / size_v)))
            state.pan_x = -horizontal * state.zoom
            state.pan_y = vertical * state.zoom
        self.np_target = center
        max_extent = max(extents)
        self.perspective_distance.set(max(14.0, min(5000.0, max_extent * 2.1)))
        active = self.pane_states[self.active_projection]
        self._syncing_depth = True
        self.depth_value.set(active.depth)
        self.zoom.set(active.zoom)
        self._syncing_depth = False
        self.redraw()
        self.schedule_layout_save()
        if announce:
            self.update_status("Viewports reset and framed safely · asset geometry was not changed")

    def frame_all(self) -> None:
        self.reset_viewports(announce=True)

    def new_document(self) -> None:
        if not self.confirm_discard():
            return
        selector = tk.Toplevel(self)
        selector.title("New Point Cloud Paint++ asset")
        kind = tk.StringVar(value="environment_object")
        ttk.Label(selector, text="Environment type", font=("Sans", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        box = ttk.Combobox(selector, textvariable=kind, values=branch2.ENVIRONMENT_TYPES, state="readonly", width=28)
        box.pack(fill="x", padx=12)

        def create() -> None:
            self.document = PCPDocument.new(kind.get())
            self.project_path = None
            self.history.clear()
            self.future.clear()
            self.push_history("New document")
            self._sync_all_from_document()
            self.reset_viewports(announce=False)
            selector.destroy()
            self.update_status("New asset created · viewport navigation reset to safe defaults")

        ttk.Button(selector, text="Create", command=create).pack(fill="x", padx=12, pady=12)

    def save_workspace_layout(self) -> None:
        # Persist only finite, bounded navigation. A corrupt runtime state can never become permanent again.
        for state in self.pane_states.values():
            state.depth = max(-MAX_SAVED_DEPTH, min(MAX_SAVED_DEPTH, _finite(state.depth)))
            state.zoom = max(2.0, min(400.0, _finite(state.zoom, DEFAULT_ZOOM)))
            state.pan_x = max(-MAX_ABS_PAN, min(MAX_ABS_PAN, _finite(state.pan_x)))
            state.pan_y = max(-MAX_ABS_PAN, min(MAX_ABS_PAN, _finite(state.pan_y)))
        self.np_target = tuple(max(-MAX_SAVED_CENTER, min(MAX_SAVED_CENTER, _finite(item))) for item in self.np_target)
        super().save_workspace_layout()
        path = self.layout_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["schema"] = "pcp3_workspace_v3"
            data["window_sync_mode"] = "buffered_one_shot"
            data["window_sync_delay_ms"] = SYNC_DELAY_MS
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temporary.replace(path)
            self.layout_data = data
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    # ---------- help/status ----------
    def tool_help(self, key: str) -> str:
        if key == "window_sync":
            return (
                "Click or drag to choose one 3D focus point, then release. The views remain unchanged for 1.3 seconds "
                "and synchronize exactly once. Window Sync does not pan; use the Pan tool or middle-drag."
            )
        return super().tool_help(key)

    def update_tool_hud(self) -> None:
        if self.tool.get() != "window_sync":
            self._cancel_pending_sync()
        super().update_tool_hud()
        if self.tool.get() == "window_sync":
            self.update_status("Window Sync: choose a target and release · one guarded sync occurs after 1.3 seconds")

    def on_close(self) -> None:
        self._cancel_pending_sync()
        super().on_close()


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
