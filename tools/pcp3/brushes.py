from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk
from typing import Any, Callable

BRUSH_SCHEMA = "pcp3_3dbrush_v1"
MAX_BRUSH_SIDE = 65
MIN_BRUSH_SIDE = 3


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def safe_brush_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._") or "untitled_brush"
    if not cleaned.lower().endswith(".3dbrush"):
        cleaned += ".3dbrush"
    return cleaned


@dataclass
class BrushLayer:
    name: str
    opacity: float = 1.0
    pixels: list[list[float]] = field(default_factory=list)

    def normalized(self, width: int, height: int) -> "BrushLayer":
        rows: list[list[float]] = []
        for row_index in range(height):
            source = self.pixels[row_index] if row_index < len(self.pixels) else []
            rows.append([_clamp(source[column] if column < len(source) else 0.0) for column in range(width)])
        return BrushLayer(self.name or "Layer", _clamp(self.opacity), rows)


@dataclass
class BrushPreset:
    name: str
    width: int = 17
    height: int = 17
    layers: list[BrushLayer] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "BrushPreset":
        width = max(MIN_BRUSH_SIDE, min(MAX_BRUSH_SIDE, int(self.width)))
        height = max(MIN_BRUSH_SIDE, min(MAX_BRUSH_SIDE, int(self.height)))
        layers = [layer.normalized(width, height) for layer in self.layers] or [BrushLayer("Base", 1.0, [[0.0] * width for _ in range(height)])]
        return BrushPreset(self.name or "Untitled Brush", width, height, layers, dict(self.metadata))

    def composite(self) -> list[list[float]]:
        preset = self.normalized()
        output = [[0.0] * preset.width for _ in range(preset.height)]
        for layer in preset.layers:
            layer_opacity = _clamp(layer.opacity)
            for row in range(preset.height):
                for column in range(preset.width):
                    source = _clamp(layer.pixels[row][column]) * layer_opacity
                    output[row][column] = 1.0 - (1.0 - output[row][column]) * (1.0 - source)
        return output

    def active_pixels(self, limit: int = 1024) -> list[tuple[int, int, float]]:
        values: list[tuple[int, int, float]] = []
        for row_index, row in enumerate(self.composite()):
            for column_index, alpha in enumerate(row):
                if alpha > 0.001:
                    values.append((column_index, row_index, alpha))
        if len(values) <= limit:
            return values
        stride = len(values) / float(limit)
        return [values[min(len(values) - 1, int(index * stride))] for index in range(limit)]

    def to_json(self) -> dict[str, Any]:
        preset = self.normalized()
        return {
            "schema": BRUSH_SCHEMA,
            "name": preset.name,
            "width": preset.width,
            "height": preset.height,
            "layers": [
                {"name": layer.name, "opacity": layer.opacity, "pixels": layer.pixels}
                for layer in preset.layers
            ],
            "metadata": preset.metadata,
        }

    @classmethod
    def from_json(cls, value: Any) -> "BrushPreset":
        if not isinstance(value, dict):
            raise ValueError("3D brush document must be an object")
        schema = str(value.get("schema", BRUSH_SCHEMA))
        if schema != BRUSH_SCHEMA:
            raise ValueError(f"Unsupported 3D brush schema: {schema}")
        width = int(value.get("width", 17))
        height = int(value.get("height", 17))
        layers: list[BrushLayer] = []
        for item in value.get("layers", []):
            if isinstance(item, dict):
                layers.append(
                    BrushLayer(
                        str(item.get("name", f"Layer {len(layers) + 1}")),
                        float(item.get("opacity", 1.0)),
                        item.get("pixels", []) if isinstance(item.get("pixels", []), list) else [],
                    )
                )
        return cls(
            str(value.get("name", "Untitled Brush")), width, height, layers,
            value.get("metadata", {}) if isinstance(value.get("metadata", {}), dict) else {},
        ).normalized()

    def duplicate(self, name: str | None = None) -> "BrushPreset":
        copied = copy.deepcopy(self)
        copied.name = name or f"{self.name} Copy"
        return copied

    @classmethod
    def round_soft(cls, name: str = "Round Soft", size: int = 17) -> "BrushPreset":
        size = max(MIN_BRUSH_SIDE, min(MAX_BRUSH_SIDE, int(size)))
        center = (size - 1) / 2.0
        radius = max(1.0, center)
        pixels = []
        for row in range(size):
            values = []
            for column in range(size):
                distance = math.hypot(column - center, row - center) / radius
                values.append(_clamp(1.0 - distance))
            pixels.append(values)
        return cls(name, size, size, [BrushLayer("Soft Core", 1.0, pixels)], {"builtin": True, "semantic": "generic", "environment_types": ["enemy", "boss", "mini_boss", "friendly", "environment_object", "environment_theme", "room", "liquid", "raid"], "tags": ["soft", "general"]})

    @classmethod
    def square(cls, name: str = "Square Solid", size: int = 11) -> "BrushPreset":
        return cls(name, size, size, [BrushLayer("Base", 1.0, [[1.0] * size for _ in range(size)])], {"builtin": True, "semantic": "generic", "environment_types": ["environment_object", "environment_theme", "room", "raid"], "tags": ["solid", "structural"]})

    @classmethod
    def cross(cls, name: str = "Cross", size: int = 17) -> "BrushPreset":
        center = size // 2
        pixels = [[0.0] * size for _ in range(size)]
        for index in range(size):
            pixels[center][index] = 1.0
            pixels[index][center] = 1.0
        return cls(name, size, size, [BrushLayer("Cross", 1.0, pixels)], {"builtin": True, "semantic": "trigger", "environment_types": ["enemy", "boss", "mini_boss", "friendly", "environment_object", "room", "raid"], "tags": ["anchor", "marker"]})


