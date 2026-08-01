from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from tkinter import ttk

from .model import FontDocument, Point
from .native_preview_bridge import launch_native_preview


def rotate_xyz(point: tuple[float, float, float], pitch: float, yaw: float,
               roll: float) -> tuple[float, float, float]:
    x, y, z = point
    ax, ay, az = map(math.radians, (pitch, yaw, roll))
    cy, sy = math.cos(ax), math.sin(ax)
    y, z = y*cy-z*sy, y*sy+z*cy
    cx, sx = math.cos(ay), math.sin(ay)
    x, z = x*cx+z*sx, -x*sx+z*cx
    cz, sz = math.cos(az), math.sin(az)
    return x*cz-y*sz, x*sz+y*cz, z


class RenderPreviewWindow(tk.Toplevel):
    """Low-resource adaptation of PCP3's multiview camera projection."""

    def __init__(self, master: tk.Misc, document: FontDocument, preview_text: str,
                 project_root: Path) -> None:
        super().__init__(master)
        self.title("+SCFS+ SignalCloud Engine Render Preview")
        self.geometry("1050x720")
        self.minsize(760, 520)
        self.document = document.clone()
        self.preview_text = preview_text
        self.project_root = Path(project_root)
        self.mode = tk.StringVar(value="Rich")
        self.yaw = tk.DoubleVar(value=-25)
        self.pitch = tk.DoubleVar(value=18)
        self.roll = tk.DoubleVar(value=0)
        self.zoom = tk.DoubleVar(value=23)
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.drag_anchor: tuple[int, int, float, float, float, float] | None = None
        self._build()
        self.render()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        bar = ttk.Frame(self, padding=7)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(bar, text="SIGNALCLOUD ENGINE TEXT PREVIEW", font=("Sans", 12, "bold")).pack(side="left")
        for value in ("Rich", "Simple"):
            ttk.Radiobutton(
                bar, text=value, value=value, variable=self.mode,
                command=self.mode_changed,
            ).pack(side="left", padx=(12 if value == "Rich" else 2, 0))
        ttk.Button(bar, text="Reset View", command=self.reset).pack(side="right")
        ttk.Button(
            bar, text="Open Native PointRenderer", command=self.open_native,
        ).pack(side="right", padx=(0, 4))
        self.readout = ttk.Label(bar)
        self.readout.pack(side="right", padx=12)

        self.canvas = tk.Canvas(self, bg="#03080b", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.vertical_scroll = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview,
        )
        self.vertical_scroll.grid(row=1, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.vertical_scroll.set)
        self.canvas.bind("<Configure>", lambda _e: self.render())
        self.canvas.bind("<ButtonPress-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "drag_anchor", None))
        self.canvas.bind("<ButtonPress-3>", self.pan_start)
        self.canvas.bind("<B3-Motion>", self.pan)
        self.canvas.bind("<ButtonRelease-3>", lambda _e: setattr(self, "drag_anchor", None))
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Button-4>", lambda e: self.linux_wheel(e, -1))
        self.canvas.bind("<Button-5>", lambda e: self.linux_wheel(e, 1))

        controls = ttk.LabelFrame(self, text="Smart view scrubber — drag the block to orbit / tilt / yaw", padding=6)
        controls.grid(row=2, column=0, columnspan=2, sticky="ew", padx=7, pady=7)
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Horizontal view").grid(row=0, column=0, padx=(0, 5))
        self.scrubber = ttk.Scale(
            controls, from_=-180, to=180, variable=self.yaw,
            command=lambda _v: self.render(),
        )
        self.scrubber.grid(row=0, column=1, sticky="ew")
        ttk.Label(
            controls,
            text="Left-drag: yaw + tilt   •   Right-drag: move   •   Wheel: vertical scroll   •   Ctrl+wheel: zoom",
            foreground="#78929b",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

    def mode_changed(self) -> None:
        if self.mode.get() == "Simple":
            self.pitch.set(0)
            self.yaw.set(0)
            self.roll.set(0)
        self.render()
        self.canvas.yview_moveto(0.0)

    def reset(self) -> None:
        self.pan_x = self.pan_y = 0
        if self.mode.get() == "Rich":
            self.pitch.set(18)
            self.yaw.set(-25)
        else:
            self.pitch.set(0)
            self.yaw.set(0)
        self.roll.set(0)
        self.zoom.set(23)
        self.render()
        self.canvas.yview_moveto(0.0)

    def drag_start(self, event: tk.Event) -> None:
        self.drag_anchor = (
            event.x, event.y, self.yaw.get(), self.pitch.get(), self.pan_x, self.pan_y,
        )

    def drag(self, event: tk.Event) -> None:
        if self.drag_anchor and self.mode.get() == "Rich":
            x, y, yaw, pitch, _, _ = self.drag_anchor
            self.yaw.set(yaw+(event.x-x)*.45)
            self.pitch.set(max(-89, min(89, pitch+(event.y-y)*.35)))
            self.render()

    def pan_start(self, event: tk.Event) -> None:
        self.drag_anchor = (
            event.x, event.y, self.yaw.get(), self.pitch.get(), self.pan_x, self.pan_y,
        )

    def pan(self, event: tk.Event) -> None:
        if self.drag_anchor:
            x, y, _, _, pan_x, pan_y = self.drag_anchor
            self.pan_x, self.pan_y = pan_x+event.x-x, pan_y+event.y-y
            self.render()

    def wheel(self, event: tk.Event) -> None:
        if event.state & 0x0004:
            self.zoom_step(1.08 if event.delta > 0 else .92)
            return
        direction = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(direction * 3, "units")

    def linux_wheel(self, event: tk.Event, direction: int) -> None:
        if event.state & 0x0004:
            self.zoom_step(1.08 if direction < 0 else .92)
            return
        self.canvas.yview_scroll(direction * 3, "units")

    def zoom_step(self, multiplier: float) -> None:
        self.zoom.set(max(4, min(90, self.zoom.get()*multiplier)))
        self.render()

    def maximum_text_width(self, canvas_width: int) -> float:
        if self.mode.get() == "Simple":
            margin = max(28.0, canvas_width * .08)
            horizontal_padding = margin + 22.0
        else:
            horizontal_padding = max(72.0, canvas_width * .08)
        available_pixels = max(80.0, canvas_width - horizontal_padding * 2.0)
        return max(1.0, available_pixels / self.zoom.get())

    def wrapped_preview_text(self, canvas_width: int | None = None) -> str:
        width = canvas_width if canvas_width is not None else max(240, self.canvas.winfo_width())
        return self.document.wrap_text(
            self.preview_text, self.maximum_text_width(width),
        )

    def source_points(self, canvas_width: int | None = None) -> list[tuple[float, float, Point, int, int]]:
        return self.document.layout(self.wrapped_preview_text(canvas_width))

    def render(self) -> None:
        previous_y = self.canvas.yview()[0]
        self.canvas.delete("all")
        width = max(240, self.canvas.winfo_width())
        viewport_height = max(180, self.canvas.winfo_height())
        wrapped_text = self.wrapped_preview_text(width)
        line_count = max(1, wrapped_text.count("\n") + 1)
        source = self.document.layout(wrapped_text)
        source_positions = [
            (offset_x + point.x, offset_y + point.y, point, code, layer)
            for offset_x, offset_y, point, code, layer in source
        ]
        if source_positions:
            minimum_x = min(item[0] for item in source_positions)
            maximum_x = max(item[0] for item in source_positions)
            minimum_y = min(item[1] for item in source_positions)
        else:
            minimum_x = maximum_x = minimum_y = 0.0
        pivot_x = (minimum_x + maximum_x) * .5
        text_top = max(96.0, viewport_height * .22)
        points = []
        for x, y, point, _, _ in source_positions:
            z = point.z if self.mode.get() == "Rich" else 0.0
            rx, ry, rz = rotate_xyz(
                (x - pivot_x, y - minimum_y, z),
                self.pitch.get() if self.mode.get() == "Rich" else 0,
                self.yaw.get() if self.mode.get() == "Rich" else 0,
                self.roll.get() if self.mode.get() == "Rich" else 0,
            )
            distance = 36.0
            perspective = distance/max(4.0, distance+rz) if self.mode.get() == "Rich" else 1.0
            sx = width/2+self.pan_x+rx*self.zoom.get()*perspective
            sy = text_top+self.pan_y+ry*self.zoom.get()*perspective
            points.append((rz, sx, sy, point, perspective))

        expected_bottom = (
            text_top
            + line_count * self.document.metrics.line_height * self.zoom.get()
            + 48.0
        )
        point_bottom = max(
            (sy + max(1.2, 3.6 * point.alpha * perspective) + 48.0
             for _, _, sy, point, perspective in points),
            default=0.0,
        )
        content_height = max(float(viewport_height), expected_bottom, point_bottom)
        self.canvas.create_rectangle(
            0, 0, width, content_height, fill="#03080b", outline="",
        )
        if self.mode.get() == "Simple":
            self.draw_menu_shell(width, viewport_height, content_height)
        else:
            self.draw_world_grid(width, viewport_height, content_height)

        for _, sx, sy, point, perspective in sorted(
            points, key=lambda item: item[0], reverse=True,
        ):
            radius = max(1.2, 3.6*point.alpha*perspective)
            self.canvas.create_oval(
                sx-radius, sy-radius, sx+radius, sy+radius,
                fill=point.color, outline="",
            )
        self.canvas.configure(scrollregion=(0, 0, width, content_height))
        self.canvas.yview_moveto(previous_y)
        self.readout.configure(
            text=(
                f"{self.mode.get()} · lines {line_count:,} · points {len(points):,}"
                f" · yaw {self.yaw.get():.1f}° · pitch {self.pitch.get():.1f}°"
            )
        )

    def open_native(self) -> None:
        try:
            launch_native_preview(
                self.project_root, self.document, self.wrapped_preview_text(),
                simple=self.mode.get() == "Simple",
            )
        except Exception as exc:
            messagebox.showerror(
                "+SCFS+ Native PointRenderer",
                f"{exc}\n\nThe built-in engine-style preview remains available in this window.",
                parent=self,
            )

    def draw_world_grid(self, width: int, viewport_height: int, content_height: float) -> None:
        horizon = viewport_height*.72+self.pan_y
        for index in range(-8, 9):
            x = width/2+self.pan_x+index*60
            self.canvas.create_line(
                width/2+self.pan_x, horizon-40, x, content_height, fill="#10272f",
            )
        for index in range(8):
            y = horizon+(index*index)*5
            self.canvas.create_line(0, y, width, y, fill="#10272f")
        self.canvas.create_text(16, 16, text="RICH · WORLD-SPACE 3D SIGNALCLOUD TEXT", fill="#45d8ef", anchor="nw")

    def draw_menu_shell(self, width: int, viewport_height: int, content_height: float) -> None:
        margin = max(28, width*.08)
        top = viewport_height*.15
        bottom = max(viewport_height*.85, content_height-28)
        self.canvas.create_rectangle(
            margin, top, width-margin, bottom,
            fill="#071318", outline="#327587", width=2,
        )
        self.canvas.create_text(
            margin+18, top+16, text="SIMPLE · FLAT GUI / MENU TEXT",
            fill="#45d8ef", anchor="nw",
        )
