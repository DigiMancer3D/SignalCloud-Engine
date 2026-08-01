#!/usr/bin/env python3
"""
SignalCloud Illuminosity Light Lab — standalone Tkinter GUI

Implements the handwritten light-source / aperture / i% / day-night design
as a self-contained tool.  Does NOT patch or depend on the SignalCloud
launcher.  Optionally discovers a nearby SignalCloud tree for config
defaults; runs fully offline if none is present.

Requires only: Python 3 + Tkinter (already used by SignalCloud tools).
No pygame, no SDL, no extra packages.

Usage:
    python3 light_lab_gui.py
    python3 light_lab_gui.py /path/to/Almond_Signal_...
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

if TYPE_CHECKING:
    from tools.signalcloud_studio.context import ToolContext

# ---------------------------------------------------------------------------
# Constants from the handwritten notes
# ---------------------------------------------------------------------------

BOX_MIN = -12.0
BOX_MAX = 12.0
BOX_HEIGHT = 6.0

QUALITY_BANDS = [
    (3.0,   "DARKNESS / NO LIGHT"),
    (29.0,  "OUTLINES & SILHOUETTES (¼ dist)"),
    (45.0,  "LOW LIGHT (½ dist)"),
    (65.0,  "LOW LIGHT (norm dist)"),
    (77.0,  "GOOD LIGHT"),
    (89.0,  "GREAT LIGHT"),
    (110.0, "BEST"),
    (1e9,   "BEST + DISTANCE BOOST"),
]

REFLECTION_COST = 1.0 / 3.0   # 1 i% per ~3 % of reflection segment


def quality_name(i: float) -> str:
    for limit, name in QUALITY_BANDS:
        if i <= limit:
            return name
    return QUALITY_BANDS[-1][1]


def degree_burst(i_pct: float, ap_distance: float) -> float:
    """( (i%/3) - i% ) - AP  from the notes."""
    return (i_pct / 3.0 - i_pct) - ap_distance


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def dist(self, o: "Vec3") -> float:
        return math.sqrt((self.x - o.x) ** 2 + (self.y - o.y) ** 2 + (self.z - o.z) ** 2)


@dataclass
class LightSource:
    pos: Vec3
    target: Vec3
    i_pct: float = 70.0
    radius: float = 9.0
    color: Tuple[float, float, float] = (1.0, 0.92, 0.75)
    is_global: bool = False
    selected: bool = False
    name: str = "Local"
    scope: str = "local"
    extra_fields: dict[str, Any] = field(default_factory=dict)

    def remaining_at(self, sample: Vec3, ap_dist: float = 2.5) -> float:
        d = self.pos.dist(sample)
        if d > self.radius * 1.6:
            return 0.0
        fall = max(0.0, 1.0 - d / self.radius)
        cost = REFLECTION_COST * (d / self.radius) * 100.0 * 0.35
        return max(0.0, self.i_pct * fall - cost)


@dataclass
class Aperture:
    pos: Vec3 = field(default_factory=lambda: Vec3(0, 1.6, 0))
    distance: float = 2.5
    color: Tuple[float, float, float] = (0.9, 0.85, 0.7)
    half_width: float = 1.2
    bottom_y: float = 0.4
    top_y: float = 2.8


@dataclass
class DayNight:
    day_color: Tuple[float, float, float] = (1.0, 0.95, 0.85)
    day_i: float = 95.0
    night_color: Tuple[float, float, float] = (0.15, 0.18, 0.35)
    night_i: float = 18.0
    day_to_night_s: float = 45.0
    night_to_day_s: float = 60.0
    time_of_day: float = 0.35
    playing: bool = False
    paused: bool = False
    extra_fields: dict[str, Any] = field(default_factory=dict)

    def colors(self) -> Tuple[Tuple[float, float, float], float]:
        t = self.time_of_day
        if t < 0.25:
            night_w = 1.0 - t * 4.0
        elif t < 0.75:
            night_w = 0.0
        else:
            night_w = (t - 0.75) * 4.0
        col = tuple(
            self.day_color[i] * (1 - night_w) + self.night_color[i] * night_w
            for i in range(3)
        )
        i_val = self.day_i * (1 - night_w) + self.night_i * night_w
        return col, i_val  # type: ignore

    def tick(self, dt: float) -> None:
        if not self.playing or self.paused:
            return
        period = self.day_to_night_s if self.time_of_day < 0.5 else self.night_to_day_s
        self.time_of_day += dt / (period * 2.0)
        if self.time_of_day >= 1.0:
            self.time_of_day -= 1.0


# ---------------------------------------------------------------------------
# Optional SignalCloud discovery (read-only)
# ---------------------------------------------------------------------------

def find_signalcloud_root(start: Optional[Path] = None) -> Optional[Path]:
    p = (start or Path.cwd()).resolve()
    for _ in range(8):
        markers = [
            p / "scripts" / "setup_dev_environment.sh",
            p / "tools" / "signalcloud_launcher.py",
            p / "config" / "renderer.udata",
            p / "engine" / "render" / "point_renderer.hpp",
        ]
        if any(m.exists() for m in markers):
            return p
        if p.parent == p:
            break
        p = p.parent
    return None


LIGHT_SET_SCHEMA = "signalcloud_light_set_v1"


def _vec_to_json(value: Vec3) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def _vec_from_json(value: Any, fallback: Vec3 | None = None) -> Vec3:
    default = fallback or Vec3()
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return Vec3(default.x, default.y, default.z)
    try:
        return Vec3(float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError):
        return Vec3(default.x, default.y, default.z)


def _color_from_json(value: Any, fallback: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return fallback
    try:
        return tuple(clamp(float(value[i]), 0.0, 1.0) for i in range(3))  # type: ignore[return-value]
    except (TypeError, ValueError):
        return fallback


def _float_from_json(value: Any, fallback: float, *, minimum: Optional[float] = None) -> float:
    try:
        result = float(value)
        if not math.isfinite(result):
            return fallback
    except (TypeError, ValueError):
        return fallback
    if minimum is not None:
        result = max(minimum, result)
    return result


def light_set_to_json(
    lights: List[LightSource],
    aperture: Aperture,
    daynight: DayNight,
    *,
    unknown_fields: Optional[dict[str, Any]] = None,
    linked_document: Optional[str] = None,
) -> dict[str, Any]:
    value = dict(unknown_fields or {})
    value.update(
        {
            "schema": LIGHT_SET_SCHEMA,
            "linked_document": linked_document,
            "lights": [
                {
                    **dict(light.extra_fields),
                    "name": light.name,
                    "position": _vec_to_json(light.pos),
                    "target": _vec_to_json(light.target),
                    "illuminosity_percent": float(light.i_pct),
                    "radius": float(light.radius),
                    "color": list(light.color),
                    "scope": (
                        "global"
                        if light.is_global
                        else light.scope
                        if light.scope in {"local", "area", "room"}
                        else "local"
                    ),
                }
                for light in lights
            ],
            "aperture": {
                "position": _vec_to_json(aperture.pos),
                "distance": float(aperture.distance),
                "color": list(aperture.color),
                "half_width": float(aperture.half_width),
                "bottom_y": float(aperture.bottom_y),
                "top_y": float(aperture.top_y),
            },
            "day_night": {
                **dict(daynight.extra_fields),
                "day_color": list(daynight.day_color),
                "day_illuminosity_percent": float(daynight.day_i),
                "night_color": list(daynight.night_color),
                "night_illuminosity_percent": float(daynight.night_i),
                "day_to_night_seconds": float(daynight.day_to_night_s),
                "night_to_day_seconds": float(daynight.night_to_day_s),
                "time_of_day": float(daynight.time_of_day),
                "playing": bool(daynight.playing),
                "paused": bool(daynight.paused),
            },
        }
    )
    return value


def light_set_from_json(
    value: Any,
) -> tuple[List[LightSource], Aperture, DayNight, dict[str, Any], Optional[str]]:
    if not isinstance(value, dict):
        raise ValueError("light set root must be a JSON object")
    known = {"schema", "linked_document", "lights", "aperture", "day_night"}
    unknown = {key: item for key, item in value.items() if key not in known}

    lights: List[LightSource] = []
    raw_lights = value.get("lights", [])
    if isinstance(raw_lights, list):
        for index, raw in enumerate(raw_lights):
            if not isinstance(raw, dict):
                continue
            scope = str(raw.get("scope", "local")).lower()
            if scope not in {"local", "area", "room", "global"}:
                scope = "local"
            known_light = {
                "name", "position", "target", "illuminosity_percent",
                "radius", "color", "scope",
            }
            lights.append(
                LightSource(
                    pos=_vec_from_json(raw.get("position")),
                    target=_vec_from_json(raw.get("target")),
                    i_pct=_float_from_json(raw.get("illuminosity_percent"), 70.0, minimum=0.0),
                    radius=_float_from_json(raw.get("radius"), 9.0, minimum=0.05),
                    color=_color_from_json(raw.get("color"), (1.0, 0.92, 0.75)),
                    is_global=scope == "global",
                    selected=False,
                    name=str(raw.get("name", f"Light_{index + 1}")),
                    scope=scope,
                    extra_fields={key: item for key, item in raw.items() if key not in known_light},
                )
            )

    raw_aperture = value.get("aperture", {})
    if not isinstance(raw_aperture, dict):
        raw_aperture = {}
    aperture = Aperture(
        pos=_vec_from_json(raw_aperture.get("position"), Vec3(0, 1.6, 0)),
        distance=_float_from_json(raw_aperture.get("distance"), 2.5, minimum=0.05),
        color=_color_from_json(raw_aperture.get("color"), (0.9, 0.85, 0.7)),
        half_width=_float_from_json(raw_aperture.get("half_width"), 1.2, minimum=0.05),
        bottom_y=_float_from_json(raw_aperture.get("bottom_y"), 0.4),
        top_y=_float_from_json(raw_aperture.get("top_y"), 2.8),
    )

    raw_daynight = value.get("day_night", {})
    if not isinstance(raw_daynight, dict):
        raw_daynight = {}
    known_daynight = {
        "day_color", "day_illuminosity_percent", "night_color",
        "night_illuminosity_percent", "day_to_night_seconds",
        "night_to_day_seconds", "time_of_day", "playing", "paused",
    }
    daynight = DayNight(
        day_color=_color_from_json(raw_daynight.get("day_color"), (1.0, 0.95, 0.85)),
        day_i=_float_from_json(raw_daynight.get("day_illuminosity_percent"), 95.0, minimum=0.0),
        night_color=_color_from_json(raw_daynight.get("night_color"), (0.15, 0.18, 0.35)),
        night_i=_float_from_json(raw_daynight.get("night_illuminosity_percent"), 18.0, minimum=0.0),
        day_to_night_s=_float_from_json(raw_daynight.get("day_to_night_seconds"), 45.0, minimum=1.0),
        night_to_day_s=_float_from_json(raw_daynight.get("night_to_day_seconds"), 60.0, minimum=1.0),
        time_of_day=_float_from_json(raw_daynight.get("time_of_day"), 0.35) % 1.0,
        playing=bool(raw_daynight.get("playing", False)),
        paused=bool(raw_daynight.get("paused", False)),
        extra_fields={key: item for key, item in raw_daynight.items() if key not in known_daynight},
    )
    linked = value.get("linked_document")
    return lights, aperture, daynight, unknown, str(linked) if linked else None


def read_light_set(path: Path) -> tuple[List[LightSource], Aperture, DayNight, dict[str, Any], Optional[str]]:
    return light_set_from_json(json.loads(Path(path).read_text(encoding="utf-8")))


def write_light_set(
    path: Path,
    lights: List[LightSource],
    aperture: Aperture,
    daynight: DayNight,
    *,
    unknown_fields: Optional[dict[str, Any]] = None,
    linked_document: Optional[str] = None,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            light_set_to_json(
                lights,
                aperture,
                daynight,
                unknown_fields=unknown_fields,
                linked_document=linked_document,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class LightLabApp(tk.Tk):
    def __init__(
        self,
        sc_root: Optional[Path] = None,
        studio_context: Optional["ToolContext"] = None,
    ):
        super().__init__()
        self.title("SignalCloud Studio — Illuminosity Light Lab")
        self.geometry("1180x720")
        self.minsize(900, 560)

        self.studio_context = studio_context
        self.sc_root = (
            Path(studio_context.project_root).resolve()
            if studio_context is not None
            else (sc_root or find_signalcloud_root())
        )
        self.document_path: Optional[Path] = None
        self.document_unknown: dict[str, Any] = {}
        self.linked_document: Optional[str] = None
        self.document_dirty = False
        self._suspend_dirty = True
        self.lights: List[LightSource] = []
        self.aperture = Aperture()
        self.daynight = DayNight()
        self.active_idx: int = -1
        self.mode = "idle"
        self.pending_pos: Optional[Vec3] = None
        self.drag_start: Optional[Tuple[float, float]] = None
        self.select_rect: Optional[Tuple[float, float, float, float]] = None
        self.last_click_time = 0.0
        self.last_click_btn = 0
        self.view_cx = 0.0
        self.view_cz = 0.0
        self.view_scale = 18.0

        if not self._load_shared_light_document():
            self._seed_demo_lights()
        self._build_ui()
        self._suspend_dirty = False
        self._update_document_label()
        self._redraw()
        self.after(50, self._tick)

        if self.document_path is not None:
            self.status.set(f"Loaded light set: {self.document_path.name}")
        elif self.sc_root:
            self.status.set(f"SignalCloud project detected: {self.sc_root.name}")
        else:
            self.status.set("Standalone mode — no SignalCloud tree nearby")

    def _managed_light_dir(self) -> Path:
        root = self.sc_root or Path.cwd()
        return Path(root) / "content" / "user" / "lights"

    def _load_shared_light_document(self) -> bool:
        if self.studio_context is None or self.sc_root is None:
            return False
        shared = self.studio_context.document_context
        if shared is None:
            return False
        if shared.active_document and shared.document_kind == "light_set":
            candidate = (Path(self.sc_root) / shared.active_document).resolve()
            try:
                candidate.relative_to(Path(self.sc_root).resolve())
            except ValueError:
                return False
            if candidate.is_file():
                try:
                    self._load_document_data(candidate)
                    return True
                except (OSError, ValueError, json.JSONDecodeError, TypeError):
                    return False
        if shared.active_document:
            self.linked_document = shared.active_document
        return False

    def _load_document_data(self, path: Path) -> None:
        lights, aperture, daynight, unknown, linked = read_light_set(path)
        self.lights = lights
        self.aperture = aperture
        self.daynight = daynight
        self.document_unknown = unknown
        self.linked_document = linked
        self.document_path = Path(path).resolve()
        self.document_dirty = False
        self.active_idx = 0 if self.lights else -1

    def _update_document_label(self) -> None:
        if not hasattr(self, "document_label"):
            return
        if self.document_path is not None:
            name = self.document_path.name
        else:
            name = "Untitled light set"
        dirty = " *" if self.document_dirty else ""
        linked = f" | linked: {Path(self.linked_document).name}" if self.linked_document else ""
        self.document_label.set(f"Shared document: {name}{dirty}{linked}")

    def _publish_document_state(self, *, dirty: bool) -> None:
        if self.document_path is None:
            self._update_document_label()
            return
        if self.studio_context is None or self.studio_context.document_store is None:
            self._update_document_label()
            return
        previous = self.studio_context.document_context
        linked_documents: tuple[str, ...] = ()
        if self.linked_document:
            linked_documents = (self.linked_document,)
        active_document: Optional[Path] = self.document_path
        updated = self.studio_context.document_store.publish(
            previous,
            active_document=active_document,
            document_kind="light_set",
            owner_tool="light-lab",
            dirty=dirty,
            linked_documents=linked_documents,
            metadata={"light_count": len(self.lights), "format": LIGHT_SET_SCHEMA},
        )
        self.studio_context.document_context = updated
        if self.studio_context.document_bus is not None:
            self.studio_context.document_bus.publish(updated)
        self._update_document_label()

    def _mark_dirty(self) -> None:
        if self._suspend_dirty:
            return
        self.document_dirty = True
        self._publish_document_state(dirty=True)

    def _new_document(self) -> None:
        self.linked_document = None
        current = None
        if self.studio_context is not None:
            current = self.studio_context.document_context
        if current is not None and current.active_document and current.document_kind != "light_set":
            self.linked_document = current.active_document
        self.document_path = None
        self.document_unknown = {}
        self._seed_demo_lights()
        self.document_dirty = True
        self._refresh_list()
        self._load_props()
        self._update_document_label()
        self.status.set("Created a new managed light set")
        self._redraw()

    def _validate_managed_path(self, path: Path) -> bool:
        if self.studio_context is None or self.sc_root is None:
            return True
        try:
            path.resolve().relative_to(Path(self.sc_root).resolve())
            return True
        except ValueError:
            messagebox.showerror(
                "Managed SignalCloud content",
                "Studio light sets must be saved inside the current SignalCloud project.",
            )
            return False

    def _open_document(self) -> None:
        initial = self._managed_light_dir()
        initial.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.askopenfilename(
            title="Open SignalCloud light set",
            initialdir=initial,
            filetypes=(("SignalCloud light sets", "*.slight *.sclight"), ("Canonical SignalCloud light", "*.sclight"), ("Legacy SignalCloud light", "*.slight"), ("JSON", "*.json"), ("All files", "*")),
        )
        if not chosen:
            return
        path = Path(chosen)
        if not self._validate_managed_path(path):
            return
        try:
            self._load_document_data(path)
        except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
            messagebox.showerror("Open light set", str(exc))
            return
        self._suspend_dirty = True
        try:
            self.var_ap_dist.set(self.aperture.distance)
            self.scale_dn.set(self.daynight.day_to_night_s)
            self.scale_nd.set(self.daynight.night_to_day_s)
        finally:
            self._suspend_dirty = False
        self._refresh_list()
        self._load_props()
        self._publish_document_state(dirty=False)
        self.status.set(f"Opened {path.name}")
        self._redraw()

    def _next_default_document_path(self) -> Path:
        directory = self._managed_light_dir()
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(1, 10000):
            candidate = directory / f"light_set_{index:03d}.slight"
            if not candidate.exists():
                return candidate
        raise RuntimeError("no free managed light-set filename remains")

    def _save_document(self) -> None:
        path = self.document_path or self._next_default_document_path()
        if not self._validate_managed_path(path):
            return
        try:
            write_light_set(
                path,
                self.lights,
                self.aperture,
                self.daynight,
                unknown_fields=self.document_unknown,
                linked_document=self.linked_document,
            )
        except OSError as exc:
            messagebox.showerror("Save light set", str(exc))
            return
        self.document_path = path.resolve()
        self.document_dirty = False
        self._publish_document_state(dirty=False)
        self.status.set(f"Saved {path.name}")

    def _save_document_as(self) -> None:
        initial = self._managed_light_dir()
        initial.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            title="Save SignalCloud light set",
            initialdir=initial,
            defaultextension=".slight",
            filetypes=(("SignalCloud light set", "*.slight"), ("JSON", "*.json")),
        )
        if not chosen:
            return
        path = Path(chosen)
        if not self._validate_managed_path(path):
            return
        self.document_path = path
        self._save_document()

    def _export_sclight(self) -> None:
        if self.sc_root is None:
            messagebox.showerror("Export .sclight", "A SignalCloud project root is required for managed export.")
            return
        if self.document_dirty or self.document_path is None:
            self._save_document()
        if self.document_path is None:
            return
        initial = self._managed_light_dir()
        initial.mkdir(parents=True, exist_ok=True)
        chosen = filedialog.asksaveasfilename(
            title="Export canonical SignalCloud light",
            initialdir=initial,
            defaultextension=".sclight",
            filetypes=(("Canonical SignalCloud light", "*.sclight"),),
        )
        if not chosen:
            return
        output = Path(chosen)
        if not self._validate_managed_path(output):
            return
        try:
            from tools.signalcloud_lighting.exporter import export_sclight
            exported = export_sclight(Path(self.sc_root), source=self.document_path, output=output)
        except Exception as exc:
            messagebox.showerror("Export .sclight", str(exc))
            return
        self.status.set(f"Exported canonical light set: {exported.name}")

    def _build_ui(self) -> None:
        action_bar = ttk.Frame(self, padding=(6, 5))
        action_bar.pack(fill="x")
        ttk.Button(action_bar, text="New Light Set", command=self._new_document).pack(side="left", padx=2)
        ttk.Button(action_bar, text="Open…", command=self._open_document).pack(side="left", padx=2)
        ttk.Button(action_bar, text="Save", command=self._save_document).pack(side="left", padx=2)
        ttk.Button(action_bar, text="Save As…", command=self._save_document_as).pack(side="left", padx=2)
        ttk.Button(action_bar, text="Export .sclight", command=self._export_sclight).pack(side="left", padx=2)
        self.document_label = tk.StringVar(value="Shared document: none")
        ttk.Label(action_bar, textvariable=self.document_label, anchor="e").pack(
            side="right", fill="x", expand=True, padx=8
        )

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", padx=8, pady=2)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=6, pady=4)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, bg="#1a1a22", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_left_down)
        self.canvas.bind("<B1-Motion>", self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_up)
        self.canvas.bind("<Button-3>", self._on_right_down)
        self.canvas.bind("<B3-Motion>", self._on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_up)
        self.canvas.bind("<Double-Button-1>", self._on_double_left)
        self.canvas.bind("<Double-Button-3>", self._on_double_right)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

        right = ttk.Frame(body, width=320)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)

        ttk.Label(right, text="SIDE PANEL", font=("", 11, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(right, text="Lights").pack(anchor="w")
        self.listbox = tk.Listbox(right, height=8, exportselection=False)
        self.listbox.pack(fill="x", pady=2)
        self.listbox.bind("<<ListboxSelect>>", self._on_list_select)

        btn_row = ttk.Frame(right)
        btn_row.pack(fill="x", pady=2)
        ttk.Button(btn_row, text="Add (click view)", command=self._start_place).pack(side="left", padx=1)
        ttk.Button(btn_row, text="Delete", command=self._delete_active).pack(side="left", padx=1)
        ttk.Button(btn_row, text="Clear sel", command=self._clear_selection).pack(side="left", padx=1)

        self.prop = ttk.LabelFrame(right, text="Active light / Global defaults")
        self.prop.pack(fill="x", pady=6)

        self.var_name = tk.StringVar()
        self.var_i = tk.DoubleVar(value=70)
        self.var_radius = tk.DoubleVar(value=9)
        self.var_global = tk.BooleanVar(value=False)
        self.var_pos = tk.StringVar(value="—")
        self.var_target = tk.StringVar(value="—")
        self.var_burst = tk.StringVar(value="—")
        self.var_quality = tk.StringVar(value="—")

        def row(label, var, width=12):
            f = ttk.Frame(self.prop)
            f.pack(fill="x", pady=1)
            ttk.Label(f, text=label, width=10).pack(side="left")
            ttk.Entry(f, textvariable=var, width=width).pack(side="left", fill="x", expand=True)

        row("Name", self.var_name)
        row("i %", self.var_i)
        row("Radius", self.var_radius)
        row("Pos", self.var_pos)
        row("Target", self.var_target)

        f = ttk.Frame(self.prop)
        f.pack(fill="x", pady=1)
        ttk.Checkbutton(f, text="Global (cannot delete / region-select)",
                        variable=self.var_global,
                        command=self._apply_props).pack(anchor="w")

        f = ttk.Frame(self.prop)
        f.pack(fill="x", pady=1)
        ttk.Label(f, text="Degree burst").pack(side="left")
        ttk.Label(f, textvariable=self.var_burst).pack(side="left", padx=4)

        f = ttk.Frame(self.prop)
        f.pack(fill="x", pady=1)
        ttk.Label(f, text="Quality @ centre").pack(side="left")
        ttk.Label(f, textvariable=self.var_quality, wraplength=200).pack(side="left", padx=4)

        ttk.Button(self.prop, text="Apply changes", command=self._apply_props).pack(fill="x", pady=4)
        ttk.Button(self.prop, text="Pick colour…", command=self._pick_color).pack(fill="x")

        ap = ttk.LabelFrame(right, text="Aperture (AP)")
        ap.pack(fill="x", pady=4)
        self.var_ap_dist = tk.DoubleVar(value=self.aperture.distance)
        f = ttk.Frame(ap)
        f.pack(fill="x")
        ttk.Label(f, text="AP distance", width=12).pack(side="left")
        ttk.Scale(f, from_=0.5, to=8.0, variable=self.var_ap_dist,
                  command=lambda v: self._on_ap_change()).pack(side="left", fill="x", expand=True)

        probe = ttk.LabelFrame(right, text="Probe sample point")
        probe.pack(fill="x", pady=4)
        self.var_probe = tk.StringVar(value="0 1.5 0")
        ttk.Entry(probe, textvariable=self.var_probe).pack(fill="x", padx=2, pady=2)
        ttk.Button(probe, text="Probe quality", command=self._probe).pack(fill="x", padx=2, pady=2)
        self.probe_out = tk.Text(probe, height=5, width=36, wrap="word", font=("TkFixedFont", 9))
        self.probe_out.pack(fill="x", padx=2, pady=2)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=6, pady=6)

        left_bar = ttk.Frame(bottom)
        left_bar.pack(side="left", fill="x", expand=True)
        ttk.Label(left_bar, text="Day → Night (s)").pack(anchor="w")
        self.lbl_dn = ttk.Label(
            left_bar, text=f"{self.daynight.day_to_night_s:.0f} s"
        )
        self.scale_dn = ttk.Scale(left_bar, from_=30, to=90, orient="horizontal",
                                  command=self._on_dn_scale)
        self.scale_dn.pack(fill="x")
        self.lbl_dn.pack(anchor="w")
        # ttk.Scale.set() may invoke the callback immediately on some Tk builds,
        # so the target label must already exist.
        self.scale_dn.set(self.daynight.day_to_night_s)

        mid = ttk.Frame(bottom)
        mid.pack(side="left", padx=12)
        ttk.Button(mid, text="▶ Play", width=8, command=self._play).pack(side="left", padx=2)
        ttk.Button(mid, text="⏸ Pause", width=8, command=self._pause).pack(side="left", padx=2)
        ttk.Button(mid, text="⏹ Stop", width=8, command=self._stop).pack(side="left", padx=2)
        self.lbl_tod = ttk.Label(mid, text="time 0.35")
        self.lbl_tod.pack(side="left", padx=8)

        right_bar = ttk.Frame(bottom)
        right_bar.pack(side="left", fill="x", expand=True)
        ttk.Label(right_bar, text="Night → Day (s)").pack(anchor="w")
        self.lbl_nd = ttk.Label(
            right_bar, text=f"{self.daynight.night_to_day_s:.0f} s"
        )
        self.scale_nd = ttk.Scale(right_bar, from_=30, to=90, orient="horizontal",
                                  command=self._on_nd_scale)
        self.scale_nd.pack(fill="x")
        self.lbl_nd.pack(anchor="w")
        self.scale_nd.set(self.daynight.night_to_day_s)

        self._refresh_list()
        self._load_props()

    def _seed_demo_lights(self) -> None:
        self.lights = [
            LightSource(Vec3(0, 5.5, 0), Vec3(0, 0, 0), 110.0, 14.0,
                        (1.0, 0.95, 0.85), True, False, "GlobalSky"),
            LightSource(Vec3(-6, 2.2, 4), Vec3(0, 1.5, 0), 78.0, 9.0,
                        (1.0, 0.9, 0.7), False, False, "WallLamp_A"),
            LightSource(Vec3(5, 1.8, -3), Vec3(-2, 1.0, 2), 55.0, 7.0,
                        (0.95, 0.85, 0.6), False, False, "FloorSpot_B"),
        ]
        self.active_idx = 0

    def _refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        for i, L in enumerate(self.lights):
            tag = "GLOBAL" if L.is_global else "local "
            sel = " ★" if L.selected else ""
            self.listbox.insert("end", f"[{i}] {L.name:12s} {tag}  i%={L.i_pct:.0f}{sel}")
        if 0 <= self.active_idx < len(self.lights):
            self.listbox.selection_set(self.active_idx)

    def _on_list_select(self, _evt=None) -> None:
        sel = self.listbox.curselection()
        if sel:
            self.active_idx = int(sel[0])
            self._load_props()
            self._redraw()

    def _load_props(self) -> None:
        if self.active_idx < 0 or self.active_idx >= len(self.lights):
            col, gi = self.daynight.colors()
            self.var_name.set("(no local selected — Global)")
            self.var_i.set(gi)
            self.var_radius.set(14.0)
            self.var_global.set(True)
            self.var_pos.set("sky")
            self.var_target.set("—")
            self.var_burst.set(f"{degree_burst(gi, self.aperture.distance):.1f}")
            self.var_quality.set(quality_name(gi))
            self.prop.configure(text="Global light / aperture defaults")
            return
        L = self.lights[self.active_idx]
        self.var_name.set(L.name)
        self.var_i.set(L.i_pct)
        self.var_radius.set(L.radius)
        self.var_global.set(L.is_global)
        self.var_pos.set(f"{L.pos.x:.2f} {L.pos.y:.2f} {L.pos.z:.2f}")
        self.var_target.set(f"{L.target.x:.2f} {L.target.y:.2f} {L.target.z:.2f}")
        self.var_burst.set(f"{degree_burst(L.i_pct, self.aperture.distance):.1f}")
        rem = L.remaining_at(Vec3(0, 1.5, 0), self.aperture.distance)
        self.var_quality.set(quality_name(rem))
        self.prop.configure(text=f"Active: {L.name}")

    def _apply_props(self) -> None:
        if self.active_idx < 0 or self.active_idx >= len(self.lights):
            return
        L = self.lights[self.active_idx]
        L.name = self.var_name.get().strip() or L.name
        L.i_pct = float(self.var_i.get())
        L.radius = float(self.var_radius.get())
        wants_global = bool(self.var_global.get())
        if wants_global:
            L.is_global = True
            L.scope = "global"
        elif L.is_global:
            L.is_global = False
            L.scope = "local"
        self._mark_dirty()
        self._refresh_list()
        self._load_props()
        self._redraw()

    def _pick_color(self) -> None:
        if self.active_idx < 0 or self.active_idx >= len(self.lights):
            return
        L = self.lights[self.active_idx]
        rgb = tuple(int(c * 255) for c in L.color)
        result = colorchooser.askcolor(color=rgb, title="Light colour")
        if result and result[0]:
            L.color = tuple(c / 255.0 for c in result[0])
            self._mark_dirty()
            self._redraw()

    def _on_ap_change(self) -> None:
        self.aperture.distance = float(self.var_ap_dist.get())
        self._mark_dirty()
        self._load_props()
        self._redraw()

    def _on_dn_scale(self, v) -> None:
        self.daynight.day_to_night_s = float(v)
        self._mark_dirty()
        label = self.__dict__.get("lbl_dn")
        if label is not None:
            label.configure(text=f"{self.daynight.day_to_night_s:.0f} s")

    def _on_nd_scale(self, v) -> None:
        self.daynight.night_to_day_s = float(v)
        self._mark_dirty()
        label = self.__dict__.get("lbl_nd")
        if label is not None:
            label.configure(text=f"{self.daynight.night_to_day_s:.0f} s")

    def _play(self) -> None:
        self.daynight.playing = True
        self.daynight.paused = False
        self.status.set("Day/night PLAYING")

    def _pause(self) -> None:
        self.daynight.paused = not self.daynight.paused
        self.status.set("PAUSED" if self.daynight.paused else "UNPAUSED")

    def _stop(self) -> None:
        self.daynight.playing = False
        self.daynight.paused = False
        self.daynight.time_of_day = 0.35
        self._mark_dirty()
        self.status.set("STOPPED — time reset")
        self._redraw()

    def _tick(self) -> None:
        self.daynight.tick(0.05)
        self.lbl_tod.configure(text=f"time {self.daynight.time_of_day:.3f}")
        if self.daynight.playing and not self.daynight.paused:
            self._redraw()
            if self.lights and self.lights[0].is_global:
                col, gi = self.daynight.colors()
                self.lights[0].color = col  # type: ignore
                self.lights[0].i_pct = gi
        self.after(50, self._tick)

    def _probe(self) -> None:
        try:
            parts = [float(x) for x in self.var_probe.get().replace(",", " ").split()]
            sample = Vec3(*parts[:3])
        except Exception:
            messagebox.showerror("Probe", "Enter three numbers: x y z")
            return
        lines = [f"Probe ({sample.x:.2f} {sample.y:.2f} {sample.z:.2f})"]
        for L in self.lights:
            rem = L.remaining_at(sample, self.aperture.distance)
            lines.append(f"  {L.name:12s}  i% left={rem:5.1f}  → {quality_name(rem)}")
        self.probe_out.delete("1.0", "end")
        self.probe_out.insert("1.0", "\n".join(lines))

    def _canvas_to_world(self, cx: float, cy: float) -> Vec3:
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        wx = (cx - w / 2) / self.view_scale + self.view_cx
        wz = (cy - h / 2) / self.view_scale + self.view_cz
        y = 1.6
        if abs(wx) > abs(wz) and abs(wx) > BOX_MAX * 0.85:
            y = clamp(3.0, 0.3, BOX_HEIGHT - 0.3)
        elif abs(wz) > BOX_MAX * 0.85:
            y = clamp(2.5, 0.3, BOX_HEIGHT - 0.3)
        return Vec3(clamp(wx, BOX_MIN, BOX_MAX), y, clamp(wz, BOX_MIN, BOX_MAX))

    def _world_to_canvas(self, p: Vec3) -> Tuple[float, float]:
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        cx = (p.x - self.view_cx) * self.view_scale + w / 2
        cy = (p.z - self.view_cz) * self.view_scale + h / 2
        return cx, cy

    def _find_light_at(self, cx: float, cy: float, radius_px: float = 14) -> int:
        for i, L in enumerate(self.lights):
            lx, ly = self._world_to_canvas(L.pos)
            if (lx - cx) ** 2 + (ly - cy) ** 2 <= radius_px ** 2:
                return i
        return -1

    def _on_left_down(self, evt) -> None:
        now = time.time()
        self.last_click_time = now
        self.last_click_btn = 1
        self.drag_start = (evt.x, evt.y)

        if self.mode == "place_source":
            pos = self._canvas_to_world(evt.x, evt.y)
            self.pending_pos = pos
            self.mode = "place_target"
            self.status.set(f"Source at ({pos.x:.1f},{pos.y:.1f},{pos.z:.1f}) — click target")
            return

        if self.mode == "place_target" and self.pending_pos is not None:
            tgt = self._canvas_to_world(evt.x, evt.y)
            name = f"Local_{len(self.lights)}"
            self.lights.append(LightSource(self.pending_pos, tgt, 70.0, 8.0,
                                           (1.0, 0.9, 0.7), False, False, name))
            self.active_idx = len(self.lights) - 1
            self._mark_dirty()
            self.pending_pos = None
            self.mode = "idle"
            self._refresh_list()
            self._load_props()
            self.status.set(f"Created {name}")
            self._redraw()
            return

        idx = self._find_light_at(evt.x, evt.y)
        if idx >= 0:
            self.active_idx = idx
            self._refresh_list()
            self._load_props()
            self._redraw()

    def _on_left_drag(self, evt) -> None:
        if self.drag_start is None:
            return
        self.select_rect = (
            min(self.drag_start[0], evt.x), min(self.drag_start[1], evt.y),
            max(self.drag_start[0], evt.x), max(self.drag_start[1], evt.y),
        )
        self.mode = "region_select"
        self._redraw()

    def _on_left_up(self, evt) -> None:
        if self.mode == "region_select" and self.select_rect:
            x0, y0, x1, y1 = self.select_rect
            if abs(x1 - x0) > 6 or abs(y1 - y0) > 6:
                for L in self.lights:
                    if L.is_global:
                        continue
                    lx, ly = self._world_to_canvas(L.pos)
                    L.selected = x0 <= lx <= x1 and y0 <= ly <= y1
                self._refresh_list()
                self.status.set("Region select complete (globals ignored)")
        self.drag_start = None
        self.select_rect = None
        if self.mode == "region_select":
            self.mode = "idle"
        self._redraw()

    def _on_right_down(self, evt) -> None:
        self.last_click_time = time.time()
        self.last_click_btn = 3
        self.drag_start = (evt.x, evt.y)
        idx = self._find_light_at(evt.x, evt.y)
        if idx >= 0:
            L = self.lights[idx]
            if L.is_global:
                messagebox.showinfo("Delete", "Global lights cannot be deleted.")
                return
            if messagebox.askyesno("Delete", f"Delete light '{L.name}'?"):
                del self.lights[idx]
                if self.active_idx == idx:
                    self.active_idx = -1
                elif self.active_idx > idx:
                    self.active_idx -= 1
                self._mark_dirty()
                self._refresh_list()
                self._load_props()
                self._redraw()

    def _on_right_drag(self, evt) -> None:
        if self.drag_start is None:
            return
        self.select_rect = (
            min(self.drag_start[0], evt.x), min(self.drag_start[1], evt.y),
            max(self.drag_start[0], evt.x), max(self.drag_start[1], evt.y),
        )
        self.mode = "region_delete"
        self._redraw()

    def _on_right_up(self, evt) -> None:
        if self.mode == "region_delete" and self.select_rect:
            x0, y0, x1, y1 = self.select_rect
            if abs(x1 - x0) > 6 or abs(y1 - y0) > 6:
                victims = []
                for i, L in enumerate(self.lights):
                    if L.is_global:
                        continue
                    lx, ly = self._world_to_canvas(L.pos)
                    if x0 <= lx <= x1 and y0 <= ly <= y1:
                        victims.append(i)
                if victims and messagebox.askyesno("Multi-delete",
                                                   f"Delete {len(victims)} local light(s)?"):
                    for i in reversed(victims):
                        del self.lights[i]
                    self.active_idx = -1
                    self._mark_dirty()
                    self._refresh_list()
                    self._load_props()
        self.drag_start = None
        self.select_rect = None
        if self.mode == "region_delete":
            self.mode = "idle"
        self._redraw()

    def _on_double_left(self, evt) -> None:
        world = self._canvas_to_world(evt.x, evt.y)
        self.view_cx = world.x
        self.view_cz = world.z
        self.status.set(f"View centred on ({world.x:.1f}, {world.z:.1f})")
        self._redraw()

    def _on_double_right(self, evt) -> None:
        for L in self.lights:
            L.selected = False
        self.mode = "idle"
        self.select_rect = None
        self.status.set("Selection cancelled")
        self._refresh_list()
        self._redraw()

    def _start_place(self) -> None:
        self.mode = "place_source"
        self.status.set("Click a wall / floor / roof to place light source")

    def _delete_active(self) -> None:
        if self.active_idx < 0 or self.active_idx >= len(self.lights):
            return
        L = self.lights[self.active_idx]
        if L.is_global:
            messagebox.showinfo("Delete", "Global lights cannot be deleted.")
            return
        if messagebox.askyesno("Delete", f"Delete '{L.name}'?"):
            del self.lights[self.active_idx]
            self.active_idx = -1
            self._mark_dirty()
            self._refresh_list()
            self._load_props()
            self._redraw()

    def _clear_selection(self) -> None:
        for L in self.lights:
            L.selected = False
        self._refresh_list()
        self._redraw()

    def _redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return

        col, _ = self.daynight.colors()
        bg = "#%02x%02x%02x" % tuple(int(clamp(x, 0, 1) * 40 + 10) for x in col)
        c.configure(bg=bg)

        corners = [
            Vec3(BOX_MIN, 0, BOX_MIN), Vec3(BOX_MAX, 0, BOX_MIN),
            Vec3(BOX_MAX, 0, BOX_MAX), Vec3(BOX_MIN, 0, BOX_MAX),
        ]
        pts = []
        for p in corners:
            pts.extend(self._world_to_canvas(p))
        c.create_polygon(pts, outline="#556677", fill="#12121a", width=2)

        for g in range(int(BOX_MIN), int(BOX_MAX) + 1, 2):
            x0, y0 = self._world_to_canvas(Vec3(g, 0, BOX_MIN))
            x1, y1 = self._world_to_canvas(Vec3(g, 0, BOX_MAX))
            c.create_line(x0, y0, x1, y1, fill="#2a2a38")
            x0, y0 = self._world_to_canvas(Vec3(BOX_MIN, 0, g))
            x1, y1 = self._world_to_canvas(Vec3(BOX_MAX, 0, g))
            c.create_line(x0, y0, x1, y1, fill="#2a2a38")

        ax, ay = self._world_to_canvas(self.aperture.pos)
        c.create_oval(ax - 8, ay - 8, ax + 8, ay + 8, outline="#88aacc", width=2)
        c.create_text(ax, ay - 14, text="AP", fill="#88aacc", font=("", 8))

        for i, L in enumerate(self.lights):
            lx, ly = self._world_to_canvas(L.pos)
            r = max(6, L.radius * self.view_scale * 0.15)
            rgb = tuple(int(clamp(x, 0, 1) * 255) for x in L.color)
            fill = "#%02x%02x%02x" % rgb
            outline = "#ffcc44" if i == self.active_idx else ("#66ffaa" if L.selected else "#aaaaaa")
            width = 3 if (i == self.active_idx or L.selected) else 1
            c.create_oval(lx - r, ly - r, lx + r, ly + r, outline=outline, width=width)
            c.create_oval(lx - 5, ly - 5, lx + 5, ly + 5, fill=fill, outline=outline)
            tx, ty = self._world_to_canvas(L.target)
            c.create_line(lx, ly, tx, ty, fill=fill, arrow=tk.LAST, width=1)
            label = L.name + (" [G]" if L.is_global else "")
            c.create_text(lx, ly + r + 10, text=label, fill="#ccccdd", font=("", 8))

        if self.select_rect:
            x0, y0, x1, y1 = self.select_rect
            color = "#44ff88" if self.mode == "region_select" else "#ff6644"
            c.create_rectangle(x0, y0, x1, y1, outline=color, dash=(4, 3), width=2)

        if self.mode != "idle":
            c.create_text(w / 2, 16, text=f"MODE: {self.mode.upper()}",
                          fill="#ffaa55", font=("", 11, "bold"))

        c.create_text(12, h - 12, text="X →  Z ↓   (top-down)", fill="#556677",
                      anchor="sw", font=("", 8))


def main(
    root_path: Optional[Path] = None,
    argv: Optional[List[str]] = None,
    context: Optional["ToolContext"] = None,
) -> int:
    if context is not None:
        app = LightLabApp(Path(context.project_root), studio_context=context)
    else:
        parser = argparse.ArgumentParser(description="SignalCloud Illuminosity Light Lab")
        parser.add_argument("root", nargs="?", type=Path)
        args = parser.parse_args(argv if argv is not None else sys.argv[1:])
        candidate = root_path or args.root
        sc_root = candidate.resolve() if candidate is not None and candidate.is_dir() else None
        app = LightLabApp(sc_root)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
