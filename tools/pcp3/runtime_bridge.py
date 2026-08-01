from __future__ import annotations

import copy
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from tools.pcp3.advanced_authoring import capabilities_for, ensure_authoring, sample_clip
from tools.pcp3.io import atomic_write_text, save_project, slugify
from tools.pcp3.model import Layer, PCPDocument, PCPPoint, SEMANTIC_FLAGS

RUNTIME_SCHEMA = "pcp3_runtime_preview_v1"
MAX_OVERLAY_POINTS = 50_000


@dataclass
class RuntimePreviewOptions:
    geometry: bool = True
    rig: bool = True
    anchors: bool = True
    triggers: bool = True
    placements: bool = True
    flow: bool = True
    raid: bool = True
    theme: bool = True
    event_markers: bool = True
    geometry_point_budget: int = 250_000

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _finite(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _vec3(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return default
    return tuple(_finite(value[i], default[i]) for i in range(3))  # type: ignore[return-value]


def _hex_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    text = str(value).strip().lstrip("#")
    if len(text) not in {6, 8}:
        return (0.85, 0.80, 0.58, alpha)
    try:
        r = int(text[0:2], 16) / 255.0
        g = int(text[2:4], 16) / 255.0
        b = int(text[4:6], 16) / 255.0
        a = int(text[6:8], 16) / 255.0 if len(text) == 8 else alpha
        return (r, g, b, a)
    except ValueError:
        return (0.85, 0.80, 0.58, alpha)


def _rotate_xyz(point: tuple[float, float, float], degrees: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    rx, ry, rz = (math.radians(value) for value in degrees)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return x, y, z


def transform_xyz(point: tuple[float, float, float], sample: dict[str, list[float]]) -> tuple[float, float, float]:
    scale = _vec3(sample.get("scale"), (1.0, 1.0, 1.0))
    rotation = _vec3(sample.get("rotation_degrees"))
    position = _vec3(sample.get("position"))
    scaled = (point[0] * scale[0], point[1] * scale[1], point[2] * scale[2])
    rotated = _rotate_xyz(scaled, rotation)
    return rotated[0] + position[0], rotated[1] + position[1], rotated[2] + position[2]


def _point_copy(point: PCPPoint, xyz: tuple[float, float, float], layer_id: int | None = None) -> PCPPoint:
    return PCPPoint(
        xyz[0], xyz[1], xyz[2], point.radius,
        point.r, point.g, point.b, point.a,
        point.nx, point.ny, point.nz, point.density,
        point.layer_id if layer_id is None else layer_id,
        point.flags, point.attribute0, point.attribute1,
    )


def _line(a: tuple[float, float, float], b: tuple[float, float, float], *, spacing: float,
          color: tuple[float, float, float, float], radius: float, layer_id: int, flags: int = 0,
          attribute0: float = 0.0, attribute1: float = 0.0) -> list[PCPPoint]:
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    count = max(2, min(2048, int(math.ceil(length / max(0.02, spacing))) + 1))
    return [
        PCPPoint(
            a[0] + dx * (i / (count - 1)),
            a[1] + dy * (i / (count - 1)),
            a[2] + dz * (i / (count - 1)),
            radius, color[0], color[1], color[2], color[3],
            0.0, 1.0, 0.0, 1.0, layer_id, flags, attribute0, attribute1,
        )
        for i in range(count)
    ]


def _cross(center: tuple[float, float, float], size: float, *, color: tuple[float, float, float, float],
           layer_id: int, flags: int, radius: float = 2.5) -> list[PCPPoint]:
    points: list[PCPPoint] = []
    for axis in range(3):
        low = list(center); high = list(center)
        low[axis] -= size; high[axis] += size
        points.extend(_line(tuple(low), tuple(high), spacing=max(0.05, size / 8.0), color=color,
                            radius=radius, layer_id=layer_id, flags=flags))
    return points


def _box(center: tuple[float, float, float], size: float, *, color: tuple[float, float, float, float],
         layer_id: int, flags: int) -> list[PCPPoint]:
    half = max(0.1, size) * 0.5
    corners = [(center[0] + sx * half, center[1] + sy * half, center[2] + sz * half)
               for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    edges: list[tuple[int, int]] = []
    for i, a in enumerate(corners):
        for j in range(i + 1, len(corners)):
            b = corners[j]
            diff = sum(1 for axis in range(3) if abs(a[axis] - b[axis]) > 1e-6)
            if diff == 1:
                edges.append((i, j))
    points: list[PCPPoint] = []
    for i, j in edges:
        points.extend(_line(corners[i], corners[j], spacing=max(0.06, size / 12.0), color=color,
                            radius=2.2, layer_id=layer_id, flags=flags))
    return points


def _ring(center: tuple[float, float, float], radius_value: float, axis: int, *,
          color: tuple[float, float, float, float], layer_id: int, flags: int) -> list[PCPPoint]:
    count = max(16, min(512, int(radius_value * 24.0)))
    points: list[PCPPoint] = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        position = [center[0], center[1], center[2]]
        first = (axis + 1) % 3
        second = (axis + 2) % 3
        position[first] += math.cos(angle) * radius_value
        position[second] += math.sin(angle) * radius_value
        points.append(PCPPoint(*position, 2.0, *color, 0.0, 1.0, 0.0, 1.0, layer_id, flags))
    return points


def clip_by_name(authoring: dict[str, Any], clip_name: str) -> dict[str, Any]:
    clips = [clip for clip in authoring.get("timelines", []) if isinstance(clip, dict)]
    for clip in clips:
        if str(clip.get("name", "")) == clip_name:
            return clip
    return clips[0] if clips else {"name": "Default", "duration": 1.0, "loop": True, "keyframes": [], "events": []}


def events_crossed(clip: dict[str, Any], previous: float, current: float, looped: bool = False) -> list[dict[str, Any]]:
    events = [event for event in clip.get("events", []) if isinstance(event, dict)]
    if looped:
        duration = max(0.0001, _finite(clip.get("duration"), 1.0))
        return [event for event in events if _finite(event.get("time")) > previous or _finite(event.get("time")) <= current % duration]
    low, high = sorted((previous, current))
    return [event for event in events if low < _finite(event.get("time")) <= high]


def _add_layer(document: PCPDocument, name: str, semantic: str, group: str = "Runtime Preview") -> Layer:
    next_id = max((layer.id for layer in document.layers), default=0) + 1
    layer = Layer(next_id, name, group=group, semantic=semantic, locked=True,
                  future_attributes={"pcp3_runtime_preview": True})
    document.layers.append(layer)
    return layer


def _apply_theme(document: PCPDocument, slots: list[dict[str, Any]]) -> None:
    by_semantic = {str(slot.get("semantic", "")): _hex_rgba(str(slot.get("color", ""))) for slot in slots if isinstance(slot, dict)}
    layer_semantic = {layer.id: layer.semantic for layer in document.layers}
    inverse_flags = {value: key for key, value in SEMANTIC_FLAGS.items()}
    for point in document.points:
        semantic = layer_semantic.get(point.layer_id, inverse_flags.get(point.flags, "generic"))
        if semantic in by_semantic:
            point.r, point.g, point.b, point.a = by_semantic[semantic]


def compile_preview_document(document: PCPDocument, clip_name: str, time_value: float,
                             options: RuntimePreviewOptions | None = None) -> PCPDocument:
    options = options or RuntimePreviewOptions()
    authoring = ensure_authoring(document)
    clip = clip_by_name(authoring, clip_name)
    sample = sample_clip(clip, time_value, target="root")
    preview = copy.deepcopy(document)
    preview.project_id = f"runtime-preview-{document.project_id}"
    preview.asset_id = f"{slugify(document.asset_id)}_runtime_preview"
    preview.display_name = f"{document.display_name} — Runtime Preview"
    preview.selected_indices.clear()
    preview.metadata["runtime_preview"] = {
        "schema": RUNTIME_SCHEMA,
        "source_project_id": document.project_id,
        "source_asset_id": document.asset_id,
        "clip": str(clip.get("name", clip_name)),
        "time": float(time_value),
        "sample": sample,
        "options": options.to_json(),
        "non_destructive": True,
    }
    if options.geometry:
        budget = max(1_000, min(1_000_000, int(options.geometry_point_budget)))
        visible_layers = {layer.id: layer for layer in document.layers if layer.visible}
        eligible = [point for point in document.points if point.layer_id in visible_layers]
        if len(eligible) <= budget:
            source_points = eligible
        else:
            stride = max(1, int(math.ceil(len(eligible) / budget)))
            source_points = eligible[::stride][:budget]
        preview.points = []
        for point in source_points:
            copied = _point_copy(point, transform_xyz((point.x, point.y, point.z), sample))
            copied.a *= max(0.0, min(1.0, visible_layers[point.layer_id].opacity))
            preview.points.append(copied)
        preview.metadata["runtime_preview"]["source_point_count"] = len(document.points)
        preview.metadata["runtime_preview"]["visible_source_point_count"] = len(eligible)
        preview.metadata["runtime_preview"]["preview_geometry_count"] = len(preview.points)
        preview.metadata["runtime_preview"]["geometry_sampled"] = len(preview.points) < len(document.points)
    else:
        preview.points = []
    if options.theme:
        _apply_theme(preview, [slot for slot in authoring.get("theme", {}).get("slots", []) if isinstance(slot, dict)])

    overlay_count = 0
    def add(points: Iterable[PCPPoint]) -> None:
        nonlocal overlay_count
        if overlay_count >= MAX_OVERLAY_POINTS:
            return
        for point in points:
            if overlay_count >= MAX_OVERLAY_POINTS:
                break
            preview.points.append(point)
            overlay_count += 1

    if options.rig:
        layer = _add_layer(preview, "Runtime Rig", "bone")
        for bone in authoring.get("rig", {}).get("bones", []):
            if not isinstance(bone, dict):
                continue
            start = transform_xyz(_vec3(bone.get("start")), sample)
            end = transform_xyz(_vec3(bone.get("end"), (0.0, 1.0, 0.0)), sample)
            add(_line(start, end, spacing=0.08, color=(0.25, 0.85, 1.0, 1.0), radius=2.6,
                      layer_id=layer.id, flags=SEMANTIC_FLAGS["bone"], attribute0=1.0))
    if options.anchors:
        layer = _add_layer(preview, "Runtime Anchors", "trigger")
        for anchor in authoring.get("rig", {}).get("anchors", []):
            if not isinstance(anchor, dict):
                continue
            position = transform_xyz(_vec3(anchor.get("position")), sample)
            add(_cross(position, 0.22, color=(1.0, 0.45, 0.2, 1.0), layer_id=layer.id,
                       flags=SEMANTIC_FLAGS["trigger"], radius=2.5))
    if options.triggers:
        layer = _add_layer(preview, "Runtime Triggers", "trigger")
        for trigger in authoring.get("triggers", []):
            if not isinstance(trigger, dict):
                continue
            position = transform_xyz(_vec3(trigger.get("position")), sample)
            radius_value = max(0.1, min(100.0, _finite(trigger.get("radius"), 1.0)))
            for axis in range(3):
                add(_ring(position, radius_value, axis, color=(1.0, 0.2, 0.55, 0.45), layer_id=layer.id,
                          flags=SEMANTIC_FLAGS["trigger"]))
    if options.placements:
        layer = _add_layer(preview, "Runtime Placements", "generic")
        for placement in authoring.get("placements", []):
            if not isinstance(placement, dict) or not bool(placement.get("enabled", True)):
                continue
            position = transform_xyz(_vec3(placement.get("position")), sample)
            size = max(0.2, min(12.0, _finite(placement.get("scale"), 1.0)))
            add(_box(position, size, color=(0.45, 1.0, 0.45, 0.8), layer_id=layer.id, flags=0))
    if options.flow:
        layer = _add_layer(preview, "Runtime Flow", "liquid_flow")
        for node in authoring.get("flow", {}).get("nodes", []):
            if not isinstance(node, dict):
                continue
            start = transform_xyz(_vec3(node.get("position")), sample)
            direction = _vec3(node.get("direction"), (1.0, 0.0, 0.0))
            strength = max(0.1, min(20.0, _finite(node.get("strength"), 1.0)))
            end_local = (start[0] + direction[0] * strength, start[1] + direction[1] * strength, start[2] + direction[2] * strength)
            add(_line(start, end_local, spacing=0.08, color=(0.2, 0.65, 1.0, 0.9), radius=2.2,
                      layer_id=layer.id, flags=SEMANTIC_FLAGS["liquid_flow"], attribute0=strength,
                      attribute1=_finite(node.get("viscosity"), 1.0)))
            add(_cross(end_local, 0.14, color=(0.2, 0.65, 1.0, 0.9), layer_id=layer.id,
                       flags=SEMANTIC_FLAGS["liquid_flow"], radius=2.0))
    if options.raid:
        waves = [wave for wave in authoring.get("raid", {}).get("waves", []) if isinstance(wave, dict)]
        if waves:
            layer = _add_layer(preview, "Runtime Raid Waves", "trigger")
            for wave_index, wave in enumerate(waves):
                count = max(1, min(24, int(wave.get("count", 1))))
                radius_value = 1.5 + wave_index * 0.8
                for entity_index in range(count):
                    angle = 2.0 * math.pi * entity_index / count
                    center = transform_xyz((math.cos(angle) * radius_value, 0.2 + wave_index * 0.1, math.sin(angle) * radius_value), sample)
                    add(_cross(center, 0.16, color=(1.0, 0.75, 0.15, 0.85), layer_id=layer.id,
                               flags=SEMANTIC_FLAGS["trigger"], radius=2.0))
    if options.event_markers:
        layer = _add_layer(preview, "Runtime Event Marker", "trigger")
        duration = max(0.001, _finite(clip.get("duration"), 1.0))
        phase = (time_value % duration) / duration
        center = transform_xyz((0.0, 0.2 + phase * 0.8, 0.0), sample)
        add(_ring(center, 0.22 + phase * 0.2, 1, color=(1.0, 1.0, 0.25, 0.8), layer_id=layer.id,
                  flags=SEMANTIC_FLAGS["trigger"]))

    preview.runtime = dict(document.runtime)
    preview.runtime.update({"enabled": False, "auto_preview_in_game": False, "stress_spawn_policy": "runtime_preview_only"})
    preview.dirty = True
    return preview


def runtime_summary(document: PCPDocument, clip_name: str = "Default") -> dict[str, Any]:
    authoring = ensure_authoring(document)
    clip = clip_by_name(authoring, clip_name)
    return {
        "clip": str(clip.get("name", clip_name)),
        "duration": _finite(clip.get("duration"), 1.0),
        "loop": bool(clip.get("loop", True)),
        "keyframes": len([item for item in clip.get("keyframes", []) if isinstance(item, dict)]),
        "events": len([item for item in clip.get("events", []) if isinstance(item, dict)]),
        "bones": len([item for item in authoring.get("rig", {}).get("bones", []) if isinstance(item, dict)]),
        "anchors": len([item for item in authoring.get("rig", {}).get("anchors", []) if isinstance(item, dict)]),
        "triggers": len([item for item in authoring.get("triggers", []) if isinstance(item, dict)]),
        "placements": len([item for item in authoring.get("placements", []) if isinstance(item, dict)]),
        "flow_nodes": len([item for item in authoring.get("flow", {}).get("nodes", []) if isinstance(item, dict)]),
        "raid_waves": len([item for item in authoring.get("raid", {}).get("waves", []) if isinstance(item, dict)]),
        "theme_slots": len([item for item in authoring.get("theme", {}).get("slots", []) if isinstance(item, dict)]),
    }


def write_runtime_report(path: Path, document: PCPDocument, clip_name: str,
                         options: RuntimePreviewOptions | None = None) -> Path:
    options = options or RuntimePreviewOptions()
    authoring = ensure_authoring(document)
    clip = clip_by_name(authoring, clip_name)
    payload = {
        "schema": RUNTIME_SCHEMA,
        "asset_id": document.asset_id,
        "environment_type": document.environment_type,
        "selected_clip": str(clip.get("name", clip_name)),
        "summary": runtime_summary(document, clip_name),
        "options": options.to_json(),
        "support": {
            "root_transform_playback": "preview_runtime",
            "rig_and_anchor_overlays": "preview_runtime",
            "timeline_event_dispatch": "preview_log_only",
            "trigger_volumes": "preview_runtime",
            "asset_placements": "preview_proxy_until_nested_asset_factory",
            "raid_waves": "preview_proxy_until_raid_factory",
            "flow_fields": "preview_runtime_visualization",
            "theme_slots": "preview_color_application",
            "game_runtime_execution": "deferred_until_explicit_pce_factories",
        },
        "capabilities": list(capabilities_for(document.environment_type)),
        "policy": "safe_non_destructive_preview_preserve_unknown",
        "data": authoring,
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def write_runtime_preview_bundle(root: Path, document: PCPDocument, clip_name: str, time_value: float,
                                 options: RuntimePreviewOptions | None = None) -> dict[str, Path]:
    preview = compile_preview_document(document, clip_name, time_value, options)
    folder = root / "user_data" / "pcp3" / "runtime_preview" / slugify(document.asset_id)
    folder.mkdir(parents=True, exist_ok=True)
    project = folder / "runtime_preview.pcp3"
    paths = save_project(preview, project, editor_name="PCP3 Runtime Preview")
    report = folder / "runtime_preview.pcp3runtime.json"
    write_runtime_report(report, document, clip_name, options)
    paths["runtime"] = report
    return paths
