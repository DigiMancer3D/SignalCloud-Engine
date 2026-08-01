from __future__ import annotations

import json
import math
import re
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable


SCHEMA = "scfs_simple_3dbrush_v1"
BRUSH_SIZE_OPTIONS = ("1x1", "4x4", "6x6", "8x8", "9x9")


@dataclass
class SimpleBrush:
    name: str = "Round"
    width: int = 7
    height: int = 7
    pixels: list[list[float]] = field(default_factory=list)

    def normalized(self) -> "SimpleBrush":
        width = max(1, min(33, int(self.width)))
        height = max(1, min(33, int(self.height)))
        rows = []
        for y in range(height):
            source = self.pixels[y] if y < len(self.pixels) else []
            rows.append([
                max(0.0, min(1.0, float(source[x] if x < len(source) else 0.0)))
                for x in range(width)
            ])
        return SimpleBrush(self.name or "Untitled", width, height, rows)

    def active_pixels(self) -> list[tuple[int, int, float]]:
        brush = self.normalized()
        cx, cy = (brush.width-1)/2, (brush.height-1)/2
        return [
            (x-round(cx), y-round(cy), alpha)
            for y, row in enumerate(brush.pixels)
            for x, alpha in enumerate(row)
            if alpha > .001
        ]

    def save(self, path: Path) -> Path:
        path = Path(path)
        if path.suffix.lower() != ".scfsbrush":
            path = path.with_suffix(".scfsbrush")
        value = {
            "schema": SCHEMA, "name": self.name, "width": self.width,
            "height": self.height, "pixels": self.normalized().pixels,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    @classmethod
    def load(cls, path: Path) -> "SimpleBrush":
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema", SCHEMA) != SCHEMA:
            raise ValueError("Unsupported +SCFS+ simple brush")
        return cls(
            str(value.get("name", "Untitled")), int(value.get("width", 7)),
            int(value.get("height", 7)), value.get("pixels", []),
        ).normalized()

    @classmethod
    def round(cls, size: int = 7, soft: bool = False) -> "SimpleBrush":
        center = (size-1)/2
        radius = max(1.0, center)
        pixels = []
        for y in range(size):
            row = []
            for x in range(size):
                distance = math.hypot(x-center, y-center)/radius
                row.append(max(0, 1-distance) if soft else float(distance <= 1.0))
            pixels.append(row)
        return cls("Round Soft" if soft else "Round Solid", size, size, pixels)

    @classmethod
    def square(cls, size: int = 5) -> "SimpleBrush":
        return cls("Square Solid", size, size, [[1.0]*size for _ in range(size)])

    @classmethod
    def cross(cls, size: int = 7) -> "SimpleBrush":
        center = size//2
        return cls("Cross", size, size, [
            [1.0 if x == center or y == center else 0.0 for x in range(size)]
            for y in range(size)
        ])

    @classmethod
    def blank(cls, size_text: str, name: str = "") -> "SimpleBrush":
        if size_text not in BRUSH_SIZE_OPTIONS:
            raise ValueError(f"Unsupported new brush size: {size_text}")
        width_text, height_text = size_text.split("x", 1)
        width, height = int(width_text), int(height_text)
        return cls(
            name.strip() or f"Untitled {size_text}", width, height,
            [[0.0]*width for _ in range(height)],
        )


PREMADES = {
    "Single Dot": SimpleBrush("Single Dot", 1, 1, [[1.0]]),
    "Round Solid": SimpleBrush.round(),
    "Round Soft": SimpleBrush.round(9, True),
    "Square Solid": SimpleBrush.square(),
    "Cross": SimpleBrush.cross(),
}


class SimpleBrushEditor(ttk.Frame):
    def __init__(self, master: tk.Misc, root_path: Path, brush: SimpleBrush,
                 on_apply: Callable[[SimpleBrush], None]) -> None:
        super().__init__(master, padding=6)
        self.root_path = Path(root_path)
        self.brush = brush.normalized()
        self.on_apply = on_apply
        self.active_alpha = tk.DoubleVar(value=1.0)
        self.erase = tk.BooleanVar(value=False)
        self.new_size = tk.StringVar(value="4x4")
        self._strength_hide_job: str | None = None
        self._strength_mouse_active = False
        self._build()
        self.draw()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(bar, text="SIMPLE 3D BRUSH EDITOR", font=("Sans", 11, "bold")).pack(side="left")
        ttk.Button(bar, text="New", command=self.new).pack(side="left", padx=(12, 2))
        ttk.Label(bar, text="Size").pack(side="left", padx=(3, 2))
        self.size_picker = ttk.Combobox(
            bar, values=BRUSH_SIZE_OPTIONS, textvariable=self.new_size,
            state="readonly", width=5, style="SCFS.TCombobox",
        )
        self.size_picker.pack(side="left", padx=(0, 3))
        ttk.Button(bar, text="Load", command=self.load).pack(side="left", padx=(0, 2))
        ttk.Button(bar, text="Save", command=self.save).pack(side="left")
        ttk.Button(bar, text="Apply", command=self.apply).pack(side="left", padx=2)
        ttk.Label(bar, text="Premade").pack(side="left", padx=(12, 3))
        self.premade = ttk.Combobox(
            bar, values=list(PREMADES), state="readonly", width=14,
            style="SCFS.TCombobox",
        )
        self.premade.set(self.brush.name if self.brush.name in PREMADES else "Single Dot")
        self.premade.pack(side="left")
        self.premade.bind("<<ComboboxSelected>>", self.select_premade)
        ttk.Button(bar, text="Rename", command=self.rename).pack(side="right")

        controls = ttk.Frame(self)
        controls.grid(row=1, column=0, sticky="ns", padx=(0, 6))
        ttk.Label(controls, text="Paint strength").pack(anchor="w")
        self.strength_scale = ttk.Scale(
            controls, from_=0.05, to=1, variable=self.active_alpha,
            orient="vertical", command=self.strength_changed,
        )
        self.strength_scale.pack(fill="y", expand=True)
        self.strength_popup = tk.Label(
            self, text="1.00", bg="#eefcff", fg="#102127",
            bd=1, relief="solid", padx=5, pady=2,
        )
        self.strength_scale.bind("<ButtonPress-1>", self.strength_pointer)
        self.strength_scale.bind("<B1-Motion>", self.strength_pointer)
        self.strength_scale.bind("<ButtonRelease-1>", self.strength_release)
        self.strength_scale.bind("<KeyPress>", lambda _e: self.show_strength(use_pointer=False))
        self.strength_scale.bind("<KeyRelease>", lambda _e: self.hide_strength_later())
        ttk.Checkbutton(controls, text="Erase", variable=self.erase).pack(anchor="w")
        ttk.Button(controls, text="Clear", command=self.clear).pack(fill="x", pady=(4, 0))
        ttk.Label(
            controls, text="Single-layer brush mask.\nLeft-drag paints cells.",
            foreground="#78929b", justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self.canvas = tk.Canvas(self, bg="#081015", height=190, highlightthickness=0)
        self.canvas.grid(row=1, column=1, sticky="nsew")
        self.canvas.bind("<Button-1>", self.paint)
        self.canvas.bind("<B1-Motion>", self.paint)
        self.canvas.bind("<Configure>", lambda _e: self.draw())

    def cell(self, event: tk.Event) -> tuple[int, int]:
        cell = max(8, min(26, min(
            max(1, self.canvas.winfo_width())//self.brush.width,
            max(1, self.canvas.winfo_height())//self.brush.height,
        )))
        ox = (self.canvas.winfo_width()-cell*self.brush.width)//2
        oy = (self.canvas.winfo_height()-cell*self.brush.height)//2
        return (event.x-ox)//cell, (event.y-oy)//cell

    def paint(self, event: tk.Event) -> None:
        x, y = self.cell(event)
        if 0 <= x < self.brush.width and 0 <= y < self.brush.height:
            self.brush.pixels[y][x] = 0.0 if self.erase.get() else self.active_alpha.get()
            self.draw()

    def draw(self) -> None:
        self.canvas.delete("all")
        cell = max(8, min(26, min(
            max(1, self.canvas.winfo_width())//self.brush.width,
            max(1, self.canvas.winfo_height())//self.brush.height,
        )))
        ox = (self.canvas.winfo_width()-cell*self.brush.width)//2
        oy = (self.canvas.winfo_height()-cell*self.brush.height)//2
        for y, row in enumerate(self.brush.pixels):
            for x, alpha in enumerate(row):
                shade = round(24 + alpha*210)
                color = f"#{round(shade*.4):02x}{round(shade*.88):02x}{shade:02x}"
                self.canvas.create_rectangle(
                    ox+x*cell, oy+y*cell, ox+(x+1)*cell, oy+(y+1)*cell,
                    fill=color, outline="#27404a",
                )

    def select_premade(self, _event=None) -> None:
        self.brush = SimpleBrush.load_from(PREMADES[self.premade.get()])
        self.draw()

    def new(self) -> None:
        size_text = self.new_size.get()
        if size_text not in BRUSH_SIZE_OPTIONS:
            size_text = "4x4"
        name = simpledialog.askstring(
            "+SCFS+ New Brush", f"Name for the new {size_text} brush:",
            initialvalue=f"Untitled {size_text}", parent=self,
        )
        if name is None:
            return
        self.brush = SimpleBrush.blank(size_text, name)
        self.premade.set("")
        self.erase.set(False)
        self.draw()

    def strength_changed(self, _value=None) -> None:
        self.show_strength(use_pointer=self._strength_mouse_active)
        self.hide_strength_later()

    def strength_pointer(self, event: tk.Event) -> None:
        self._strength_mouse_active = True
        self.show_strength(pointer_x=event.x_root, use_pointer=True)

    def strength_release(self, _event: tk.Event) -> None:
        self._strength_mouse_active = False
        self.hide_strength_later()

    def show_strength(self, pointer_x: int | None = None, *,
                      use_pointer: bool = False) -> None:
        self.update_idletasks()
        self.strength_popup.configure(text=f"{self.active_alpha.get():.2f}")
        self.strength_popup.update_idletasks()
        screen_center = self.winfo_screenwidth()/2
        if use_pointer and pointer_x is None:
            try:
                pointer_x = self.winfo_pointerx()
            except tk.TclError:
                pointer_x = None
        scale_left = self.strength_scale.winfo_rootx()
        scale_right = scale_left+self.strength_scale.winfo_width()
        popup_width = self.strength_popup.winfo_reqwidth()
        # Place away from the pointer. With no meaningful pointer position,
        # choose the side toward the physical center of the screen.
        if use_pointer and pointer_x is not None:
            use_right = pointer_x <= (scale_left+scale_right)/2
        else:
            use_right = scale_right <= screen_center
        if use_right:
            root_x = scale_right+7
        else:
            root_x = scale_left-popup_width-7
        root_y = (
            self.strength_scale.winfo_rooty()
            + self.strength_scale.winfo_height()/2
            - self.strength_popup.winfo_reqheight()/2
        )
        self.strength_popup.place(
            x=round(root_x-self.winfo_rootx()),
            y=round(root_y-self.winfo_rooty()),
        )
        self.strength_popup.lift()

    def hide_strength_later(self) -> None:
        if self._strength_hide_job:
            self.after_cancel(self._strength_hide_job)
        self._strength_hide_job = self.after(1200, self.strength_popup.place_forget)

    def load(self) -> None:
        value = filedialog.askopenfilename(
            parent=self, filetypes=[("+SCFS+ Simple Brush", "*.scfsbrush")],
        )
        if value:
            try:
                self.brush = SimpleBrush.load(Path(value))
                self.draw()
            except Exception as exc:
                messagebox.showerror("+SCFS+ Brush", str(exc), parent=self)

    def save(self) -> None:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", self.brush.name).strip("._") or "brush"
        value = filedialog.asksaveasfilename(
            parent=self, defaultextension=".scfsbrush", initialfile=safe+".scfsbrush",
            filetypes=[("+SCFS+ Simple Brush", "*.scfsbrush")],
        )
        if value:
            self.brush.save(Path(value))

    def apply(self) -> None:
        self.on_apply(self.brush.normalized())

    def rename(self) -> None:
        value = simpledialog.askstring("+SCFS+ Brush", "Brush name:", initialvalue=self.brush.name, parent=self)
        if value:
            self.brush.name = value

    def clear(self) -> None:
        self.brush.pixels = [[0.0]*self.brush.width for _ in range(self.brush.height)]
        self.draw()


def _load_from(brush: SimpleBrush) -> SimpleBrush:
    return SimpleBrush(brush.name, brush.width, brush.height, [row[:] for row in brush.pixels])


SimpleBrush.load_from = staticmethod(_load_from)  # compact copy helper for premades
