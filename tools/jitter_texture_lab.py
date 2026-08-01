#!/usr/bin/env python3
"""
SignalCloud Jitter-Based Texture Lab — standalone Tkinter GUI

Implements jG / jL / jC / jS, planetary attraction, mixing regions,
and the definition-layer visibility caps from the handwritten notes.

No pygame.  No launcher patch.

Usage:
    python3 tools/jitter_texture_lab.py
"""

from __future__ import annotations

import json
import math
import random
import tkinter as tk
from pathlib import Path
from dataclasses import dataclass, field
from tkinter import ttk
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from tools.signalcloud_studio.context import ToolContext

# Visibility caps (your missing key data)
VIS = {
    "Normal":        1.00,
    "HD Light":      0.21,
    "HD Texture":    0.28,
    "Outer Light":   0.34,
    "Outer Texture": 0.47,
    "Inner Texture": 0.57,
}

LAYERS_ORDER = [
    "Normal", "HD Light", "HD Texture",
    "Outer Light", "Outer Texture", "Inner Texture",
]


@dataclass
class Dot:
    x: float
    y: float
    r: float
    g: float
    b: float
    radius: float = 3.0
    cluster: int = 0


def planetary(radius: float, dist: float, cluster_n: int,
              same_hue: bool, same_color: bool, jitter: float) -> float:
    dist = max(dist, 1e-5)
    cluster_n = max(cluster_n, 1)
    if same_hue and not same_color:
        w = 1.0 - (radius / dist) / cluster_n
        return max(0.0, w + jitter)
    if not same_hue and not same_color:
        expected = (radius / dist) * cluster_n * 0.35
        denom = max(cluster_n - 1, 1)
        w = expected - (radius / dist) / denom
        return max(0.0, w + jitter * jitter)
    base = (radius / dist) / cluster_n
    expected = base * cluster_n
    return max(0.0, expected / cluster_n + jitter ** 3)


