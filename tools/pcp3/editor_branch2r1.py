from __future__ import annotations

import json
import math
import os
import random
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Iterable

import tkinter as tk
from tkinter import messagebox

from tools.pcp3 import editor_branch2 as branch2
from tools.pcp3.model import PCPPoint, primitive_box, primitive_cylinder, primitive_sphere


VIEWPORT_TOTAL_ITEM_BUDGET = 6_000
MAX_POINTS_PER_GENERATOR = 200_000
MAX_INTERACTIVE_DOCUMENT_POINTS = 1_500_000
MAX_UNDO_SNAPSHOT_POINTS = 300_000
MAX_STROKE_ADDITIONS = 50_000
MAX_PATH_SAMPLES_PER_EVENT = 48
MAX_NATIVE_COMMANDS_PER_POLL = 12
MAX_NATIVE_POINTS_PER_SAMPLE = 256
NATIVE_COMMAND_ROTATE_BYTES = 256 * 1024


def estimate_shape_points(shape: str, values: dict[str, float]) -> int:
    spacing = max(0.05, float(values.get("spacing", 0.12)))
    if shape == "box":
        sx = max(0.01, float(values.get("size_x", 1.0)))
        sy = max(0.01, float(values.get("size_y", 1.0)))
        sz = max(0.01, float(values.get("size_z", 1.0)))
        nx = max(2, int(math.ceil(sx / spacing)) + 1)
        ny = max(2, int(math.ceil(sy / spacing)) + 1)
        nz = max(2, int(math.ceil(sz / spacing)) + 1)
        return 2 * (nx * ny + nx * nz + ny * nz)
    radius = max(0.05, float(values.get("radius", 1.0)))
    if shape == "sphere":
        return max(24, int(4.0 * math.pi * radius * radius / (spacing * spacing)))
    height = max(0.05, float(values.get("height", 2.0)))
    ring_count = max(12, int(math.ceil(2.0 * math.pi * radius / spacing)))
    vertical_count = max(2, int(math.ceil(height / spacing)) + 1)
    radial_count = max(2, int(math.ceil(radius / spacing)) + 1)
    cap_estimate = 0
    for index in range(radial_count):
        cap_radius = radius * index / max(1, radial_count - 1)
        cap_estimate += 1 if index == 0 else max(8, int(math.ceil(2.0 * math.pi * cap_radius / spacing)))
    return ring_count * vertical_count + 2 * cap_estimate


def safe_spacing_for_limit(shape: str, values: dict[str, float], limit: int = MAX_POINTS_PER_GENERATOR) -> float:
    spacing = max(0.05, float(values.get("spacing", 0.12)))
    estimate = estimate_shape_points(shape, values)
    if estimate <= limit:
        return spacing
    # These generators create surfaces, so count scales approximately with 1/spacing^2.
    return spacing * math.sqrt(estimate / max(1, limit)) * 1.03


