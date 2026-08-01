from __future__ import annotations

import json
import math
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from tools.pcp3 import editor_branch3 as branch3
from tools.pcp3.editor_branch2r1 import (
    MAX_INTERACTIVE_DOCUMENT_POINTS,
    MAX_POINTS_PER_GENERATOR,
)
from tools.pcp3.guided_shapes import (
    FRAME_STYLES,
    PRESET_GROUPS,
    PRESET_LABELS,
    Region3D,
    default_parameters,
    estimate_preset_points,
    generate_preset,
    generate_room_shell,
    group_for_preset,
    preview_polyline,
    room_shell_preview,
    semantic_for_preset,
)
from tools.pcp3.model import Layer


MAX_CUSTOM_COLORS = 24


class NumberControl(ttk.Frame):
    """Paired numeric entry and slider used by guided-shape dialogs."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        variable: tk.DoubleVar,
        low: float,
        high: float,
        on_change: Callable[[], None],
        *,
        row: int,
    ) -> None:
        super().__init__(master)
        ttk.Label(master, text=label).grid(row=row, column=0, sticky="w", padx=(10, 5), pady=3)
        entry = ttk.Entry(master, textvariable=variable, width=12)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        scale = ttk.Scale(master, from_=low, to=high, variable=variable, command=lambda _value: on_change())
        scale.grid(row=row, column=2, sticky="ew", padx=(6, 10), pady=3)
        entry.bind("<KeyRelease>", lambda _event: on_change())
        entry.bind("<FocusOut>", lambda _event: on_change())


class GuidedPresetDialog(tk.Toplevel):
    def __init__(self, editor: "PCP3Editor", preset: str, region: Region3D) -> None:
        super().__init__(editor)
        self.editor = editor
        self.preset = preset
        self.base_region = region
        self.title(f"{PRESET_LABELS[preset]} guided parameters")
        self.transient(editor)
        self.resizable(True, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.columnconfigure(2, weight=1)

        params = default_parameters(
            preset,
            region,
            spacing=editor.brush_spacing.get(),
            room_height=editor.document.settings.height,
        )
        self.numeric: dict[str, tk.DoubleVar] = {
            "center_x": tk.DoubleVar(value=region.center[0]),
            "center_y": tk.DoubleVar(value=region.center[1]),
            "center_z": tk.DoubleVar(value=region.center[2]),
            "size_x": tk.DoubleVar(value=region.size[0]),
            "size_y": tk.DoubleVar(value=region.size[1]),
            "size_z": tk.DoubleVar(value=region.size[2]),
        }
        for key, value in params.items():
            if isinstance(value, (int, float)):
                self.numeric[key] = tk.DoubleVar(value=float(value))
        self.frame_style = tk.StringVar(value=str(params.get("frame_style", "square")))

        ttk.Label(
            self,
            text=(
                "The selected border established the center and initial dimensions. "
                "Every numeric value can be changed with either its input or slider; the cyan guide updates live."
            ),
            wraplength=650,
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 6))

        extent = max(
            editor.document.settings.width,
            editor.document.settings.height,
            editor.document.settings.depth,
            12.0,
        )
        fields: list[tuple[str, str, float, float]] = [
            ("center_x", "Center X", -extent * 2.0, extent * 2.0),
            ("center_y", "Center Y", -extent * 2.0, extent * 2.0),
            ("center_z", "Center Z", -extent * 2.0, extent * 2.0),
            ("size_x", "Size X", 0.05, extent * 3.0),
            ("size_y", "Size Y", 0.05, extent * 3.0),
            ("size_z", "Size Z", 0.05, extent * 3.0),
            ("spacing", "Point spacing", 0.05, max(2.0, extent / 5.0)),
        ]
        if preset.endswith("wall"):
            fields += [
                ("thickness", "Wall thickness", 0.05, 5.0),
                ("height", "Wall height", 0.1, extent * 2.0),
            ]
            if preset == "rock_wall":
                fields.append(("roughness", "Rock roughness", 0.0, 1.0))
            elif preset == "wood_wall":
                fields.append(("plank_size", "Plank height", 0.1, 3.0))
            elif preset == "plywood_wall":
                fields.append(("panel_size", "Panel width", 0.25, 6.0))
        elif preset.endswith("floor"):
            fields.append(("thickness", "Floor thickness", 0.05, 3.0))
            if preset == "rocky_floor":
                fields.append(("roughness", "Rock roughness", 0.0, 1.0))
        elif preset.endswith("ceiling"):
            fields.append(("thickness", "Ceiling thickness", 0.05, 3.0))
            if preset in {"vaulted_ceiling", "rounded_ceiling", "domed_ceiling"}:
                fields.append(("rise", "Arch / dome rise", 0.05, extent))
            if preset == "rock_ceiling":
                fields.append(("roughness", "Rock roughness", 0.0, 1.0))
        elif preset == "chandelier":
            fields += [
                ("radius", "Largest ring radius", 0.1, extent),
                ("chain_length", "Support-chain length", 0.1, extent),
                ("stages", "Ring stages", 1.0, 8.0),
            ]
        elif preset in {"wall_light", "ceiling_light"}:
            fields += [
                ("width", "Fixture width", 0.1, extent),
                ("fixture_height", "Fixture height", 0.05, extent),
                ("depth", "Fixture depth (3+ dots)", 0.05, extent),
            ]
        elif preset == "corner_camera":
            fields.append(("scale", "Camera grid scale (5×6×9)", 0.05, 3.0))
        elif preset.endswith("frame"):
            fields += [
                ("frame_thickness", "Frame border thickness", 0.05, 3.0),
                ("frame_depth", "Frame depth", 0.05, 5.0),
                ("height", "Opening height", 0.1, extent * 2.0),
            ]

        row = 1
        for key, label, low, high in fields:
            if key not in self.numeric:
                continue
            NumberControl(self, label, self.numeric[key], low, high, self.changed, row=row)
            row += 1

        if preset.endswith("frame"):
            ttk.Label(self, text="Frame type").grid(row=row, column=0, sticky="w", padx=(10, 5), pady=3)
            box = ttk.Combobox(self, textvariable=self.frame_style, values=FRAME_STYLES, state="readonly", width=24)
            box.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=3)
            box.bind("<<ComboboxSelected>>", lambda _event: self.changed())
            row += 1

        buttons = ttk.Frame(self, padding=10)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=3)
        ttk.Button(buttons, text="Generate", command=self.generate).pack(side="right", padx=3)
        self.after_idle(self.changed)

    def values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for key, variable in self.numeric.items():
            try:
                values[key] = float(variable.get())
            except (ValueError, tk.TclError):
                values[key] = 0.0
        values["frame_style"] = self.frame_style.get()
        return values

    def adjusted_region(self) -> Region3D:
        values = self.values()
        center = (values["center_x"], values["center_y"], values["center_z"])
        size = (
            max(0.05, values["size_x"]),
            max(0.05, values["size_y"]),
            max(0.05, values["size_z"]),
        )
        minimum = tuple(center[index] - size[index] * 0.5 for index in range(3))
        maximum = tuple(center[index] + size[index] * 0.5 for index in range(3))
        return Region3D(self.base_region.projection, minimum, maximum, center, size)

    def changed(self) -> None:
        region = self.adjusted_region()
        self.editor.shape_preview = {
            "shape": "pcp3_custom_polyline",
            "polyline": preview_polyline(self.preset, region, self.values()),
        }
        self.editor.redraw()

    def generate(self) -> None:
        self.editor.generate_guided_preset(self.preset, self.adjusted_region(), self.values())
        self.editor.shape_preview = None
        self.editor.shape_mode = None
        self.destroy()

    def cancel(self) -> None:
        self.editor.shape_preview = None
        self.editor.shape_mode = None
        self.editor.redraw()
        self.destroy()


class RoomShellDialog(tk.Toplevel):
    def __init__(self, editor: "PCP3Editor", region: Region3D) -> None:
        super().__init__(editor)
        self.editor = editor
        self.region = region
        self.title("Room Shell guided parameters")
        self.transient(editor)
        self.resizable(True, False)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.columnconfigure(2, weight=1)

        spacing = max(0.05, editor.brush_spacing.get())
        default_height = max(
            0.1,
            editor.document.settings.height - max(0.15, spacing * 2.0) * 2.0,
        )
        self.values_map = {
            "spacing": tk.DoubleVar(value=spacing),
            "wall_thickness": tk.DoubleVar(value=1.0),
            "wall_top": tk.DoubleVar(value=-0.0),
            "wall_bottom": tk.DoubleVar(value=-0.0),
            "wall_height": tk.DoubleVar(value=default_height),
            "floor_thickness": tk.DoubleVar(value=max(0.15, spacing * 2.0)),
            "ceiling_thickness": tk.DoubleVar(value=max(0.15, spacing * 2.0)),
        }
        ttk.Label(
            self,
            text=(
                "Top selection defines the floor/ceiling footprint. Front or Side selection defines the marked wall face "
                "and uses the current room depth/width for the remaining dimension. Wall top and bottom gaps leave natural openings."
            ),
            wraplength=650,
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(10, 6))
        extent = max(editor.document.settings.width, editor.document.settings.height, editor.document.settings.depth, 12.0)
        fields = (
            ("wall_thickness", "Wall thickness", 0.05, 5.0),
            ("wall_top", "Wall top opening gap", 0.0, extent),
            ("wall_bottom", "Wall bottom opening gap", 0.0, extent),
            ("wall_height", "Wall height", 0.1, extent * 2.0),
            ("floor_thickness", "Floor depth", 0.05, 3.0),
            ("ceiling_thickness", "Ceiling depth", 0.05, 3.0),
            ("spacing", "Point spacing", 0.05, max(2.0, extent / 5.0)),
        )
        for row, (key, label, low, high) in enumerate(fields, start=1):
            NumberControl(self, label, self.values_map[key], low, high, self.changed, row=row)
        buttons = ttk.Frame(self, padding=10)
        buttons.grid(row=len(fields) + 1, column=0, columnspan=3, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right", padx=3)
        ttk.Button(buttons, text="Generate Room Shell", command=self.generate).pack(side="right", padx=3)
        self.after_idle(self.changed)

    def values(self) -> dict[str, float]:
        output: dict[str, float] = {}
        for key, variable in self.values_map.items():
            try:
                output[key] = float(variable.get())
            except (ValueError, tk.TclError):
                output[key] = 0.0
        return output

    def changed(self) -> None:
        self.editor.shape_preview = {
            "shape": "pcp3_custom_polyline",
            "polyline": room_shell_preview(
                self.region,
                self.values(),
                self.editor.document.settings.width,
                self.editor.document.settings.depth,
            ),
        }
        self.editor.redraw()

    def generate(self) -> None:
        self.editor.generate_room_shell_from_region(self.region, self.values())
        self.editor.shape_preview = None
        self.editor.shape_mode = None
        self.destroy()

    def cancel(self) -> None:
        self.editor.shape_preview = None
        self.editor.shape_mode = None
        self.editor.redraw()
        self.destroy()


class PCP3Editor(branch3.PCP3Editor):
    """Branch 3 R1: architecture presets, corrected Room Shell, toolbar clarity, and persistent custom colors."""

    def __init__(self, root_path: Path) -> None:
        self.custom_colors: list[str] = []
        self.custom_color_choice: tk.StringVar | None = None
        self.custom_color_combo: ttk.Combobox | None = None
        self.custom_color_swatch: tk.Label | None = None
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 3 R1 Architecture Presets")
        self.document.metadata["editor_branch"] = "ISL_plus_branch3_R1"
        self._load_custom_colors()
        self.remember_custom_color(self.color_hex.get(), persist=False)
        self._refresh_custom_color_widgets()
        self.update_status("Branch 3 R1 active · architecture presets · guided Room Shell · persistent Custom Colors")

    # ---------- toolbar ----------
    def _build_toolbar(self) -> None:
        super()._build_toolbar()
        shell = getattr(self, "command_toolbar", None)
        if shell is not None:
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
            button("Tools Help", self.show_tools_help)

        toolbar = self.active_tool_label.master
        reset_viewports: ttk.Button | None = None
        reset_angles: ttk.Button | None = None
        for child in toolbar.winfo_children():
            try:
                text = str(child.cget("text"))
            except tk.TclError:
                continue
            if text == "Reset Viewports":
                reset_viewports = child  # type: ignore[assignment]
            elif text == "Reset View Angles":
                reset_angles = child  # type: ignore[assignment]
        if reset_viewports is not None:
            reset_viewports.grid_forget()
            reset_viewports.grid(row=1, column=7, columnspan=2, sticky="e", pady=(5, 0), padx=(4, 4))
        if reset_angles is not None:
            reset_angles.grid_forget()
            reset_angles.grid(row=1, column=13, columnspan=2, sticky="e", pady=(5, 0), padx=(4, 0))

        self.custom_color_choice = tk.StringVar(master=self, value=self.color_hex.get().upper())
        ttk.Label(toolbar, text="Custom Colors").grid(row=1, column=9, sticky="e", pady=(5, 0), padx=(5, 2))
        self.custom_color_swatch = tk.Label(toolbar, width=3, relief="sunken", background=self.color_hex.get())
        self.custom_color_swatch.grid(row=1, column=10, pady=(5, 0), padx=2)
        self.custom_color_combo = ttk.Combobox(
            toolbar,
            textvariable=self.custom_color_choice,
            values=tuple(self.custom_colors),
            state="readonly",
            width=11,
        )
        self.custom_color_combo.grid(row=1, column=11, columnspan=2, sticky="ew", pady=(5, 0), padx=(2, 4))
        self.custom_color_combo.bind("<<ComboboxSelected>>", lambda _event: self.apply_custom_color())

    # ---------- guided shape UI ----------
    def _build_workspace(self) -> None:
        super()._build_workspace()
        self._install_architecture_shape_library()

    def _install_architecture_shape_library(self) -> None:
        try:
            pane_name = self.main_paned.panes()[0]
            tools_frame = self.nametowidget(pane_name)
        except (AttributeError, IndexError, KeyError, tk.TclError):
            return
        frame = ttk.LabelFrame(tools_frame, text="Architecture & fixtures", padding=3)
        frame.pack(fill="x", pady=(7, 2))
        for group, entries in PRESET_GROUPS.items():
            menu_button = ttk.Menubutton(frame, text=group)
            menu = tk.Menu(menu_button, tearoff=False)
            for preset, label in entries:
                menu.add_command(label=label, command=lambda value=preset: self.activate_guided_preset(value))
            menu_button.configure(menu=menu)
            menu_button.pack(fill="x", pady=1)

    def activate_guided_preset(self, preset: str) -> None:
        self.shape_mode = f"pcp3_preset:{preset}"
        self.shape_preview = None
        self.shape_region_start = None
        self.shape_region_end = None
        self.update_status(f"{PRESET_LABELS[preset]} active · select its border / region in a viewport")

    def generate_room_shell(self) -> None:
        self.shape_mode = "pcp3_room_shell"
        self.shape_preview = None
        self.shape_region_start = None
        self.shape_region_end = None
        self.update_status("Room Shell active · select the footprint in Top or a wall face in Front / Side")

    def finish_shape_region(self) -> None:
        if not self.shape_mode or not self.shape_region_start or not self.shape_region_end:
            return
        if not self.shape_mode.startswith("pcp3_"):
            super().finish_shape_region()
            return
        pane = self.shape_pane or self.panes()[0]
        x1, y1 = self.shape_region_start
        x2, y2 = self.shape_region_end
        if math.dist((x1, y1), (x2, y2)) < 4.0:
            x2, y2 = x1 + 40.0, y1 + 40.0
        a = self.screen_to_world(x1, y1, pane)
        b = self.screen_to_world(x2, y2, pane)
        region = Region3D.from_points(
            pane.projection,
            a,
            b,
            missing_size=max(0.15, self.brush_spacing.get() * 2.0),
        )
        mode = self.shape_mode
        self.shape_region_start = None
        self.shape_region_end = None
        if mode == "pcp3_room_shell":
            RoomShellDialog(self, region)
        else:
            preset = mode.split(":", 1)[1]
            GuidedPresetDialog(self, preset, region)

    def shape_preview_polyline(self, preview: dict[str, float | str]) -> list[tuple[float, float, float]]:
        polyline = preview.get("polyline")
        if isinstance(polyline, list):
            output: list[tuple[float, float, float]] = []
            for value in polyline:
                if isinstance(value, (list, tuple)) and len(value) >= 3:
                    output.append((float(value[0]), float(value[1]), float(value[2])))
            return output
        return super().shape_preview_polyline(preview)

    def _ensure_named_layer(self, name: str, semantic: str, group: str, metadata: dict[str, Any]) -> Layer:
        base_name = name
        suffix = 1
        existing_names = {layer.name.casefold() for layer in self.document.layers}
        while name.casefold() in existing_names:
            suffix += 1
            name = f"{base_name} {suffix}"
        layer = self.document.add_layer(name, semantic)
        layer.group = group
        layer.future_attributes.update(metadata)
        return layer

    def _safe_guided_spacing(self, preset: str, region: Region3D, params: dict[str, Any]) -> dict[str, Any] | None:
        adjusted = dict(params)
        estimate = estimate_preset_points(preset, region, adjusted)
        remaining = max(0, MAX_INTERACTIVE_DOCUMENT_POINTS - len(self.document.points))
        allowed = min(MAX_POINTS_PER_GENERATOR, remaining)
        if allowed <= 0:
            messagebox.showwarning(
                "Interactive point limit reached",
                f"This interactive project is capped at {MAX_INTERACTIVE_DOCUMENT_POINTS:,} points. Export or reduce points before adding another preset.",
                parent=self,
            )
            return None
        if estimate > allowed:
            current = max(0.05, float(adjusted.get("spacing", self.brush_spacing.get())))
            safer = current * math.sqrt(estimate / max(1, allowed)) * 1.05
            if not messagebox.askyesno(
                "Guided shape density reduced for safety",
                f"{PRESET_LABELS[preset]} is estimated to create {estimate:,} points.\n\n"
                f"The safe operation limit is {allowed:,}. Increase spacing from {current:.4f} to approximately {safer:.4f} and continue?",
                parent=self,
            ):
                return None
            adjusted["spacing"] = safer
        return adjusted

    def generate_guided_preset(self, preset: str, region: Region3D, params: dict[str, Any]) -> None:
        adjusted = self._safe_guided_spacing(preset, region, params)
        if adjusted is None:
            return
        semantic = semantic_for_preset(preset)
        label = PRESET_LABELS[preset]
        group = group_for_preset(preset)
        metadata: dict[str, Any] = {
            "pcp3_guided_preset": preset,
            "generator_version": 1,
            "projection": region.projection,
        }
        if semantic == "light":
            metadata.update({"light_source": "normal", "light_intensity": 1.0})
        if preset == "corner_camera":
            metadata.update({"device_type": "corner_camera", "light_source": "status_indicator", "light_intensity": 0.02, "blink_color": "#ff0000"})
        if preset.endswith("frame"):
            metadata.update({
                "opening_type": preset.removesuffix("_frame"),
                "frame_style": str(adjusted.get("frame_style", "square")),
                "opening_hole": preset != "portal_frame",
            })
        self.push_history(f"Generate {label}")
        layer = self._ensure_named_layer(label, semantic, group, metadata)
        points = generate_preset(preset, region, adjusted, layer.id, self.current_color(), self.point_radius.get())
        remaining = max(0, min(MAX_POINTS_PER_GENERATOR, MAX_INTERACTIVE_DOCUMENT_POINTS - len(self.document.points)))
        if len(points) > remaining and remaining > 0:
            stride = max(1, int(math.ceil(len(points) / remaining)))
            points = points[::stride][:remaining]
        self.document.add_points(points)
        self.document.active_layer_id = layer.id
        self.semantic.set(semantic)
        self.finish_edit(f"{label} generated ({len(points):,} points) · {region.projection}")

    def generate_room_shell_from_region(self, region: Region3D, params: dict[str, float]) -> None:
        remaining = max(0, MAX_INTERACTIVE_DOCUMENT_POINTS - len(self.document.points))
        if remaining <= 0:
            messagebox.showwarning("Interactive point limit reached", "The project has reached its interactive point limit.", parent=self)
            return
        self.push_history("Generate guided Room Shell")
        walls = self._ensure_named_layer("Walls", "wall", "Architecture", {"pcp3_guided_preset": "room_shell_walls"})
        floor = self._ensure_named_layer("Floor", "floor", "Architecture", {"pcp3_guided_preset": "room_shell_floor"})
        ceiling = self._ensure_named_layer("Ceiling", "ceiling", "Architecture", {"pcp3_guided_preset": "room_shell_ceiling"})
        generated = generate_room_shell(
            region,
            params,
            room_width=self.document.settings.width,
            room_depth=self.document.settings.depth,
            layer_ids={"walls": walls.id, "floor": floor.id, "ceiling": ceiling.id},
            color=self.current_color(),
            point_radius=self.point_radius.get(),
        )
        total = sum(len(values) for values in generated.values())
        if total > min(MAX_POINTS_PER_GENERATOR, remaining):
            allowed = min(MAX_POINTS_PER_GENERATOR, remaining)
            if not messagebox.askyesno(
                "Room Shell density reduced for safety",
                f"The Room Shell generated {total:,} points; the safe limit is {allowed:,}. Sample the shell to the safe limit?",
                parent=self,
            ):
                return
            merged = generated["walls"] + generated["floor"] + generated["ceiling"]
            stride = max(1, int(math.ceil(len(merged) / allowed)))
            merged = merged[::stride][:allowed]
            self.document.add_points(merged)
            count = len(merged)
        else:
            for points in generated.values():
                self.document.add_points(points)
            count = total
        self.document.active_layer_id = walls.id
        self.semantic.set("wall")
        self.finish_edit(f"Guided Room Shell generated ({count:,} points) · floor, ceiling, and four walls")

    # ---------- persistent custom colors ----------
    def custom_colors_path(self) -> Path:
        return self.root_path / "user_data" / "pcp3" / "custom_colors.json"

    def _normalize_hex(self, value: str) -> str | None:
        text = value.strip().upper()
        if not text.startswith("#"):
            text = "#" + text
        if len(text) != 7 or any(character not in "#0123456789ABCDEF" for character in text):
            return None
        return text

    def _load_custom_colors(self) -> None:
        path = self.custom_colors_path()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            payload = {}
        colors = payload.get("colors", []) if isinstance(payload, dict) else []
        if isinstance(colors, list):
            for value in colors:
                normalized = self._normalize_hex(str(value))
                if normalized and normalized not in self.custom_colors:
                    self.custom_colors.append(normalized)
        self.custom_colors = self.custom_colors[:MAX_CUSTOM_COLORS]

    def _save_custom_colors(self) -> None:
        path = self.custom_colors_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps({"schema": "pcp3_custom_colors_v1", "colors": self.custom_colors[:MAX_CUSTOM_COLORS]}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def remember_custom_color(self, value: str, *, persist: bool = True) -> None:
        normalized = self._normalize_hex(value)
        if normalized is None:
            return
        self.custom_colors = [item for item in self.custom_colors if item != normalized]
        self.custom_colors.insert(0, normalized)
        del self.custom_colors[MAX_CUSTOM_COLORS:]
        if persist:
            self._save_custom_colors()
        self._refresh_custom_color_widgets()

    def _refresh_custom_color_widgets(self) -> None:
        if self.custom_color_combo is not None:
            self.custom_color_combo.configure(values=tuple(self.custom_colors))
        normalized = self._normalize_hex(self.color_hex.get()) or "#D9CC94"
        if self.custom_color_choice is not None:
            self.custom_color_choice.set(normalized)
        if self.custom_color_swatch is not None:
            self.custom_color_swatch.configure(background=normalized)

    def apply_custom_color(self) -> None:
        if self.custom_color_choice is None:
            return
        normalized = self._normalize_hex(self.custom_color_choice.get())
        if normalized is None:
            return
        self.color_hex.set(normalized.lower())
        self.color_swatch.configure(background=normalized)
        if self.custom_color_swatch is not None:
            self.custom_color_swatch.configure(background=normalized)
        self.remember_custom_color(normalized)
        self.update_status(f"Custom Color applied: {normalized}")

    def choose_color(self) -> None:
        previous = self.color_hex.get()
        super().choose_color()
        current = self.color_hex.get()
        if current != previous:
            self.remember_custom_color(current)

    def pick_nearest(self, world: tuple[float, float, float]) -> None:
        previous = self.color_hex.get()
        super().pick_nearest(world)
        if self.color_hex.get() != previous:
            self.remember_custom_color(self.color_hex.get())

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
        if text is None:
            return
        text.configure(state="normal")
        text.insert("end", "Architecture & Fixture Guided Shapes\n", "heading")
        text.insert(
            "end",
            "Use the Walls, Floors, Ceilings, Fixtures, or Openings menus in the left panel. Select a viewport border, then tune every value with both an input and slider. Cyan lines preview the generated bounds.\n\n",
        )
        text.insert("end", "Guided Room Shell\n", "heading")
        text.insert(
            "end",
            "Select a footprint in Top or a wall face in Front/Side. The dialog generates floor, ceiling, and four walls, with wall thickness plus top/bottom opening gaps.\n\n",
        )
        text.insert("end", "Custom Colors\n", "heading")
        text.insert(
            "end",
            "Newly chosen and sampled colors are retained in the Custom Colors dropdown between Reset Viewports and Reset View Angles.\n\n",
        )
        text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
