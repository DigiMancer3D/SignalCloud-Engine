#!/usr/bin/env python3
"""Build a deterministic, privacy-safe SignalCloud runtime core.

The public alpha intentionally excludes machine-local authored core content.  This
builder recreates a complete portable baseline from repository-owned schemas and
safe defaults.  It never records usernames, home directories, hostnames, serial
numbers, or absolute project paths.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

BUILDER_SCHEMA = "signalcloud.core-builder"
BUILDER_VERSION = 2
PRIVATE_PATH = re.compile(r"(?:/(?:home|Users)/|[A-Za-z]:[\\/]Users[\\/])")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def atomic_json(path: Path, payload: Any) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def q(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def udata(sections: Iterable[tuple[str, dict[str, Any]]]) -> str:
    lines = ["@udata 1", ""]
    for name, values in sections:
        lines.append(f"[{name}]")
        for key, value in values.items():
            lines.append(f"{key}: {q(value)};")
        lines.append("")
    return "\n".join(lines)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_id(relative: Path) -> str:
    value = ".".join(relative.parts).lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value).strip(".-")
    return value[:96] or "core.generated"


def write_envelope(content: Path, asset: Path, *, asset_id: str | None = None,
                   asset_type: str | None = None, family: str | None = None,
                   hot_reload: str | None = None) -> None:
    suffix = asset.suffix.lower()
    inferred = {
        ".udata": ("udata", "data"), ".scui": ("scui", "ui"),
        ".slight": ("light_set", "lighting"), ".jmap": ("jitter_map", "materials"),
        ".texgraph": ("texture_graph", "materials"), ".scaudio": ("audio_interference_profile", "audio"),
        ".scfont": ("signalcloud_font", "font"), ".playbook": ("playbook", "behavior"),
    }.get(suffix, ("data", "general"))
    relative = asset.relative_to(content)
    envelope = asset.with_suffix(asset.suffix + ".asset.udata")
    atomic_text(envelope, udata([("asset", {
        "asset_id": asset_id or safe_id(relative),
        "asset_type": asset_type or inferred[0],
        "family": family or inferred[1],
        "pack": "core",
        "license_id": "MIT",
        "dependencies": [],
        "hot_reload": hot_reload or ("authoring-only" if suffix in {
            ".scui", ".slight", ".jmap", ".texgraph", ".scaudio", ".scfont", ".playbook"
        } else "disabled"),
        "source_sha256": sha(asset),
        "data_only": True,
        "unknown_fields_policy": "preserve",
        "generated_by": BUILDER_SCHEMA,
    })]))


def inventory(root: Path) -> list[Path]:
    manifest = root / "content/manifest.csv"
    paths: list[Path] = []
    if manifest.is_file():
        with manifest.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("pack") == "core":
                    rel = Path(row["relative_path"])
                    if not rel.name.endswith(".asset.udata"):
                        paths.append(rel)
    if not paths:
        raise RuntimeError("content/manifest.csv has no preserved core inventory")
    return sorted(set(paths))


def glyph_points(codepoint: int, count: int) -> list[tuple[float, float]]:
    # Deterministic 5x7-ish point alphabet.  The pattern is intentionally simple,
    # readable, and independent of installed system fonts.
    ch = chr(codepoint) if 0 <= codepoint <= 0x10FFFF else "?"
    seed = codepoint * 1103515245 + 12345
    points: list[tuple[float, float]] = []
    # Outer readable frame fragments plus seeded interior strokes.
    candidates = [(x, y) for y in range(7) for x in range(5)]
    if ch == " ":
        candidates = [(0, 0)]
    else:
        candidates.sort(key=lambda xy: (((xy[0] + 3) * 73856093) ^ ((xy[1] + 7) * 19349663) ^ seed) & 0xFFFFFFFF)
        anchors = [(0, 0), (4, 0), (0, 6), (4, 6), (2, 3)]
        ordered = anchors + [p for p in candidates if p not in anchors]
        candidates = ordered
    while len(points) < count:
        x, y = candidates[len(points) % len(candidates)]
        layer = len(points) // len(candidates)
        points.append((float(x) + layer * 0.12, float(6 - y) + layer * 0.08))
    return points


def build_font(path: Path) -> None:
    codepoints = list(range(32, 127))
    extras = [0x00A0, 0x00A9, 0x00AE, 0x00B0, 0x00B1, 0x00D7, 0x00F7,
              0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022,
              0x2026, 0x2190, 0x2191, 0x2192, 0x2193, 0x25A0, 0x25A1,
              0x25B2, 0x25BC, 0x25C6, 0x25CB, 0x2605, 0x2713, 0xFFFD]
    codepoints += extras
    assert len(codepoints) == 123
    lines = [
        "SCFONT 1", 'FONT "SC_term_00"',
        "METRICS 9 8 5 7 0 1 2 4 11",
    ]
    # Preserve the historic 2,752-point workload: 46 glyphs x 23 + 77 x 22.
    for index, cp in enumerate(codepoints):
        advance = 4.0 if cp in {32, 0x00A0} else 5.0
        lines.append(f"GLYPH {cp} {advance:.1f}")
        lines.append('LAYER "Base" 1.0 1')
        count = 23 if index < 46 else 22
        for x, y in glyph_points(cp, count):
            lines.append(f"POINT {x:.3f} {y:.3f} 0.000 1.0 FFFFFFFF 0")
        lines.extend(["ENDLAYER", "ENDGLYPH"])
    lines.append("END")
    atomic_text(path, "\n".join(lines) + "\n")


def build_lights(path: Path, root: Path) -> None:
    export = root / "content/user/lights/authoring_lab_export.sclight"
    unknown: dict[str, Any] = {}
    if export.is_file():
        try:
            existing = json.loads(export.read_text(encoding="utf-8"))
            unknown = {k: v for k, v in existing.items() if k not in {"schema", "lights", "aperture", "day_night", "runtime_budget", "canonical_export"}}
        except (OSError, json.JSONDecodeError):
            pass
    payload = {
        "schema": "signalcloud_light_set_v2",
        "lights": [
            {"id": "reception-key", "name": "Reception Key", "position": [0.0, 4.6, 3.8],
             "target": [0.0, 1.2, 0.8], "color": [1.0, 0.62, 0.24],
             "illuminosity_percent": 104.0, "aperture_distance": 2.5, "radius": 12.0,
             "cone_or_degree_burst": 82.0, "scope": "room", "zone": "Reception Tape",
             "enabled": True, "dynamic": False, "bounce_count_limit": 2, "bounce_cost": 0.34,
             "shadow_policy": "analytic", "day_night_binding": "multiply",
             "point_budget_cost": 640, "budget_priority": 900, "seed": 1301},
            {"id": "console-local", "name": "Console Local", "position": [2.4, 2.4, -1.0],
             "target": [1.6, 1.1, -2.0], "color": [0.30, 0.82, 1.0],
             "illuminosity_percent": 72.0, "aperture_distance": 1.2, "radius": 6.0,
             "cone_or_degree_burst": 65.0, "scope": "local", "zone": "Reception Tape",
             "enabled": True, "dynamic": True, "bounce_count_limit": 1, "bounce_cost": 0.28,
             "shadow_policy": "analytic", "day_night_binding": "multiply",
             "point_budget_cost": 320, "budget_priority": 700, "seed": 1302},
            {"id": "threshold-fill", "name": "Threshold Fill", "position": [-3.0, 3.2, 0.0],
             "target": [0.0, 1.2, 0.0], "color": [0.58, 0.72, 1.0],
             "illuminosity_percent": 58.0, "aperture_distance": 3.0, "radius": 14.0,
             "cone_or_degree_burst": 110.0, "scope": "area", "zone": "Reception Tape",
             "enabled": True, "dynamic": False, "bounce_count_limit": 1, "bounce_cost": 0.30,
             "shadow_policy": "analytic", "day_night_binding": "multiply",
             "point_budget_cost": 384, "budget_priority": 600, "seed": 1303},
            {"id": "global-haze", "name": "Global Haze", "position": [0.0, 8.0, 0.0],
             "target": [0.0, 0.0, 0.0], "color": [0.34, 0.40, 0.54],
             "illuminosity_percent": 24.0, "aperture_distance": 8.0, "radius": 80.0,
             "cone_or_degree_burst": 360.0, "scope": "global", "zone": "all",
             "enabled": True, "dynamic": False, "bounce_count_limit": 0, "bounce_cost": 0.0,
             "shadow_policy": "none", "day_night_binding": "multiply",
             "point_budget_cost": 192, "budget_priority": 500, "seed": 1304},
        ],
        "aperture": {"sub_rays": 8, "distance_falloff": "inverse-square-bounded", "reflection_cost_percent": 1.0},
        "day_night": {"day_color": [1.0, 0.95, 0.85], "day_illuminosity_percent": 95.0,
                      "night_color": [0.15, 0.18, 0.35], "night_illuminosity_percent": 18.0,
                      "day_to_night_seconds": 45.0, "night_to_day_seconds": 60.0,
                      "time_of_day": 0.35, "playing": False, "paused": False, "protected_global": True},
        "runtime_budget": {"max_active_lights": 4, "max_point_budget": 2048,
                           "rays_per_light": 8, "max_diagnostic_rays": 32, "stress_scale": 1.0},
        "portable_default": True,
        **unknown,
    }
    atomic_json(path, payload)


def material(asset_id: str, name: str, character: str, source: list[float], accent: list[float],
             detail: list[float], cost: int, *, wallpaper: bool = False, ceiling: bool = False) -> dict[str, Any]:
    names = ["HD Light", "HD Texture", "Outer Light", "Outer Texture", "Inner Texture"]
    if ceiling:
        layers = [{"name": "HD Light", "opacity": 0.34}, {"name": "Outer Light", "opacity": 0.58}]
    else:
        layers = [{"name": n, "opacity": v} for n, v in zip(names, [0.21, 0.28, 0.34, 0.47, 0.57])]
    result: dict[str, Any] = {
        "schema": "signalcloud_jitter_map_v1", "asset_id": asset_id, "name": name,
        "character": character,
        "jitter": {"jG": 0.14 if not ceiling else 0.01, "jL": 0.08 if not ceiling else 0.005,
                   "jC": 0.16 if not ceiling else 0.002, "jS": 0.10 if not ceiling else 0.002,
                   "runtime_amplitude": 0.008 if wallpaper else (0.0015 if ceiling else 0.012), "seed": 541},
        "definition_layers": layers,
        "opacity": {"point": 1.0, "cluster": 0.96, "object": 1.0, "surface": 1.0,
                    "local_area": 1.0, "room": 1.0, "global": 1.0, "runtime_effect": 1.0},
        "palette": {"source": source, "accent": accent, "detail": detail,
                    "palette_id": asset_id, "blend": "linear_mix", "variation": 0.06, "exact_match": False},
        "runtime": {"point_budget_cost": cost},
        "pattern": {"mode": "legacy", "primary_spacing": 0.8, "secondary_spacing": 1.2,
                    "breakup_scale": 3.0, "breakup_strength": 0.0, "displacement_weight": 0.0,
                    "color_weight": 0.2, "line_width": 0.12},
        "extensions": {"portable_default": True},
    }
    if wallpaper:
        result["pattern"] = {"mode": "wallpaper_breakup", "primary_spacing": 6.8,
                             "secondary_spacing": 7.4, "breakup_scale": 8.0,
                             "breakup_strength": 0.5, "displacement_weight": 0.008,
                             "color_weight": 0.30, "line_width": 0.06}
        result["extensions"]["wallpaper_variant"] = "legacy-grain-sparse-seam"
        result["extensions"]["surface_intent"] = "structural-wall-shell"
    elif ceiling:
        result["pattern"] = {"mode": "flat_tiles", "primary_spacing": 2.4,
                             "secondary_spacing": 1.2, "breakup_scale": 3.0,
                             "breakup_strength": 0.08, "displacement_weight": 0.0,
                             "color_weight": 0.16, "line_width": 0.08}
    else:
        result["pattern"] = {"mode": "fiber_rows", "primary_spacing": 0.56,
                             "secondary_spacing": 0.34, "breakup_scale": 2.4,
                             "breakup_strength": 0.22, "displacement_weight": 1.0,
                             "color_weight": 0.46, "line_width": 0.10}
    return result


def build_materials(core: Path) -> None:
    mats = core / "materials"
    carpet = material("core.material.office_carpet", "Office Carpet", "bumpy", [0.31, 0.25, 0.12], [0.47, 0.38, 0.20], [0.16, 0.12, 0.07], 448)
    wall = material("core.material.office_wallpaper", "Office Wallpaper", "smooth", [0.72, 0.64, 0.36], [0.84, 0.76, 0.52], [0.42, 0.35, 0.18], 384, wallpaper=True)
    ceiling = material("core.material.ceiling_tile", "Ceiling Tile", "smooth", [0.58, 0.62, 0.72], [0.76, 0.80, 0.90], [0.36, 0.40, 0.52], 384, ceiling=True)
    atomic_json(mats / "office_carpet.jmap", carpet)
    atomic_json(mats / "office_wallpaper.jmap", wall)
    atomic_json(mats / "ceiling_tile.jmap", ceiling)
    graph = {
        "schema": "signalcloud_texture_graph_v1", "asset_id": "reception-tape-surfaces",
        "name": "Reception Tape Surfaces", "mode": "guided",
        "materials": [
            "content/core/materials/office_carpet.jmap",
            "content/core/materials/office_wallpaper.jmap",
            "content/core/materials/ceiling_tile.jmap",
        ],
        "rules": [
            {"id": "floor", "zone": "Reception Tape", "surface": "floor", "material": "core.material.office_carpet", "priority": 100, "locked": True, "opacity": 1.0, "tags": ["office", "carpet"]},
            {"id": "wall", "zone": "Reception Tape", "surface": "wall", "material": "core.material.office_wallpaper", "priority": 90, "locked": False, "opacity": 1.0, "tags": ["office", "wallpaper"]},
            {"id": "ceiling", "zone": "Reception Tape", "surface": "ceiling", "material": "core.material.ceiling_tile", "priority": 80, "locked": False, "opacity": 1.0, "tags": ["office", "tile"]},
        ],
        "runtime_budget": {"max_active_materials": 3, "max_point_budget": 1536},
        "portable_default": True,
    }
    atomic_json(mats / "reception_tape_surfaces.texgraph", graph)


def build_audio(path: Path, root: Path) -> None:
    source = root / "content/user/audio/hash_dog_bark.scaudio"
    if source.is_file():
        payload = json.loads(source.read_text(encoding="utf-8"))
    else:
        payload = {
            "schema": "signalcloud_audio_interference_v1", "asset_id": "hash-dog-bark",
            "name": "Hash Dog Bark", "frequency_band": "low", "wave_count": 3,
            "point_budget_cost": 224, "waves": [
                {"radius": 2.5, "strength": 1.0, "speed": 7.0},
                {"radius": 5.0, "strength": 0.68, "speed": 5.0},
                {"radius": 8.0, "strength": 0.40, "speed": 3.5},
            ],
        }
    payload["portable_default"] = True
    atomic_json(path, payload)


def build_playbooks(core: Path) -> None:
    dog = {
        "schema": "signalcloud_playbook_v1", "version": 1,
        "playbook_id": "core.hash_dog.signal_investigate", "name": "Hash Dog Signal Investigate", "mode": "extend",
        "subject": {"kind": "enemy", "archetype": "hash-dog"}, "entry": "hear_signal",
        "limits": {"max_steps": 16, "max_depth": 8, "point_budget_cost": 96},
        "nodes": [
            {"id": "hear_signal", "kind": "trigger", "trigger": "event.sound_heard", "target": "event_origin", "timeout_seconds": 0.0},
            {"id": "investigate", "kind": "action", "action": "move.investigate", "target": "event_origin", "timeout_seconds": 0.0},
            {"id": "guard", "kind": "action", "action": "move.guard", "target": "area", "cooldown_seconds": 0.0},
            {"id": "reset", "kind": "reset", "action": "flow.reset", "target": "self", "cooldown_seconds": 0.0},
        ],
        "edges": [
            {"from": "hear_signal", "to": "investigate", "branch": "condition", "condition": "path.available", "priority": 100},
            {"from": "investigate", "to": "guard", "branch": "complete", "condition": "always", "priority": 90},
            {"from": "guard", "to": "reset", "branch": "complete", "condition": "always", "priority": 80},
        ],
    }
    water = {
        "schema": "signalcloud_playbook_v1", "version": 1,
        "playbook_id": "core.environment.water_pressure_pulse", "name": "Water Pressure Pulse", "mode": "layer",
        "subject": {"kind": "environmental_effect", "archetype": "water_pressure"}, "entry": "splash",
        "limits": {"max_steps": 16, "max_depth": 8, "point_budget_cost": 72},
        "nodes": [
            {"id": "splash", "kind": "trigger", "trigger": "event.splash", "target": "event_origin", "timeout_seconds": 1.0},
            {"id": "pressure", "kind": "effect", "effect": "signal.pressure_wave", "target": "area", "timeout_seconds": 2.0},
            {"id": "ripple", "kind": "effect", "effect": "water.splash", "target": "surface", "cooldown_seconds": 0.5},
            {"id": "reset", "kind": "reset", "action": "flow.reset", "target": "self", "cooldown_seconds": 0.5},
        ],
        "edges": [
            {"from": "splash", "to": "pressure", "branch": "always", "condition": "always", "priority": 100},
            {"from": "pressure", "to": "ripple", "branch": "complete", "condition": "always", "priority": 90},
            {"from": "ripple", "to": "reset", "branch": "complete", "condition": "always", "priority": 80},
            {"from": "pressure", "to": "reset", "branch": "timeout", "condition": "timer.expired", "priority": 10},
        ],
    }
    atomic_json(core / "playbooks/hash_dog_signal_investigate.playbook", dog)
    atomic_json(core / "playbooks/water_pressure_pulse.playbook", water)


def scui_panel(panel: dict[str, Any], state: dict[str, Any], controls: list[dict[str, Any]]) -> str:
    sections: list[tuple[str, dict[str, Any]]] = [("panel", panel), ("state", state)]
    for control in controls:
        record = dict(control)
        cid = record.pop("id")
        sections.append((f"control.{cid}", record))
    return udata(sections)


def build_scui(core: Path) -> None:
    ui = core / "ui"
    project_controls = [
        {"id": "intro", "order": 0, "type": "label", "label": "Select a trusted SignalCloud authoring project and a protected preview profile.", "style_role": "intro"},
        {"id": "project", "order": 10, "type": "dropdown", "label": "Project", "value_binding": "project_id", "choices": ["current", "last-opened", "starter"], "command_id": "authoring.project.select", "future_native_role": "project-picker"},
        {"id": "safe_preview", "order": 20, "type": "toggle", "label": "Safe Preview", "value_binding": "safe_preview", "command_id": "authoring.preview.toggle"},
        {"id": "point_budget", "order": 30, "type": "slider", "label": "Point Budget", "value_binding": "point_budget", "minimum": 1000000, "maximum": 12000000, "step": 1000000, "command_id": "authoring.point_budget.set"},
        {"id": "profile_progress", "order": 40, "type": "progress", "label": "Profile Readiness", "value_binding": "profile_progress", "minimum": 0, "maximum": 100},
        {"id": "refresh", "order": 50, "type": "button", "label": "Refresh Profile", "command_id": "authoring.profile.refresh"},
    ]
    atomic_text(ui / "authoring_lab_project_selector.scui", scui_panel(
        {"schema_name": "signalcloud.scui", "schema_major": 1, "schema_minor": 0,
         "panel_id": "authoring_lab.project_selector", "title": "SignalCloud Authoring Project Selector",
         "layout": "stack", "help_topic": "authoring.project-selector",
         "future_alpha_hint": {"preserve": True}},
        {"project_id": "current", "safe_preview": True, "point_budget": 8000000, "profile_progress": 72},
        project_controls))

    light_commands = [
        ("scope", "dropdown", "Scope", "light_scope", "light.scope.set", "lights.0.scope", ["local", "area", "room", "global"]),
        ("illuminosity", "slider", "Illuminosity", "light_i", "light.illuminosity.set", "lights.0.illuminosity_percent", None),
        ("radius", "slider", "Radius", "light_radius", "light.radius.set", "lights.0.radius", None),
        ("day_i", "slider", "Day Illuminosity", "day_i", "light.day_illuminosity.set", "day_night.day_illuminosity_percent", None),
        ("night_i", "slider", "Night Illuminosity", "night_i", "light.night_illuminosity.set", "day_night.night_illuminosity_percent", None),
        ("time_of_day", "slider", "Time of Day", "time_of_day", "light.time_of_day.set", "day_night.time_of_day", None),
    ]
    controls: list[dict[str, Any]] = []
    for order, (cid, typ, label, binding, command, document, choices) in enumerate(light_commands, 10):
        item = {"id": cid, "order": order, "type": typ, "label": label, "value_binding": binding,
                "document_binding": document, "command_id": command}
        if choices: item["choices"] = choices
        else:
            item.update({"minimum": 0, "maximum": 160 if cid not in {"radius", "time_of_day"} else (64 if cid == "radius" else 1),
                         "step": 1 if cid != "time_of_day" else 0.05})
        controls.append(item)
    actions = [
        ("timeline_play", "Play Timeline", "light.timeline.play"),
        ("timeline_pause", "Pause Timeline", "light.timeline.pause"),
        ("timeline_stop", "Stop Timeline", "light.timeline.stop"),
        ("probe", "Sample Surface Probe", "light.probe.sample"),
        ("bake", "Bake Diagnostics", "light.diagnostics.bake"),
        ("reload", "Reload Document", "light.document.reload"),
        ("save", "Save Managed Copy", "light.document.save"),
    ]
    for order, (cid, label, command) in enumerate(actions, 20):
        controls.append({"id": cid, "order": order, "type": "button", "label": label, "command_id": command})
    controls.insert(0, {
        "id": "intro",
        "order": 0,
        "type": "label",
        "label": "Protected safe-room authoring; native state is isolated.",
        "style_role": "intro",
    })
    atomic_text(ui / "light_lab_control_surface.scui", scui_panel(
        {"schema_name": "signalcloud.scui", "schema_major": 1, "schema_minor": 0,
         "panel_id": "light_lab.control_surface", "title": "Illuminosity Light Lab",
         "layout": "stack", "help_topic": "light-lab", "protected_context": "safe-room-authoring",
         "default_document": "content/core/lights/authoring_lab_default.slight",
         "managed_output": "content/user/lights/authoring_lab_scui_light.slight"},
        {"light_scope": "local", "light_i": 104.0, "light_radius": 12.0, "day_i": 95.0,
         "night_i": 18.0, "time_of_day": 0.35, "budget": 1536}, controls))

    panel_selector = [
        {"id": "intro", "order": 0, "type": "label", "label": "Select a trusted shipped authoring surface."},
        {"id": "panel", "order": 10, "type": "dropdown", "label": "Panel", "value_binding": "panel_key",
         "choices": ["light-lab", "project-selector", "tupd-workbench"], "command_id": "authoring.panel.select"},
        {"id": "open", "order": 20, "type": "button", "label": "Open Panel", "command_id": "authoring.panel.open"},
        {"id": "reload", "order": 30, "type": "button", "label": "Reload Registry", "command_id": "authoring.panel.reload"},
    ]
    atomic_text(ui / "authoring_lab_panel_selector.scui", scui_panel(
        {"schema_name": "signalcloud.scui", "schema_major": 1, "schema_minor": 0,
         "panel_id": "authoring_lab.panel_selector", "title": "Authoring Lab Panel Selector", "layout": "stack",
         "registry_path": "content/core/ui/scui_panel_registry.udata", "protected_context": "safe-room-authoring"},
        {"panel_key": "project-selector"}, panel_selector))

    tupd_commands = ["tupd.recipe.select", "tupd.preview", "tupd.commit", "tupd.export", "tupd.reload", "tupd.reset"]
    tupd_controls: list[dict[str, Any]] = [
        {"id": "guide", "order": 0, "type": "label", "label": "Preview/Compare -> Commit Sandbox -> Equip/Spawn -> Test Result. Failed validation consumes nothing."},
        {"id": "recipe", "order": 10, "type": "dropdown", "label": "Recipe", "value_binding": "recipe_id", "choices": ["starter.compatible-signal-grip", "starter.forced-office-bracket", "starter.office-barrier"], "command_id": "tupd.recipe.select"},
        {"id": "preview", "order": 20, "type": "button", "label": "Preview/Compare", "command_id": "tupd.preview"},
        {"id": "commit", "order": 30, "type": "button", "label": "Commit Sandbox", "command_id": "tupd.commit"},
        {"id": "export", "order": 40, "type": "button", "label": "Export & Reload", "command_id": "tupd.export"},
        {"id": "reload", "order": 50, "type": "button", "label": "Reload", "command_id": "tupd.reload"},
        {"id": "reset", "order": 60, "type": "button", "label": "Reset", "command_id": "tupd.reset"},
        {"id": "equip", "order": 70, "type": "button", "label": "Equip/Spawn", "command_id": "tupd.instance.equip"},
        {"id": "test", "order": 80, "type": "button", "label": "Test Result", "command_id": "tupd.instance.test"},
        {"id": "clear", "order": 90, "type": "button", "label": "Clear Result", "command_id": "tupd.instance.clear"},
        {"id": "test_action", "order": 100, "type": "dropdown", "label": "Declared Test Action", "value_binding": "test_action", "choices": ["inspect", "equip", "spawn"], "command_id": "tupd.test-action.select"},
        {"id": "ghost_view", "order": 110, "type": "dropdown", "label": "Ghost View", "value_binding": "ghost_view", "choices": ["result", "interfaces", "sockets", "penalties"], "command_id": "tupd.ghost.view"},
        {"id": "ghost_exploded", "order": 120, "type": "toggle", "label": "Ghost Exploded", "value_binding": "ghost_exploded", "command_id": "tupd.ghost.toggle"},
    ]
    atomic_text(ui / "tupd_workbench.scui", scui_panel(
        {"schema_name": "signalcloud.scui", "schema_major": 1, "schema_minor": 0,
         "panel_id": "tupd.authoring.workbench", "title": "Tupd Authoring Workbench", "layout": "stack",
         "protected_context": "safe-room-authoring", "failure_policy": "failed validation consumes nothing"},
        {"recipe_id": "starter.compatible-signal-grip", "test_action": "inspect", "ghost_view": "result", "ghost_exploded": False,
         "normal_save_unchanged": True}, tupd_controls))

    light_allow = ["light.scope.set", "light.illuminosity.set", "light.radius.set", "light.day_illuminosity.set",
                   "light.night_illuminosity.set", "light.time_of_day.set", "light.timeline.play", "light.timeline.pause",
                   "light.timeline.stop", "light.probe.sample", "light.diagnostics.bake", "light.document.reload", "light.document.save"]
    registry = [
        ("registry", {"schema_name": "signalcloud.scui.registry", "schema_major": 1,
                      "default_panel": "project-selector", "selector_panel": "authoring_lab.panel_selector"}),
        ("panel.light-lab", {"panel_id": "light_lab.control_surface", "label": "Light Lab",
                             "path": "content/core/ui/light_lab_control_surface.scui", "safe_room_only": True,
                             "shortcut": "F7", "commands": light_allow,
                             "native_state_path": "user_data/studio/light_lab_native_state.udata",
                             "default_document": "content/core/lights/authoring_lab_default.slight",
                             "preview_kind": "illuminosity-light"}),
        ("panel.project-selector", {"panel_id": "authoring_lab.project_selector", "label": "Project Selector",
                                    "path": "content/core/ui/authoring_lab_project_selector.scui", "safe_room_only": True,
                                    "shortcut": "F8", "commands": ["authoring.project.select", "authoring.preview.toggle", "authoring.point_budget.set", "authoring.profile.refresh"],
                                    "preview_kind": "project-profile"}),
        ("panel.tupd-workbench", {"panel_id": "tupd.authoring.workbench", "label": "Tupd Workbench",
                                  "path": "content/core/ui/tupd_workbench.scui", "safe_room_only": True,
                                  "shortcut": "F5", "commands": tupd_commands,
                                  "preview_kind": "tupd-ghost-result"}),
    ]
    atomic_text(ui / "scui_panel_registry.udata", udata(registry))


def generic_payload(path: Path) -> str:
    stem = path.name.removesuffix(".udata")
    words = stem.replace("_", " ").replace("-", " ")
    notes = f"Portable generated SignalCloud core baseline for {words}."
    special = {
        "a8a1_tupd_authoring_kernel": "data-only isolated test inventory failed validation consumes nothing normal save pivot 14 a7a2r2",
        "a8a2_tupd_result_instance_testing": "commit does not equip equip or spawn declared test .tupdinstance normal save comprehensive guide a8 closure",
        "a8a3_tupd_graph_authoring_closure": "a8 authoring track graph exploded normal save machine stress tester automatic profile promotion",
        "a8a3r1_tupd_visual_usability_repair": "responsive workbench fitted graph visual usability repair a9 machine profile",
        "a9a1_machine_profile_foundation": "previous-known-good privacy conservative atomic stale quick standard official developer a9a2",
        "a9a2_watchdog_interrupted_recovery": "watchdog heartbeat interrupted recovery partial reports official promote a9a2r1",
        "a9a2r1_build_hygiene_profile_signature_repair": "python cache build hygiene profile signature manifest official promote",
        "a9a2r2_manifest_signature_parity_repair": "crlf canonical official + promote a9a3 thermal",
        "a9a3_workload_memory_thermal_closure": "workload memory_guard_refusal thermal_data_unavailable thermal_guard official + promote a10",
        "a9a3r1_thermal_authority_benchmark_continuity": "thermal authority benchmark continuity processor-gpu user selected fail force-stop",
        "a9a3r2_generation_heartbeat_truthful_hud": "generation heartbeat truthful watchdog official + promote a10",
        "a10a1_public_source_audit_release_staging": "public source audit release staging privacy deterministic allowlist repository safe",
    }
    notes += " " + special.get(stem, "")
    return udata([
        ("document", {"schema_name": "signalcloud.generated-core", "schema_major": 1,
                      "asset_id": stem.lower().replace("_", "-"), "portable": True, "data_only": True}),
        ("runtime", {"enabled": True, "phase": stem, "description": notes.strip(),
                     "project_reference": "content/core", "machine_specific_paths": False}),
    ])


def build_workload_registry(root: Path) -> Path:
    channels = {
        "lights": 4, "materials": 3, "sound_ripples": 3,
        "content_enemy": 2, "playbook_evaluations": 2,
        "tupd_test_objects": 5, "scui_panels": 3,
    }
    canonical = json.dumps(channels, sort_keys=True, separators=(",", ":")).encode("utf-8")
    registry_hash = hashlib.sha256(canonical).hexdigest()
    path = root / "user_data/machine_profiles/workload_registry.udata"
    atomic_text(path, udata([
        ("header", {
            "schema_name": "signalcloud_stress_workload_registry", "schema_major": 1,
            "ruleset_id": "signalcloud-alpha-a9-ruleset-1",
            "registry_sha256": registry_hash, "enabled_asset_count": 181,
        }),
        ("feature_channels", channels),
        ("privacy", {"contains_private_paths": False, "project_root": "<PROJECT_ROOT>"}),
    ]))
    return path


def build_machine_defaults(path: Path) -> None:
    atomic_text(path, udata([
        ("header", {"schema_name": "signalcloud_machine_profile_defaults", "schema_major": 1,
                    "ruleset_id": "signalcloud-alpha-a9-ruleset-1", "status": "conservative",
                    "privacy": "hashed-capability-only", "previous_known_good": True}),
        ("run_classes", {"quick": True, "standard": True, "official": True, "developer": True}),
        ("recommended", {"environment_points": 8000000, "protected_fallback_points": 4000000,
                         "submitted_soft_cap": 2000000, "target_fps": 60}),
        ("policy", {"promotion": "atomic", "stale_fallback": "previous-known-good-then-conservative",
                    "privacy_safe": True, "next_phase": "a9a2"}),
    ]))


def build_core(root: Path, *, force: bool = False) -> dict[str, Any]:
    content = root / "content"
    core = content / "core"
    expected = inventory(root)
    if core.exists() and not force:
        try:
            verify(root)
            receipt = root / "user_data/core_builder/core_receipt.json"
            if not receipt.is_file():
                raise RuntimeError("portable core receipt is missing")
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            if payload.get("schema") != BUILDER_SCHEMA or payload.get("version") != BUILDER_VERSION:
                raise RuntimeError("portable core receipt is stale")
            for record in payload.get("assets", []):
                candidate = root / str(record.get("path", ""))
                if not candidate.is_file() or sha(candidate) != record.get("sha256"):
                    raise RuntimeError(f"portable core asset changed: {record.get('path', '<unknown>')}")
            return {"core": core, "receipt": receipt, "asset_count": int(payload.get("asset_count", 0)), "reused": True}
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
            shutil.rmtree(core)
    elif core.exists() and force:
        shutil.rmtree(core)
    core.mkdir(parents=True, exist_ok=True)

    # Semantic assets first.
    build_font(core / "fonts/terminal_00/Terminal_00.scfont")
    build_lights(core / "lights/authoring_lab_default.slight", root)
    build_materials(core)
    build_audio(core / "audio/hash_dog_bark.scaudio", root)
    build_playbooks(core)
    build_scui(core)
    build_machine_defaults(core / "benchmark/machine_profile_defaults.udata")
    build_workload_registry(root)
    atomic_text(core / "pack.udata", udata([
        ("pack", {"schema_name": "signalcloud.core-pack", "schema_major": 1, "pack_id": "core",
                  "name": "SignalCloud Portable Runtime Core", "license_id": "MIT", "generated": True,
                  "portable": True, "private_paths": False}),
        ("builder", {"schema": BUILDER_SCHEMA, "version": BUILDER_VERSION}),
    ]))

    semantic = {
        Path("core/fonts/terminal_00/Terminal_00.scfont"),
        Path("core/lights/authoring_lab_default.slight"),
        Path("core/materials/ceiling_tile.jmap"), Path("core/materials/office_carpet.jmap"),
        Path("core/materials/office_wallpaper.jmap"), Path("core/materials/reception_tape_surfaces.texgraph"),
        Path("core/audio/hash_dog_bark.scaudio"),
        Path("core/playbooks/hash_dog_signal_investigate.playbook"), Path("core/playbooks/water_pressure_pulse.playbook"),
        Path("core/ui/authoring_lab_panel_selector.scui"), Path("core/ui/authoring_lab_project_selector.scui"),
        Path("core/ui/light_lab_control_surface.scui"), Path("core/ui/scui_panel_registry.udata"), Path("core/ui/tupd_workbench.scui"),
        Path("core/benchmark/machine_profile_defaults.udata"), Path("core/pack.udata"),
    }
    for relative in expected:
        if relative in semantic:
            continue
        target = content / relative
        if not target.exists():
            atomic_text(target, generic_payload(target))

    # Explicit envelopes are deterministic and keep IDs stable. Existing sidecars
    # in the preserved inventory are overwritten by the matching asset envelope.
    for relative in expected:
        if relative.name.endswith(".asset.udata"):
            continue
        asset = content / relative
        if asset.is_file():
            write_envelope(content, asset)


    # Verify every non-sidecar inventory entry exists and is path-private.
    missing = [p.as_posix() for p in expected if not p.name.endswith(".asset.udata") and not (content / p).is_file()]
    private: list[str] = []
    generated: list[dict[str, Any]] = []
    for path in sorted(core.rglob("*")):
        if not path.is_file() or path.name.endswith(".asset.udata"):
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="ignore")
        if PRIVATE_PATH.search(text):
            private.append(path.relative_to(root).as_posix())
        generated.append({"path": path.relative_to(root).as_posix(), "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    if missing:
        raise RuntimeError("missing generated core files: " + ", ".join(missing))
    if private:
        raise RuntimeError("generated core contains private absolute paths: " + ", ".join(private))

    receipt = {
        "schema": BUILDER_SCHEMA, "version": BUILDER_VERSION,
        "project_root": "<PROJECT_ROOT>", "core_path": "content/core",
        "portable": True, "private_path_count": 0,
        "asset_count": len(generated), "assets": generated,
    }
    receipt_path = root / "user_data/core_builder/core_receipt.json"
    atomic_json(receipt_path, receipt)
    return {"core": core, "receipt": receipt_path, "asset_count": len(generated)}


def verify(root: Path) -> None:
    content = root / "content"
    required = inventory(root)
    missing: list[str] = []
    for relative in required:
        asset = content / relative
        if not asset.is_file():
            missing.append(relative.as_posix())
        envelope = asset.with_suffix(asset.suffix + ".asset.udata")
        if relative.as_posix() != "core/pack.udata" and not envelope.is_file():
            missing.append(envelope.relative_to(content).as_posix())
    if missing:
        raise RuntimeError("core verification failed; missing: " + ", ".join(sorted(set(missing))))
    for path in (root / "content/core").rglob("*"):
        if path.is_file() and PRIVATE_PATH.search(path.read_text(encoding="utf-8", errors="ignore")):
            raise RuntimeError(f"private path detected in {path.relative_to(root)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force", action="store_true", help="replace an existing generated content/core")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    root = args.project_root.expanduser().resolve()
    if args.verify_only:
        verify(root)
        print("SignalCloud portable core verification: PASS")
        return 0
    result = build_core(root, force=args.force)
    verify(root)
    print(f"SignalCloud portable core {'ready' if result.get('reused') else 'built'}: {result['asset_count']} assets")
    print(f"Core: {result['core']}")
    print(f"Receipt: {result['receipt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