class PCP3Editor(branch2.PCP3Editor):
    """Branch 2 repair: bounded viewport/brush work, crash logging, and queue recovery."""

    def __init__(self, root_path: Path) -> None:
        self.viewport_total_item_budget = VIEWPORT_TOTAL_ITEM_BUDGET
        self.stroke_points_added = 0
        self.history_suspended_for_size = False
        self.last_viewport_sample_note = ""
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 2 R1 Safe Repair")
        self.document.metadata["editor_branch"] = "ISL_plus_branch2_R1"
        self._quarantine_stale_native_queue()
        self._install_crash_logging()
        self.update_status("Safe Repair active · bounded multi-view, shapes, brushes, history, and command queue")

    # ---------- diagnostics ----------
    def crash_log_path(self) -> Path:
        return self.root_path / "reports" / "pcp3_crash_latest.log"

    def _install_crash_logging(self) -> None:
        self.root_path.joinpath("reports").mkdir(parents=True, exist_ok=True)

    def report_callback_exception(self, exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        path = self.crash_log_path()
        try:
            path.write_text(
                f"Point Cloud Paint++ callback failure\nEpoch: {time.time():.6f}\n\n{text}",
                encoding="utf-8",
            )
        except OSError:
            pass
        try:
            messagebox.showerror(
                "Point Cloud Paint++ recovered an error",
                f"The failing action was stopped.\n\nCrash log:\n{path}\n\n{text[-1200:]}",
                parent=self,
            )
        except tk.TclError:
            pass

    # ---------- bounded history ----------
    def _history_limit(self) -> int:
        count = len(self.document.points)
        if count <= 50_000:
            return 30
        if count <= 150_000:
            return 12
        if count <= MAX_UNDO_SNAPSHOT_POINTS:
            return 5
        return 1

    def push_history(self, label: str) -> None:
        count = len(self.document.points)
        self.future.clear()
        if count > MAX_UNDO_SNAPSHOT_POINTS:
            self.history_suspended_for_size = True
            self.history[:] = [{
                "label": f"{label} · undo paused above {MAX_UNDO_SNAPSHOT_POINTS:,} points",
                "snapshot": None,
            }]
        else:
            self.history_suspended_for_size = False
            self.history.append({"label": label, "snapshot": self.document.snapshot()})
            limit = self._history_limit()
            if len(self.history) > limit:
                del self.history[:-limit]
        self.refresh_history()

    def finish_edit(self, label: str) -> None:
        self.document.dirty = True
        count = len(self.document.points)
        if not self.history:
            self.push_history(label)
        elif count > MAX_UNDO_SNAPSHOT_POINTS:
            self.history_suspended_for_size = True
            self.history[:] = [{
                "label": f"{label} · undo paused above {MAX_UNDO_SNAPSHOT_POINTS:,} points",
                "snapshot": None,
            }]
        else:
            self.history_suspended_for_size = False
            self.history[-1] = {"label": label, "snapshot": self.document.snapshot()}
            limit = self._history_limit()
            if len(self.history) > limit:
                del self.history[:-limit]
        self.refresh_history()
        self.redraw()
        self.refresh_layers()
        self.update_status(label)
        self.schedule_live_preview()

    def undo(self) -> None:
        if not self.history or self.history[-1].get("snapshot") is None:
            self.update_status(
                f"Undo is paused above {MAX_UNDO_SNAPSHOT_POINTS:,} points to prevent memory exhaustion"
            )
            return
        super().undo()

    def redo(self) -> None:
        if self.future and self.future[-1].get("snapshot") is None:
            self.update_status("Redo is unavailable for a memory-protected large-document edit")
            return
        super().redo()

    # ---------- bounded viewport ----------
    def _sample_visible_points(self, limit: int) -> list[tuple[int, PCPPoint]]:
        total = len(self.document.points)
        if total == 0:
            return []
        visible_layers = {layer.id for layer in self.document.layers if layer.visible}
        stride = max(1, int(math.ceil(total / max(1, limit))))
        sampled: list[tuple[int, PCPPoint]] = []
        for index in range(0, total, stride):
            point = self.document.points[index]
            if point.layer_id in visible_layers:
                sampled.append((index, point))
                if len(sampled) >= limit:
                    break
        # Keep selected points visible when possible without allowing an unbounded overlay.
        selected_extra = 0
        present = {index for index, _point in sampled}
        for index in sorted(self.document.selected_indices):
            if selected_extra >= 500 or index in present or index >= total:
                continue
            point = self.document.points[index]
            if point.layer_id in visible_layers:
                sampled.append((index, point))
                selected_extra += 1
        return sampled

    def redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        panes = self.panes()
        pane_count = max(1, len(panes))
        per_pane_budget = max(3_000, self.viewport_total_item_budget // pane_count)
        points = self._sample_visible_points(per_pane_budget)
        layer_map = {layer.id: layer for layer in self.document.layers}
        mode = self.display_mode.get()
        total_points = len(self.document.points)
        self.last_viewport_sample_note = (
            f"viewport {len(points):,}/{total_points:,} points per pane"
            if total_points > len(points)
            else f"viewport {total_points:,} points"
        )
        for pane in panes:
            self.active_event_pane = pane
            self.canvas.create_rectangle(
                pane.x,
                pane.y,
                pane.x + pane.width,
                pane.y + pane.height,
                fill="#0f1418" if pane.projection != "Perspective 3D" else "#080c10",
                outline="#4b5961",
                width=1,
            )
            self.draw_grid(pane)
            pane_points = points
            if pane.projection == "Perspective 3D":
                pane_points = sorted(points, key=lambda item: self.point_depth(item[1], pane), reverse=True)
            for index, point in pane_points:
                layer = layer_map.get(point.layer_id)
                if layer is None:
                    continue
                sx, sy = self.world_to_screen(point, pane)
                if not pane.contains(sx, sy):
                    continue
                if pane.projection == "Perspective 3D":
                    fade = max(0.18, min(1.0, 18.0 / max(1.0, self.point_depth(point, pane))))
                else:
                    depth_delta = abs(self.point_depth(point, pane) - self.depth_value.get())
                    max_depth_delta = max(0.2, self.brush_size.get() * 1.5)
                    fade = max(0.12, 1.0 - depth_delta / max_depth_delta)
                color = self.point_display_color(point, layer, mode, fade)
                size = max(1.0, min(9.0, point.radius * 0.65 * self.document.settings.point_scale))
                outline = "#ffffff" if index in self.document.selected_indices else ""
                self.canvas.create_oval(
                    sx - size,
                    sy - size,
                    sx + size,
                    sy + size,
                    fill=color,
                    outline=outline,
                    width=1,
                )
            self.draw_canvas_bounds(pane)
            self.canvas.create_text(
                pane.x + 8,
                pane.y + 8,
                text=pane.name,
                anchor="nw",
                fill="#a9c4d2",
                font=("Sans", 9, "bold"),
            )
            if pane.projection == "Perspective 3D":
                self.canvas.create_text(
                    pane.x + 8,
                    pane.y + 25,
                    text="Safe perspective bridge · F5 native renderer · B native brush",
                    anchor="nw",
                    fill="#6f8793",
                    font=("Sans", 8),
                )
        self.active_event_pane = None
        self.draw_interaction_overlays()
        self.canvas.create_text(
            8,
            max(8, self.canvas.winfo_height() - 8),
            text=self.last_viewport_sample_note,
            anchor="sw",
            fill="#71838d",
            font=("Sans", 8),
        )

    # ---------- bounded shape generation ----------
    def generate_shape_from_values(self, shape: str, values: dict[str, float]) -> None:
        adjusted = dict(values)
        estimate = estimate_shape_points(shape, adjusted)
        remaining = max(0, MAX_INTERACTIVE_DOCUMENT_POINTS - len(self.document.points))
        allowed = min(MAX_POINTS_PER_GENERATOR, remaining)
        if allowed <= 0:
            messagebox.showwarning(
                "Interactive point limit reached",
                f"This editor repair caps an interactive document at {MAX_INTERACTIVE_DOCUMENT_POINTS:,} points. "
                "Export the current asset or reduce existing points before adding more.",
                parent=self,
            )
            return
        if estimate > allowed:
            safer = safe_spacing_for_limit(shape, adjusted, allowed)
            accepted = messagebox.askyesno(
                "Shape density reduced for safety",
                f"The requested {shape} is estimated to create {estimate:,} points.\n\n"
                f"For this operation the safe limit is {allowed:,} points.\n"
                f"Increase spacing from {adjusted['spacing']:.4f} to approximately {safer:.4f} and continue?",
                parent=self,
            )
            if not accepted:
                self.update_status("Shape generation cancelled before unsafe allocation")
                return
            adjusted["spacing"] = safer
        self.push_history(f"Generate {shape}")
        center = (adjusted["center_x"], adjusted["center_y"], adjusted["center_z"])
        common = (
            self.document.active_layer_id,
            self.current_color(),
            self.point_radius.get(),
            self.semantic.get(),
        )
        spacing = max(0.05, adjusted["spacing"])
        if shape == "box":
            points = primitive_box(
                center,
                (adjusted["size_x"], adjusted["size_y"], adjusted["size_z"]),
                spacing,
                *common,
            )
        elif shape == "sphere":
            points = primitive_sphere(center, adjusted["radius"], spacing, *common)
        else:
            points = primitive_cylinder(center, adjusted["radius"], adjusted["height"], spacing, *common)
        if len(points) > allowed:
            stride = max(1, int(math.ceil(len(points) / allowed)))
            points = points[::stride][:allowed]
        self.document.add_points(points)
        self.finish_edit(f"{shape.title()} generated safely ({len(points):,} points)")

    # ---------- bounded strokes ----------
    def canvas_press(self, event: tk.Event) -> None:
        if self.tool.get() in {"pencil", "brush"}:
            self.stroke_points_added = 0
        super().canvas_press(event)

    @staticmethod
    def _limit_samples(samples: list[tuple[float, float, float]], limit: int) -> list[tuple[float, float, float]]:
        if len(samples) <= limit:
            return samples
        stride = len(samples) / float(limit)
        return [samples[min(len(samples) - 1, int(index * stride))] for index in range(limit)]

    def apply_tool(self, world: tuple[float, float, float], first: bool) -> None:
        tool = self.tool.get()
        layer = self.document.active_layer()
        if layer.locked:
            self.update_status("Active layer is locked")
            return
        positions = [world]
        if self.stroke_last_world is not None and tool in {"pencil", "brush", "eraser", "recolor"}:
            spacing = max(0.02, min(self.brush_spacing.get(), 1.25 / max(2.0, self.zoom.get())))
            positions = branch2.resample_polyline([self.stroke_last_world, world], spacing)[1:]
            if not positions:
                positions = [world]
        positions = self._limit_samples(positions, MAX_PATH_SAMPLES_PER_EVENT)
        for position in positions:
            if tool == "pencil":
                if self.stroke_points_added >= MAX_STROKE_ADDITIONS:
                    break
                self.document.add_point(self.make_point(*position))
                self.stroke_points_added += 1
            elif tool == "brush":
                if self.stroke_points_added >= MAX_STROKE_ADDITIONS:
                    break
                generated = self.brush_points(position)
                remaining = MAX_STROKE_ADDITIONS - self.stroke_points_added
                if len(generated) > remaining:
                    stride = max(1, int(math.ceil(len(generated) / remaining))) if remaining else 1
                    generated = generated[::stride][:remaining]
                self.document.add_points(generated)
                self.stroke_points_added += len(generated)
            elif tool == "eraser":
                self.document.erase_sphere(*position, self.brush_size.get(), active_layer_only=False)
            elif tool == "recolor":
                self.document.recolor_sphere(*position, self.brush_size.get(), self.current_color())
        if self.stroke_points_added >= MAX_STROKE_ADDITIONS and tool in {"pencil", "brush"}:
            self.update_status(
                f"Stroke capped at {MAX_STROKE_ADDITIONS:,} new points to protect the desktop"
            )
        self.stroke_last_world = world
        self.request_redraw()
        self.update_status()

    def brush_points_3d(self, world: tuple[float, float, float]) -> list[PCPPoint]:
        spacing = max(0.05, self.brush_spacing.get())
        radius = max(spacing, self.brush_size.get())
        area_estimate = max(24, int(4.0 * math.pi * radius * radius / (spacing * spacing)))
        count = min(MAX_NATIVE_POINTS_PER_SAMPLE, area_estimate)
        hardness = max(0.0, min(1.0, self.brush_hardness.get()))
        golden = math.pi * (3.0 - math.sqrt(5.0))
        points: list[PCPPoint] = []
        for index in range(count):
            y_norm = 1.0 - 2.0 * (index + 0.5) / count
            ring = math.sqrt(max(0.0, 1.0 - y_norm * y_norm))
            angle = golden * index
            shell = radius * (hardness + (1.0 - hardness) * ((index % 7) + 1) / 7.0)
            offset = (math.cos(angle) * ring * shell, y_norm * shell, math.sin(angle) * ring * shell)
            points.append(self.make_point(world[0] + offset[0], world[1] + offset[1], world[2] + offset[2]))
        return points

    # ---------- native command queue ----------
    def _quarantine_stale_native_queue(self) -> None:
        path = self.native_brush_command_path()
        if not path.exists() or path.stat().st_size == 0:
            return
        stale_dir = path.parent / "stale_commands"
        stale_dir.mkdir(parents=True, exist_ok=True)
        destination = stale_dir / f"native_brush_commands_{int(time.time())}.jsonl"
        try:
            path.replace(destination)
            path.write_text("", encoding="utf-8")
            self.preview_command_offset = 0
        except OSError:
            try:
                path.write_text("", encoding="utf-8")
            except OSError:
                pass

    @staticmethod
    def _compact_native_commands(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compacted: list[dict[str, Any]] = []
        for command in commands:
            if not compacted:
                compacted.append(command)
                continue
            previous = compacted[-1]
            distance_sq = sum((float(command[key]) - float(previous[key])) ** 2 for key in ("x", "y", "z"))
            if command.get("action") != previous.get("action") or distance_sq >= 0.0025:
                compacted.append(command)
        if len(compacted) <= MAX_NATIVE_COMMANDS_PER_POLL:
            return compacted
        stride = len(compacted) / float(MAX_NATIVE_COMMANDS_PER_POLL)
        return [compacted[min(len(compacted) - 1, int(index * stride))] for index in range(MAX_NATIVE_COMMANDS_PER_POLL)]

    def poll_native_brush_commands(self) -> None:
        path = self.native_brush_command_path()
        if path.exists():
            try:
                size = path.stat().st_size
                if size < self.preview_command_offset:
                    self.preview_command_offset = 0
                if size > self.preview_command_offset:
                    with path.open("r", encoding="utf-8") as handle:
                        handle.seek(self.preview_command_offset)
                        lines = handle.readlines()
                        self.preview_command_offset = handle.tell()
                    raw_commands: list[dict[str, Any]] = []
                    for line in lines:
                        try:
                            command = json.loads(line)
                            if all(key in command for key in ("action", "x", "y", "z")):
                                raw_commands.append(command)
                        except (json.JSONDecodeError, TypeError):
                            continue
                    commands = self._compact_native_commands(raw_commands)
                    if commands:
                        self.push_history("Native 3D brush")
                        total_added = 0
                        for command in commands:
                            world = (float(command["x"]), float(command["y"]), float(command["z"]))
                            if command["action"] == "erase":
                                self.document.erase_sphere(*world, self.brush_size.get(), active_layer_only=False)
                            else:
                                remaining = max(0, MAX_STROKE_ADDITIONS - total_added)
                                if remaining == 0:
                                    break
                                generated = self.brush_points_3d(world)[:remaining]
                                self.document.add_points(generated)
                                total_added += len(generated)
                        self.finish_edit(
                            f"Native 3D brush · {len(commands)} safe sample(s) · {total_added:,} points"
                        )
                if size >= NATIVE_COMMAND_ROTATE_BYTES:
                    archive_dir = path.parent / "processed_commands"
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    archived = archive_dir / f"native_brush_commands_{int(time.time())}.jsonl"
                    try:
                        path.replace(archived)
                        path.write_text("", encoding="utf-8")
                        self.preview_command_offset = 0
                    except OSError:
                        pass
            except OSError:
                pass
        self.preview_poll_after = self.after(160, self.poll_native_brush_commands)


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