def save_brush(path: Path, brush: BrushPreset) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".3dbrush":
        path = path.with_suffix(".3dbrush")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(brush.normalized().to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def load_brush(path: Path) -> BrushPreset:
    return BrushPreset.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


def ensure_default_brushes(root_path: Path) -> list[Path]:
    directory = Path(root_path) / "content" / "pcp3_brushes"
    directory.mkdir(parents=True, exist_ok=True)
    defaults = [BrushPreset.round_soft(), BrushPreset.square(), BrushPreset.cross()]
    paths = []
    for brush in defaults:
        path = directory / safe_brush_filename(brush.name)
        if not path.exists():
            save_brush(path, brush)
        paths.append(path)
    return paths


def discover_brushes(root_path: Path) -> list[Path]:
    root_path = Path(root_path)
    paths: list[Path] = []
    for directory in (
        root_path / "content" / "pcp3_brushes",
        root_path / "user_data" / "pcp3" / "brushes",
    ):
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.3dbrush"), key=lambda path: path.name.lower()))
    unique: dict[str, Path] = {}
    for path in paths:
        unique[str(path.resolve())] = path
    return list(unique.values())


class BrushEditorWindow(tk.Toplevel):
    """Paint.NET-like 2D mask editor for PCP3 3D brush presets."""

    def __init__(
        self,
        master: tk.Misc,
        root_path: Path,
        initial: BrushPreset,
        on_apply: Callable[[BrushPreset, Path | None], None],
    ) -> None:
        super().__init__(master)
        self.root_path = Path(root_path)
        self.on_apply = on_apply
        self.brush = initial.duplicate(initial.name).normalized()
        self.current_path: Path | None = None
        self.active_layer = 0
        self.selected_cell = (self.brush.width // 2, self.brush.height // 2)
        self.paint_alpha = tk.DoubleVar(value=1.0)
        self.opacity_value = tk.DoubleVar(value=1.0)
        self.opacity_display = tk.StringVar(value="100%")
        self.active_target = tk.StringVar(value="Dot")
        self.brush_name = tk.StringVar(value=self.brush.name)
        self.status = tk.StringVar(value="Left-click toggles pixels · drag paints · right-drag erases")
        self._tab_buttons: list[ttk.Button] = []
        self._tab_index = 0
        self._painting = False
        self._erase = False

        self.title("Point Cloud Paint++ · 3D Brush Editor")
        self.geometry("980x680")
        self.minsize(800, 560)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self._build_ui()
        self.refresh_all()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        split = ttk.Panedwindow(outer, orient="horizontal")
        split.pack(fill="both", expand=True)

        left = ttk.Frame(split, padding=(0, 0, 6, 0))
        split.add(left, weight=4)
        top = ttk.Frame(left)
        top.pack(fill="x", pady=(0, 4))
        ttk.Label(top, text="Brush name:").pack(side="left")
        ttk.Entry(top, textvariable=self.brush_name).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(top, text="Pixel mask workspace", font=("Sans", 10, "bold")).pack(side="right")

        self.canvas = tk.Canvas(left, background="#11161a", highlightthickness=1, highlightbackground="#52616a")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<Button-1>", self.pixel_left)
        self.canvas.bind("<B1-Motion>", self.pixel_left_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _event: setattr(self, "_painting", False))
        self.canvas.bind("<Button-3>", self.pixel_right)
        self.canvas.bind("<B3-Motion>", self.pixel_right_drag)
        self.canvas.bind("<ButtonRelease-3>", lambda _event: setattr(self, "_erase", False))

        target_bar = ttk.Frame(left)
        target_bar.pack(fill="x", pady=(6, 2))
        ttk.Button(target_bar, text="◀", width=4, command=lambda: self.move_target(-1)).pack(side="left")
        self.tab_canvas = tk.Canvas(target_bar, height=34, highlightthickness=0)
        self.tab_canvas.pack(side="left", fill="x", expand=True, padx=3)
        self.tab_inner = ttk.Frame(self.tab_canvas)
        self.tab_window = self.tab_canvas.create_window((0, 0), window=self.tab_inner, anchor="nw")
        self.tab_inner.bind("<Configure>", self._tabs_configured)
        self.tab_canvas.bind("<Configure>", lambda event: self.tab_canvas.itemconfigure(self.tab_window, height=event.height))
        ttk.Button(target_bar, text="▶", width=4, command=lambda: self.move_target(1)).pack(side="left")

        opacity = ttk.Frame(left)
        opacity.pack(fill="x")
        ttk.Label(opacity, text="Active target opacity:").pack(side="left")
        self.opacity_scale = ttk.Scale(opacity, from_=0.0, to=1.0, variable=self.opacity_value, command=self.opacity_changed)
        self.opacity_scale.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(opacity, textvariable=self.opacity_display, width=7).pack(side="left")

        right = ttk.Frame(split, padding=(6, 0, 0, 0))
        split.add(right, weight=2)
        ttk.Label(right, text="Local 3D Brush Sets", font=("Sans", 10, "bold")).pack(anchor="w")
        self.brush_list = tk.Listbox(right, exportselection=False, height=13)
        self.brush_list.pack(fill="both", expand=True, pady=(4, 5))
        self.brush_list.bind("<Double-Button-1>", lambda _event: self.load_selected())
        action = ttk.Frame(right)
        action.pack(fill="x")
        for text, command in (
            ("Apply", self.apply), ("Save", self.save), ("Load", self.load_selected),
            ("New", self.new), ("Dup", self.duplicate),
        ):
            ttk.Button(action, text=text, command=command).pack(side="left", fill="x", expand=True, padx=1)

        ttk.Separator(right).pack(fill="x", pady=8)
        ttk.Label(right, text="Pixel-dot layers", font=("Sans", 10, "bold")).pack(anchor="w")
        self.layer_list = tk.Listbox(right, exportselection=False, height=8)
        self.layer_list.pack(fill="x", pady=4)
        self.layer_list.bind("<<ListboxSelect>>", self.layer_selected)
        layer_buttons = ttk.Frame(right)
        layer_buttons.pack(fill="x")
        for text, command in (("+", self.add_layer), ("Copy", self.copy_layer), ("−", self.delete_layer), ("↑", lambda: self.move_layer(-1)), ("↓", lambda: self.move_layer(1))):
            ttk.Button(layer_buttons, text=text, width=5, command=command).pack(side="left", padx=1)
        ttk.Button(right, text="Rename selected layer", command=self.rename_layer).pack(fill="x", pady=(4, 0))
        ttk.Label(
            right,
            text=("Dot tab controls the selected pixel. Each layer tab controls that layer's opacity. "
                  "Arrow buttons move through hidden tabs."),
            wraplength=260,
        ).pack(fill="x", pady=8)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(6, 0))
        ttk.Label(footer, textvariable=self.status).pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Close", command=self.withdraw).pack(side="right")

    def _tabs_configured(self, _event: tk.Event) -> None:
        self.tab_canvas.configure(scrollregion=self.tab_canvas.bbox("all"))

    def refresh_all(self) -> None:
        self.brush = self.brush.normalized()
        self.brush.name = self.brush_name.get().strip() or self.brush.name
        self.refresh_presets()
        self.refresh_layers()
        self.refresh_targets()
        self.sync_opacity_from_target()
        self.redraw()

    def refresh_presets(self) -> None:
        ensure_default_brushes(self.root_path)
        self.discovered = discover_brushes(self.root_path)
        self.brush_list.delete(0, "end")
        for path in self.discovered:
            self.brush_list.insert("end", path.stem)

    def refresh_layers(self) -> None:
        self.layer_list.delete(0, "end")
        for layer in self.brush.layers:
            self.layer_list.insert("end", f"{layer.name} · {int(layer.opacity * 100)}%")
        self.active_layer = max(0, min(self.active_layer, len(self.brush.layers) - 1))
        self.layer_list.selection_set(self.active_layer)

    def refresh_targets(self) -> None:
        for child in self.tab_inner.winfo_children():
            child.destroy()
        names = ["Dot"] + [layer.name for layer in self.brush.layers]
        self._tab_buttons.clear()
        for index, name in enumerate(names):
            button = ttk.Button(self.tab_inner, text=name, command=lambda value=name, i=index: self.set_target(value, i))
            button.pack(side="left", padx=1, pady=2)
            self._tab_buttons.append(button)
        if self.active_target.get() not in names:
            self.active_target.set("Dot")
            self._tab_index = 0
        else:
            self._tab_index = names.index(self.active_target.get())
        self.after_idle(self.ensure_target_visible)

    def set_target(self, name: str, index: int) -> None:
        self.active_target.set(name)
        self._tab_index = index
        self.sync_opacity_from_target()
        self.ensure_target_visible()

    def move_target(self, direction: int) -> None:
        names = ["Dot"] + [layer.name for layer in self.brush.layers]
        if not names:
            return
        self._tab_index = max(0, min(len(names) - 1, self._tab_index + direction))
        self.set_target(names[self._tab_index], self._tab_index)

    def ensure_target_visible(self) -> None:
        if not self._tab_buttons or self._tab_index >= len(self._tab_buttons):
            return
        self.update_idletasks()
        button = self._tab_buttons[self._tab_index]
        total = max(1, self.tab_inner.winfo_reqwidth())
        viewport = max(1, self.tab_canvas.winfo_width())
        left = button.winfo_x()
        right = left + button.winfo_width()
        current_left = self.tab_canvas.canvasx(0)
        if left < current_left:
            self.tab_canvas.xview_moveto(left / total)
        elif right > current_left + viewport:
            self.tab_canvas.xview_moveto(max(0.0, (right - viewport) / total))

    def sync_opacity_from_target(self) -> None:
        target = self.active_target.get()
        if target == "Dot":
            column, row = self.selected_cell
            value = self.brush.layers[self.active_layer].pixels[row][column]
        else:
            layer = next((item for item in self.brush.layers if item.name == target), self.brush.layers[self.active_layer])
            value = layer.opacity
        self.opacity_value.set(value)
        self.opacity_display.set(f"{int(round(value * 100))}%")

    def opacity_changed(self, value: str) -> None:
        opacity = _clamp(float(value))
        self.opacity_display.set(f"{int(round(opacity * 100))}%")
        target = self.active_target.get()
        if target == "Dot":
            column, row = self.selected_cell
            self.brush.layers[self.active_layer].pixels[row][column] = opacity
        else:
            layer = next((item for item in self.brush.layers if item.name == target), None)
            if layer is not None:
                layer.opacity = opacity
                self.refresh_layers()
        self.redraw()

    def cell_at(self, event: tk.Event) -> tuple[int, int] | None:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        cell = max(4.0, min(width / self.brush.width, height / self.brush.height))
        total_w = cell * self.brush.width
        total_h = cell * self.brush.height
        origin_x = (width - total_w) / 2.0
        origin_y = (height - total_h) / 2.0
        column = int((event.x - origin_x) // cell)
        row = int((event.y - origin_y) // cell)
        if 0 <= column < self.brush.width and 0 <= row < self.brush.height:
            return column, row
        return None

    def set_cell(self, event: tk.Event, *, erase: bool, toggle: bool = False) -> None:
        cell = self.cell_at(event)
        if cell is None:
            return
        column, row = cell
        self.selected_cell = cell
        layer = self.brush.layers[self.active_layer]
        if erase:
            layer.pixels[row][column] = 0.0
        elif toggle:
            layer.pixels[row][column] = 0.0 if layer.pixels[row][column] > 0.001 else max(0.05, self.paint_alpha.get())
        else:
            layer.pixels[row][column] = max(0.05, self.paint_alpha.get())
        self.active_target.set("Dot")
        self._tab_index = 0
        self.sync_opacity_from_target()
        self.redraw()

    def pixel_left(self, event: tk.Event) -> None:
        self._painting = True
        self.paint_alpha.set(max(0.05, self.opacity_value.get()))
        self.set_cell(event, erase=False, toggle=True)

    def pixel_left_drag(self, event: tk.Event) -> None:
        if self._painting:
            self.set_cell(event, erase=False)

    def pixel_right(self, event: tk.Event) -> None:
        self._erase = True
        self.set_cell(event, erase=True)

    def pixel_right_drag(self, event: tk.Event) -> None:
        if self._erase:
            self.set_cell(event, erase=True)

    def redraw(self) -> None:
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        cell = max(4.0, min(width / self.brush.width, height / self.brush.height))
        total_w = cell * self.brush.width
        total_h = cell * self.brush.height
        origin_x = (width - total_w) / 2.0
        origin_y = (height - total_h) / 2.0
        composite = self.brush.composite()
        active = self.brush.layers[self.active_layer]
        for row in range(self.brush.height):
            for column in range(self.brush.width):
                x1 = origin_x + column * cell
                y1 = origin_y + row * cell
                alpha = composite[row][column]
                shade = int(26 + alpha * 205)
                fill = f"#{shade:02x}{shade:02x}{shade:02x}"
                outline = "#55c9ff" if (column, row) == self.selected_cell else "#344047"
                canvas.create_rectangle(x1, y1, x1 + cell, y1 + cell, fill=fill, outline=outline, width=2 if outline == "#55c9ff" else 1)
                if active.pixels[row][column] > 0.001:
                    canvas.create_oval(x1 + cell * 0.32, y1 + cell * 0.32, x1 + cell * 0.68, y1 + cell * 0.68, fill="#e0c982", outline="")
        canvas.create_text(8, 8, anchor="nw", fill="#a9c4d2", text=f"{self.brush.width}×{self.brush.height} · layer {active.name}")

    def selected_preset_path(self) -> Path | None:
        selection = self.brush_list.curselection()
        if not selection:
            return None
        index = selection[0]
        return self.discovered[index] if index < len(self.discovered) else None

    def load_selected(self) -> None:
        path = self.selected_preset_path()
        if path is None:
            path_value = filedialog.askopenfilename(parent=self, title="Load 3D brush", initialdir=self.root_path / "user_data" / "pcp3" / "brushes", filetypes=(("PCP3 3D Brush", "*.3dbrush"),))
            if not path_value:
                return
            path = Path(path_value)
        try:
            self.brush = load_brush(path)
            self.current_path = path
            self.brush_name.set(self.brush.name)
            self.active_layer = 0
            self.selected_cell = (self.brush.width // 2, self.brush.height // 2)
            self.active_target.set("Dot")
            self.status.set(f"Loaded {path.name}")
            self.refresh_all()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Could not load brush", str(exc), parent=self)

    def save(self) -> None:
        self.brush.name = self.brush_name.get().strip() or "Untitled Brush"
        path = self.current_path
        if path is None or path.parent == self.root_path / "content" / "pcp3_brushes":
            initial = self.root_path / "user_data" / "pcp3" / "brushes"
            initial.mkdir(parents=True, exist_ok=True)
            value = filedialog.asksaveasfilename(parent=self, title="Save 3D brush", initialdir=initial, initialfile=safe_brush_filename(self.brush.name), defaultextension=".3dbrush", filetypes=(("PCP3 3D Brush", "*.3dbrush"),))
            if not value:
                return
            path = Path(value)
        try:
            self.current_path = save_brush(path, self.brush)
            self.status.set(f"Saved {self.current_path.name}")
            self.refresh_presets()
        except OSError as exc:
            messagebox.showerror("Could not save brush", str(exc), parent=self)

    def apply(self) -> None:
        self.brush.name = self.brush_name.get().strip() or self.brush.name
        self.on_apply(self.brush.normalized(), self.current_path)
        self.status.set(f"Applied {self.brush.name} to Point Cloud Paint++")

    def new(self) -> None:
        size = simpledialog.askinteger("New 3D brush", "Brush grid side (3–65):", initialvalue=17, minvalue=MIN_BRUSH_SIDE, maxvalue=MAX_BRUSH_SIDE, parent=self)
        if size is None:
            return
        self.brush = BrushPreset("Untitled Brush", size, size, [BrushLayer("Base", 1.0, [[0.0] * size for _ in range(size)])])
        self.current_path = None
        self.brush_name.set(self.brush.name)
        self.active_layer = 0
        self.selected_cell = (size // 2, size // 2)
        self.refresh_all()

    def duplicate(self) -> None:
        name = simpledialog.askstring("Duplicate 3D brush", "New brush name:", initialvalue=f"{self.brush.name} Copy", parent=self)
        if not name:
            return
        self.brush = self.brush.duplicate(name)
        self.current_path = None
        self.brush_name.set(name)
        self.refresh_all()

    def layer_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.layer_list.curselection()
        if selection:
            self.active_layer = selection[0]
            self.active_target.set(self.brush.layers[self.active_layer].name)
            self._tab_index = self.active_layer + 1
            self.sync_opacity_from_target()
            self.redraw()

    def add_layer(self) -> None:
        pixels = [[0.0] * self.brush.width for _ in range(self.brush.height)]
        self.brush.layers.append(BrushLayer(f"Layer {len(self.brush.layers) + 1}", 1.0, pixels))
        self.active_layer = len(self.brush.layers) - 1
        self.refresh_all()

    def copy_layer(self) -> None:
        self.brush.layers.insert(self.active_layer + 1, copy.deepcopy(self.brush.layers[self.active_layer]))
        self.brush.layers[self.active_layer + 1].name += " Copy"
        self.active_layer += 1
        self.refresh_all()

    def delete_layer(self) -> None:
        if len(self.brush.layers) <= 1:
            messagebox.showinfo("Layer retained", "A 3D brush must keep at least one pixel-dot layer.", parent=self)
            return
        del self.brush.layers[self.active_layer]
        self.active_layer = max(0, min(self.active_layer, len(self.brush.layers) - 1))
        self.refresh_all()

    def move_layer(self, direction: int) -> None:
        target = self.active_layer + direction
        if not 0 <= target < len(self.brush.layers):
            return
        self.brush.layers[self.active_layer], self.brush.layers[target] = self.brush.layers[target], self.brush.layers[self.active_layer]
        self.active_layer = target
        self.refresh_all()

    def rename_layer(self) -> None:
        layer = self.brush.layers[self.active_layer]
        name = simpledialog.askstring("Rename pixel-dot layer", "Layer name:", initialvalue=layer.name, parent=self)
        if name:
            layer.name = name.strip() or layer.name
            self.refresh_all()