class JitterLab(tk.Tk):
    def __init__(self, root_path: Path | None = None):
        super().__init__()
        self.project_root = Path(root_path).expanduser().resolve() if root_path is not None else Path(__file__).resolve().parents[1]
        self.title("SignalCloud Jitter & Material Lab  (jG/jL/jC/jS + Planetary Attraction)")
        self.geometry("1200x720")
        self.minsize(900, 560)

        self.dots: List[Dot] = []
        self.layer = tk.StringVar(value="Normal")
        self.jitter_amp = tk.DoubleVar(value=0.15)
        self.cluster_radius = tk.DoubleVar(value=28.0)
        self.signal_dist = tk.DoubleVar(value=70.0)
        self.cluster_n = tk.IntVar(value=4)
        self.opacity = tk.DoubleVar(value=1.0)
        self.show_fill = tk.BooleanVar(value=True)

        self._build()
        self._seed()
        self._redraw()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Definition layer:").pack(side="left")
        ttk.Combobox(top, textvariable=self.layer, values=LAYERS_ORDER,
                     state="readonly", width=14).pack(side="left", padx=4)
        ttk.Button(top, text="Reseed", command=self._seed).pack(side="left", padx=4)
        ttk.Button(top, text="Add planetary fill", command=self._add_fill).pack(side="left", padx=4)
        ttk.Button(top, text="Edit Reception surfaces", command=self._open_surface_editor).pack(side="left", padx=4)
        ttk.Button(top, text="Edit audio interference", command=self._open_audio_editor).pack(side="left", padx=4)
        ttk.Checkbutton(top, text="Show fill dots", variable=self.show_fill,
                        command=self._redraw).pack(side="left", padx=8)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=6, pady=4)

        self.canvas = tk.Canvas(body, bg="#12121a", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._click)

        side = ttk.Frame(body, width=280)
        side.pack(side="right", fill="y", padx=(8, 0))
        side.pack_propagate(False)

        def slider(label, var, lo, hi):
            ttk.Label(side, text=label).pack(anchor="w", pady=(6, 0))
            ttk.Scale(side, from_=lo, to=hi, variable=var,
                      command=lambda v: self._redraw()).pack(fill="x")

        slider("Jitter amplitude", self.jitter_amp, 0.0, 0.8)
        slider("Cluster radius (px)", self.cluster_radius, 8, 80)
        slider("Signal distance jS (px)", self.signal_dist, 20, 160)
        slider("Opacity", self.opacity, 0.0, 1.0)

        ttk.Label(side, text="Cluster count").pack(anchor="w", pady=(6, 0))
        ttk.Spinbox(side, from_=1, to=12, textvariable=self.cluster_n,
                    command=self._redraw, width=6).pack(anchor="w")

        ttk.Label(side, text="Layer visibility (fixed)", font=("", 10, "bold")).pack(
            anchor="w", pady=(12, 2))
        self.vis_text = tk.Text(side, height=9, width=34, font=("TkFixedFont", 9))
        self.vis_text.pack(fill="x")
        for name, v in VIS.items():
            self.vis_text.insert("end", f"  {name:16s}  {v*100:5.0f}%\n")
        self.vis_text.configure(state="disabled")

        ttk.Label(side, text="Stack order (notes)", font=("", 10, "bold")).pack(
            anchor="w", pady=(10, 2))
        ttk.Label(side, text="User → HD light → HD tex → … → jG → Core\n"
                             "jG first, then jL, then jC over jL,\n"
                             "jS between jC on same texture layer.",
                  wraplength=260, justify="left").pack(anchor="w")

        self.status = tk.StringVar(value="Click canvas to place a seed dot")
        ttk.Label(self, textvariable=self.status).pack(fill="x", padx=8, pady=2)


    def _open_surface_editor(self) -> None:
        from tools.signalcloud_materials.compiler import compile_material_runtime
        from tools.signalcloud_materials.managed import (
            ensure_managed_material_set, load_surface_pattern, save_surface_pattern,
            load_surface_definition_layers, save_surface_definition_layers,
        )
        from tools.asset_doctor.asset_doctor import run as run_asset_doctor
        from tools.asset_doctor.hot_reload_bridge import stage_preview_reload

        managed = ensure_managed_material_set(self.project_root)
        if managed.created:
            run_asset_doctor(self.project_root)

        window = tk.Toplevel(self)
        window.title("Managed Reception Surface Patterns")
        window.geometry("560x610")
        window.minsize(500, 560)
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)

        surface = tk.StringVar(value="wall")
        mode = tk.StringVar(value="wallpaper_breakup")
        primary = tk.DoubleVar(value=6.8)
        secondary = tk.DoubleVar(value=7.4)
        breakup_scale = tk.DoubleVar(value=6.6)
        breakup_strength = tk.DoubleVar(value=0.50)
        displacement = tk.DoubleVar(value=0.008)
        color_weight = tk.DoubleVar(value=0.30)
        line_width = tk.DoubleVar(value=0.055)
        definition_values = {
            "HD Light": tk.DoubleVar(value=0.0),
            "HD Texture": tk.DoubleVar(value=0.28),
            "Outer Light": tk.DoubleVar(value=0.0),
            "Outer Texture": tk.DoubleVar(value=0.47),
            "Inner Texture": tk.DoubleVar(value=0.57),
        }
        status = tk.StringVar(value="Managed user copy ready. Save, then stage for F9.")

        ttk.Label(body, text="Surface", font=("", 10, "bold")).pack(anchor="w")
        surface_box = ttk.Combobox(body, textvariable=surface, values=("floor", "wall", "ceiling"), state="readonly")
        surface_box.pack(fill="x", pady=(2, 8))
        ttk.Label(body, text="Pattern mode", font=("", 10, "bold")).pack(anchor="w")
        mode_box = ttk.Combobox(body, textvariable=mode, values=("fiber_rows", "wallpaper_breakup", "flat_tiles", "legacy"), state="readonly")
        mode_box.pack(fill="x", pady=(2, 8))

        def add_slider(label: str, variable: tk.DoubleVar, lo: float, hi: float) -> None:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=22).pack(side="left")
            ttk.Scale(row, from_=lo, to=hi, variable=variable).pack(side="left", fill="x", expand=True)
            ttk.Label(row, textvariable=variable, width=7).pack(side="right", padx=(8, 0))

        add_slider("Primary spacing", primary, 0.08, 12.0)
        add_slider("Secondary spacing", secondary, 0.08, 12.0)
        add_slider("Breakup scale", breakup_scale, 0.2, 24.0)
        add_slider("Breakup strength", breakup_strength, 0.0, 1.0)
        add_slider("Displacement weight", displacement, 0.0, 1.0)
        add_slider("Color strength", color_weight, 0.0, 1.0)
        add_slider("Line width", line_width, 0.02, 0.48)
        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=(10, 5))
        ttk.Label(body, text="Definition layers", font=("", 10, "bold")).pack(anchor="w")
        for layer_name in ("HD Light", "HD Texture", "Outer Light", "Outer Texture", "Inner Texture"):
            add_slider(layer_name, definition_values[layer_name], 0.0, 1.0)

        def load_current(*_args) -> None:
            _path, pattern = load_surface_pattern(self.project_root, surface.get())
            mode.set(str(pattern.get("mode", "legacy")))
            primary.set(float(pattern.get("primary_spacing", 0.8)))
            secondary.set(float(pattern.get("secondary_spacing", 1.2)))
            breakup_scale.set(float(pattern.get("breakup_scale", 3.0)))
            breakup_strength.set(float(pattern.get("breakup_strength", 0.0)))
            displacement.set(float(pattern.get("displacement_weight", 1.0)))
            color_weight.set(float(pattern.get("color_weight", 0.68)))
            line_width.set(float(pattern.get("line_width", 0.18)))
            _layer_path, layers = load_surface_definition_layers(self.project_root, surface.get())
            by_name = {str(item.get("name")): float(item.get("opacity", 0.0)) for item in layers}
            for layer_name, variable in definition_values.items():
                variable.set(by_name.get(layer_name, 0.0))
            status.set(f"Loaded managed {surface.get()} pattern and definition layers")

        def save_current() -> None:
            pattern = {
                "mode": mode.get(),
                "primary_spacing": round(primary.get(), 4),
                "secondary_spacing": round(secondary.get(), 4),
                "breakup_scale": round(breakup_scale.get(), 4),
                "breakup_strength": round(breakup_strength.get(), 4),
                "displacement_weight": round(displacement.get(), 4),
                "color_weight": round(color_weight.get(), 4),
                "line_width": round(line_width.get(), 4),
            }
            path = save_surface_pattern(self.project_root, surface.get(), pattern)
            layers = [
                {"name": layer_name, "opacity": round(variable.get(), 4)}
                for layer_name, variable in definition_values.items()
                if variable.get() > 0.0
            ]
            save_surface_definition_layers(self.project_root, surface.get(), layers)
            result = compile_material_runtime(self.project_root)
            status.set(f"Saved {path.name}; runtime {result.signature}. Stage for F9.")

        def stage_current() -> None:
            result = stage_preview_reload(self.project_root)
            status.set(f"Staged tx {result.transaction_id}: materials {result.changed_material_count}")

        surface_box.bind("<<ComboboxSelected>>", load_current)
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(12, 6))
        ttk.Button(controls, text="Reload", command=load_current).pack(side="left")
        ttk.Button(controls, text="Save managed copy", command=save_current).pack(side="left", padx=6)
        ttk.Button(controls, text="Stage protected preview", command=stage_current).pack(side="left")
        ttk.Label(body, textvariable=status, wraplength=510, justify="left").pack(fill="x", pady=(10, 0))
        ttk.Label(body, text="Wallpaper guidance: use sparse seams, legacy-style paper grain, no vertical periodic wave, and near-zero displacement. Carpet may keep dense rows and full displacement.", wraplength=510, justify="left").pack(fill="x", pady=(8, 0))
        load_current()

    def _open_audio_editor(self) -> None:
        from tools.signalcloud_audio.compiler import compile_audio_interference_runtime
        from tools.signalcloud_audio.managed import ensure_managed_audio_profile, load_profile, save_profile
        from tools.asset_doctor.asset_doctor import run as run_asset_doctor
        from tools.asset_doctor.hot_reload_bridge import stage_preview_reload

        managed = ensure_managed_audio_profile(self.project_root)
        if managed.created:
            run_asset_doctor(self.project_root)
        window = tk.Toplevel(self)
        window.title("Managed Audio Interference")
        window.geometry("560x640")
        window.minsize(500, 580)
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)

        band = tk.StringVar(value="low")
        strength = tk.DoubleVar(value=0.82)
        duration = tk.DoubleVar(value=1.08)
        obstruction = tk.DoubleVar(value=0.12)
        radius_scale = tk.DoubleVar(value=1.18)
        wave_count = tk.IntVar(value=3)
        wave_sharpness = tk.DoubleVar(value=0.72)
        displacement = tk.DoubleVar(value=0.82)
        color_mix = tk.DoubleVar(value=0.34)
        visibility_floor = tk.DoubleVar(value=0.08)
        hearing = tk.DoubleVar(value=0.86)
        cooldown = tk.DoubleVar(value=7.5)
        status = tk.StringVar(value="Managed audio profile ready. Save, then stage for F9.")

        ttk.Label(body, text="Frequency band", font=("", 10, "bold")).pack(anchor="w")
        ttk.Combobox(body, textvariable=band, values=("low", "mid", "high", "broadband"),
                     state="readonly").pack(fill="x", pady=(2, 8))

        def add_slider(label: str, variable, lo: float, hi: float) -> None:
            row = ttk.Frame(body)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=24).pack(side="left")
            ttk.Scale(row, from_=lo, to=hi, variable=variable).pack(side="left", fill="x", expand=True)
            ttk.Label(row, textvariable=variable, width=7).pack(side="right", padx=(8, 0))

        add_slider("Event strength", strength, 0.08, 1.0)
        add_slider("Duration seconds", duration, 0.18, 1.8)
        add_slider("Obstruction path", obstruction, 0.0, 1.0)
        add_slider("Radius scale", radius_scale, 0.35, 2.0)
        ttk.Label(body, text="Wave count").pack(anchor="w", pady=(5, 0))
        ttk.Spinbox(body, from_=1, to=8, textvariable=wave_count, width=8).pack(anchor="w")
        add_slider("Wave sharpness", wave_sharpness, 0.08, 1.0)
        add_slider("Displacement scale", displacement, 0.0, 1.5)
        add_slider("Color mix", color_mix, 0.0, 1.0)
        add_slider("Visibility floor", visibility_floor, 0.0, 0.4)
        add_slider("AI hearing loudness", hearing, 0.08, 1.25)
        add_slider("Cooldown seconds", cooldown, 0.5, 20.0)

        def load_current() -> None:
            _path, payload = load_profile(self.project_root)
            event = payload.get("event", {})
            visual = payload.get("visual", {})
            gameplay = payload.get("gameplay", {})
            band.set(str(payload.get("frequency_band", "low")))
            strength.set(float(event.get("strength", 0.82)))
            duration.set(float(event.get("duration_seconds", 1.08)))
            obstruction.set(float(event.get("obstruction_path", 0.12)))
            radius_scale.set(float(visual.get("radius_scale", 1.18)))
            wave_count.set(int(visual.get("wave_count", 3)))
            wave_sharpness.set(float(visual.get("wave_sharpness", 0.72)))
            displacement.set(float(visual.get("displacement_scale", 0.82)))
            color_mix.set(float(visual.get("color_mix", 0.34)))
            visibility_floor.set(float(visual.get("visibility_floor", 0.08)))
            hearing.set(float(gameplay.get("hearing_loudness", 0.86)))
            cooldown.set(float(gameplay.get("cooldown_seconds", 7.5)))
            status.set("Loaded managed Hash Dog audio-interference profile")

        def save_current() -> None:
            path = save_profile(self.project_root, {
                "frequency_band": band.get(),
                "strength": round(strength.get(), 4),
                "duration_seconds": round(duration.get(), 4),
                "obstruction_path": round(obstruction.get(), 4),
                "radius_scale": round(radius_scale.get(), 4),
                "wave_count": int(wave_count.get()),
                "wave_sharpness": round(wave_sharpness.get(), 4),
                "displacement_scale": round(displacement.get(), 4),
                "color_mix": round(color_mix.get(), 4),
                "visibility_floor": round(visibility_floor.get(), 4),
                "hearing_loudness": round(hearing.get(), 4),
                "cooldown_seconds": round(cooldown.get(), 4),
            })
            compiled = compile_audio_interference_runtime(self.project_root)
            status.set(f"Saved {path.name}; runtime {compiled.signature}. Stage for F9.")

        def stage_current() -> None:
            run_asset_doctor(self.project_root)
            result = stage_preview_reload(self.project_root)
            status.set(f"Staged tx {result.transaction_id}: audio {result.changed_audio_count}")

        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(12, 6))
        ttk.Button(controls, text="Reload", command=load_current).pack(side="left")
        ttk.Button(controls, text="Save managed copy", command=save_current).pack(side="left", padx=6)
        ttk.Button(controls, text="Stage protected preview", command=stage_current).pack(side="left")
        ttk.Label(body, textvariable=status, wraplength=510, justify="left").pack(fill="x", pady=(10, 0))
        ttk.Label(body, text="Gameplay hearing stays analytic. These controls author the matching bounded visual ripple, hearing loudness, and cooldown without rewriting resident points.",
                  wraplength=510, justify="left").pack(fill="x", pady=(8, 0))
        load_current()

    def _seed(self) -> None:
        self.dots.clear()
        random.seed(42)
        for i in range(18):
            self.dots.append(Dot(
                x=random.uniform(80, 520),
                y=random.uniform(60, 420),
                r=random.uniform(0.55, 0.95),
                g=random.uniform(0.45, 0.85),
                b=random.uniform(0.35, 0.75),
                radius=random.uniform(3, 6),
                cluster=i % max(1, self.cluster_n.get()),
            ))
        self._redraw()

    def _click(self, evt) -> None:
        self.dots.append(Dot(evt.x, evt.y, 0.9, 0.75, 0.5, 5.0, 0))
        self.status.set(f"Seed dot at ({evt.x}, {evt.y})")
        self._redraw()

    def _add_fill(self) -> None:
        """Place smaller mixed-color dots in empty gaps (planetary attraction)."""
        if len(self.dots) < 2:
            return
        amp = self.jitter_amp.get()
        cr = self.cluster_radius.get()
        cn = max(1, self.cluster_n.get())
        new: List[Dot] = []
        for i, a in enumerate(self.dots):
            for b in self.dots[i + 1:]:
                dist = math.hypot(a.x - b.x, a.y - b.y)
                if dist < 8 or dist > cr * 2.2:
                    continue
                same_color = abs(a.r - b.r) < 0.08 and abs(a.g - b.g) < 0.08
                same_hue = abs(a.r - b.r) < 0.2  # crude hue proxy
                w = planetary(cr, dist, cn, same_hue, same_color, amp)
                if w < 0.25:
                    continue
                t = 0.5
                mx = (a.x + b.x) / 2 + random.uniform(-amp, amp) * 20
                my = (a.y + b.y) / 2 + random.uniform(-amp, amp) * 20
                new.append(Dot(
                    mx, my,
                    a.r * (1 - t) + b.r * t,
                    a.g * (1 - t) + b.g * t,
                    a.b * (1 - t) + b.b * t,
                    radius=max(1.5, min(a.radius, b.radius) * 0.55),
                    cluster=a.cluster,
                ))
        self.dots.extend(new[:40])  # cap
        self.status.set(f"Added {min(len(new), 40)} planetary fill dots")
        self._redraw()

    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 20:
            return

        layer = self.layer.get()
        vis = VIS.get(layer, 1.0)
        op = self.opacity.get()
        alpha = vis * op  # effective visibility

        # layer tint background
        bg = int(18 + 40 * (1.0 - vis))
        c.configure(bg="#%02x%02x%02x" % (bg, bg, bg + 8))

        # cluster rings (jC)
        cr = self.cluster_radius.get()
        seen = set()
        for d in self.dots:
            if d.cluster in seen:
                continue
            seen.add(d.cluster)
            # centroid of cluster
            members = [x for x in self.dots if x.cluster == d.cluster]
            if not members:
                continue
            cx = sum(m.x for m in members) / len(members)
            cy = sum(m.y for m in members) / len(members)
            c.create_oval(cx - cr, cy - cr, cx + cr, cy + cr,
                          outline="#334455", dash=(3, 3))

        # signal distance guide (jS)
        sd = self.signal_dist.get()
        c.create_line(20, h - 20, 20 + sd, h - 20, fill="#445566", width=2,
                      arrow=tk.LAST)
        c.create_text(20 + sd / 2, h - 32, text=f"jS {sd:.0f}px", fill="#667788",
                      font=("", 8))

        # dots
        for d in self.dots:
            r = int(min(255, d.r * 255 * alpha + 20))
            g = int(min(255, d.g * 255 * alpha + 20))
            b = int(min(255, d.b * 255 * alpha + 20))
            fill = "#%02x%02x%02x" % (r, g, b)
            rad = d.radius
            c.create_oval(d.x - rad, d.y - rad, d.x + rad, d.y + rad,
                          fill=fill, outline="")

        # HUD
        c.create_text(12, 14, anchor="nw", fill="#99aabb", font=("", 10, "bold"),
                      text=f"Layer: {layer}   visibility {vis*100:.0f}%   "
                           f"effective α={alpha:.2f}")
        c.create_text(12, 34, anchor="nw", fill="#778899", font=("", 9),
                      text="jG base → jL → jC over jL → jS between clusters   |   "
                           "3D brush paints these layers directly")


def main(
    root_path: Path | None = None,
    context: "ToolContext | None" = None,
) -> int:
    root = context.project_root if context is not None else root_path
    JitterLab(root_path=root).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
