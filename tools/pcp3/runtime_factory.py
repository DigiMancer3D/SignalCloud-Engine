from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tools.pcp3.advanced_authoring import ensure_authoring
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.model import PCPDocument

FACTORY_SCHEMA = "pcp3_runtime_factory_v1"
ALLOWED_TRIGGER_TYPES = {"proximity", "scanner", "threshold", "timer", "interaction"}
ALLOWED_ACTIONS = {"none", "show", "hide", "alert", "reveal", "spawn_proxy", "set_theme", "pulse_light"}
MAX_KEYFRAMES = 64
MAX_PLACEMENTS = 64
MAX_TRIGGERS = 64
MAX_FLOW_NODES = 64
MAX_THEME_SLOTS = 64


@dataclass(frozen=True)
class FactoryIssue:
    severity: str
    code: str
    message: str
    hint: str = ""

    def to_json(self) -> dict[str, str]:
        return asdict(self)


DEFAULT_FACTORY: dict[str, Any] = {
    "schema": FACTORY_SCHEMA,
    "enabled": False,
    "game_enabled": False,
    "stress_enabled": True,
    "selected_clip": "Default",
    "root_motion": True,
    "scanner_gate": False,
    "proximity_gate": False,
    "proximity_radius": 16.0,
    "nested_placements": True,
    "trigger_debug": True,
    "flow_debug": True,
    "theme_runtime": True,
    "event_policy": "telemetry_only",
    "max_nested_points": 100_000,
    "future_attributes": {},
}


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _vec3(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return [*default]
    return [_finite(value[i], default[i]) for i in range(3)]


def ensure_runtime_factory(document: PCPDocument) -> dict[str, Any]:
    current = document.metadata.get("runtime_factory")
    if not isinstance(current, dict):
        current = {}
        document.metadata["runtime_factory"] = current
    for key, value in DEFAULT_FACTORY.items():
        if key not in current:
            current[key] = json.loads(json.dumps(value)) if isinstance(value, (dict, list)) else value
    current["schema"] = FACTORY_SCHEMA
    current["proximity_radius"] = max(0.1, min(10_000.0, _finite(current.get("proximity_radius"), 16.0)))
    current["max_nested_points"] = max(1_000, min(500_000, int(_finite(current.get("max_nested_points"), 100_000))))
    if current.get("event_policy") not in {"telemetry_only", "disabled"}:
        current["event_policy"] = "telemetry_only"
    return current


def _selected_clip(authoring: dict[str, Any], name: str) -> dict[str, Any]:
    clips = [item for item in authoring.get("timelines", []) if isinstance(item, dict)]
    for clip in clips:
        if str(clip.get("name", "")) == name:
            return clip
    return clips[0] if clips else {"name": "Default", "duration": 1.0, "loop": True, "keyframes": [], "events": []}


def validate_runtime_factory(document: PCPDocument) -> list[FactoryIssue]:
    settings = ensure_runtime_factory(document)
    authoring = ensure_authoring(document)
    issues: list[FactoryIssue] = []
    if not settings["enabled"]:
        issues.append(FactoryIssue("info", "factory_disabled", "Runtime Factory is disabled; export remains preview-only."))
    if settings["enabled"] and not (settings["game_enabled"] or settings["stress_enabled"]):
        issues.append(FactoryIssue("warning", "no_runtime_target", "Factory is enabled but neither Game nor Stress target is enabled."))
    clip = _selected_clip(authoring, str(settings["selected_clip"]))
    roots = [key for key in clip.get("keyframes", []) if isinstance(key, dict) and str(key.get("target", "root")) == "root"]
    if settings["root_motion"] and not roots:
        issues.append(FactoryIssue("info", "root_motion_empty", "Root Motion is enabled but the selected clip has no root keyframes."))
    if len(roots) > MAX_KEYFRAMES:
        issues.append(FactoryIssue("warning", "keyframes_trimmed", f"Only the first {MAX_KEYFRAMES} root keyframes will be compiled."))
    placements = [p for p in authoring.get("placements", []) if isinstance(p, dict) and bool(p.get("enabled", True))]
    if settings["nested_placements"] and not placements:
        issues.append(FactoryIssue("info", "placements_empty", "Nested Placements is enabled but no enabled placements are authored."))
    if len(placements) > MAX_PLACEMENTS:
        issues.append(FactoryIssue("warning", "placements_trimmed", f"Only the first {MAX_PLACEMENTS} placements will be compiled."))
    for trigger in [t for t in authoring.get("triggers", []) if isinstance(t, dict)]:
        trigger_type = str(trigger.get("type", "proximity"))
        action = str(trigger.get("action", "none"))
        if trigger_type not in ALLOWED_TRIGGER_TYPES:
            issues.append(FactoryIssue("warning", "trigger_type_deferred", f"Trigger type {trigger_type!r} remains preserved but inactive."))
        if action not in ALLOWED_ACTIONS:
            issues.append(FactoryIssue("warning", "trigger_action_deferred", f"Trigger action {action!r} is not an approved runtime action and remains telemetry-only."))
    for clip_item in [c for c in authoring.get("timelines", []) if isinstance(c, dict)]:
        for event in [e for e in clip_item.get("events", []) if isinstance(e, dict)]:
            if str(event.get("type", "")) == "script":
                issues.append(FactoryIssue("warning", "scripts_blocked", "Script timeline events are preserved but never executed by the guarded Runtime Factory policy."))
    if settings["scanner_gate"] and not any(str(t.get("type")) == "scanner" for t in authoring.get("triggers", []) if isinstance(t, dict)):
        issues.append(FactoryIssue("info", "scanner_gate_global", "Scanner gate is enabled without a scanner trigger; the complete asset will require scanner mode."))
    if settings["proximity_gate"] and settings["proximity_radius"] <= 0.1:
        issues.append(FactoryIssue("error", "proximity_radius_invalid", "Proximity radius must be greater than 0.1."))
    if not any(issue.severity == "error" for issue in issues):
        issues.append(FactoryIssue("pass", "factory_compilable", "Runtime Factory data can be compiled under the guarded runtime policy."))
    return issues


def compile_runtime_factory(document: PCPDocument) -> dict[str, Any]:
    settings = ensure_runtime_factory(document)
    authoring = ensure_authoring(document)
    clip = _selected_clip(authoring, str(settings["selected_clip"]))
    keyframes = []
    if settings["root_motion"]:
        for source in [k for k in clip.get("keyframes", []) if isinstance(k, dict) and str(k.get("target", "root")) == "root"][:MAX_KEYFRAMES]:
            keyframes.append({
                "time": max(0.0, _finite(source.get("time"))),
                "position": _vec3(source.get("position")),
                "rotation_degrees": _vec3(source.get("rotation_degrees")),
                "scale": _vec3(source.get("scale"), (1.0, 1.0, 1.0)),
            })
        keyframes.sort(key=lambda item: item["time"])
    placements = []
    if settings["nested_placements"]:
        for source in [p for p in authoring.get("placements", []) if isinstance(p, dict) and bool(p.get("enabled", True))][:MAX_PLACEMENTS]:
            placements.append({
                "asset_id": str(source.get("asset_id", "")).strip(),
                "kind": str(source.get("kind", "object")),
                "position": _vec3(source.get("position")),
                "rotation_degrees": _vec3(source.get("rotation")),
                "scale": max(0.001, min(1000.0, _finite(source.get("scale"), 1.0))),
                "group": str(source.get("group", "")),
                "enabled": True,
            })
    triggers = []
    for source in [t for t in authoring.get("triggers", []) if isinstance(t, dict)][:MAX_TRIGGERS]:
        trigger_type = str(source.get("type", "proximity"))
        action = str(source.get("action", "none"))
        triggers.append({
            "type": trigger_type,
            "position": _vec3(source.get("position")),
            "radius": max(0.05, min(10_000.0, _finite(source.get("radius"), 1.0))),
            "action": action if action in ALLOWED_ACTIONS else "none",
            "original_action": action,
            "target": str(source.get("target", "")),
            "delay": max(0.0, _finite(source.get("delay"))),
            "repeat": bool(source.get("repeat", False)),
            "cooldown": max(0.05, min(60.0, _finite(source.get("cooldown"), 1.3))),
            "runtime_status": "approved" if trigger_type in ALLOWED_TRIGGER_TYPES and action in ALLOWED_ACTIONS else "telemetry_only",
        })
    flow_nodes = []
    if settings["flow_debug"]:
        for source in [n for n in authoring.get("flow", {}).get("nodes", []) if isinstance(n, dict)][:MAX_FLOW_NODES]:
            flow_nodes.append({
                "position": _vec3(source.get("position")),
                "direction": _vec3(source.get("direction", source.get("vector")), (1.0, 0.0, 0.0)),
                "strength": _finite(source.get("strength"), 1.0),
                "viscosity": max(0.0, _finite(source.get("viscosity"), 1.0)),
            })
    theme_slots = []
    if settings["theme_runtime"]:
        for source in [s for s in authoring.get("theme", {}).get("slots", []) if isinstance(s, dict)][:MAX_THEME_SLOTS]:
            theme_slots.append({
                "semantic": str(source.get("semantic", "generic")),
                "color": str(source.get("color", "#D9CC94")),
                "brush": str(source.get("brush", "")),
                "preset": str(source.get("preset", "")),
            })
    payload = {
        "schema": FACTORY_SCHEMA,
        "asset_id": document.asset_id,
        "environment_type": document.environment_type,
        "enabled": bool(settings["enabled"]),
        "targets": {"game": bool(settings["game_enabled"]), "stress": bool(settings["stress_enabled"])},
        "gates": {
            "scanner_required": bool(settings["scanner_gate"]),
            "proximity_required": bool(settings["proximity_gate"]),
            "proximity_radius": float(settings["proximity_radius"]),
        },
        "timeline": {
            "clip": str(clip.get("name", settings["selected_clip"])),
            "duration": max(0.001, _finite(clip.get("duration"), 1.0)),
            "loop": bool(clip.get("loop", True)),
            "keyframes": keyframes,
            "event_policy": str(settings["event_policy"]),
            "events": [event for event in clip.get("events", []) if isinstance(event, dict)],
        },
        "nested_placements": placements,
        "triggers": triggers,
        "flow_nodes": flow_nodes,
        "theme_slots": theme_slots,
        "limits": {
            "max_nested_points": int(settings["max_nested_points"]),
            "max_nesting_depth": 1,
            "max_keyframes": MAX_KEYFRAMES,
            "max_placements": MAX_PLACEMENTS,
        },
        "support": {
            "root_motion": "game_and_stress",
            "scanner_gate": "game_and_stress",
            "proximity_gate": "game_and_stress",
            "nested_pcp3_placements": "one_level_bounded",
            "trigger_actions": "approved_visual_and_alert_subset",
            "flow_fields": "debug_evidence_only",
            "timeline_events": "telemetry_only",
            "arbitrary_scripts": "blocked",
            "raid_waves": "deferred",
            "skeletal_deformation": "deferred",
        },
        "future_attributes": settings.get("future_attributes", {}),
        "policy": "guarded_explicit_opt_in_no_arbitrary_code",
    }
    return payload


def _json_value(value: Any) -> str:
    return json.dumps({"value": value}, separators=(",", ":"), ensure_ascii=False)


def runtime_factory_udata(payload: dict[str, Any]) -> str:
    lines = ["@udata 1", "", "[factory]"]
    lines += [
        f"schema: {_json_value(payload['schema'])};",
        f"enabled: {_json_value(payload['enabled'])};",
        f"game_enabled: {_json_value(payload['targets']['game'])};",
        f"stress_enabled: {_json_value(payload['targets']['stress'])};",
        f"scanner_required: {_json_value(payload['gates']['scanner_required'])};",
        f"proximity_required: {_json_value(payload['gates']['proximity_required'])};",
        f"proximity_radius: {_json_value(payload['gates']['proximity_radius'])};",
        f"clip: {_json_value(payload['timeline']['clip'])};",
        f"duration: {_json_value(payload['timeline']['duration'])};",
        f"loop: {_json_value(payload['timeline']['loop'])};",
        f"event_policy: {_json_value(payload['timeline']['event_policy'])};",
        f"max_nested_points: {_json_value(payload['limits']['max_nested_points'])};",
        "max_nesting_depth: " + _json_value(1) + ";",
        "",
    ]
    for index, keyframe in enumerate(payload["timeline"]["keyframes"]):
        lines += [f"[keyframe.{index}]", f"time: {_json_value(keyframe['time'])};", f"position: {_json_value(keyframe['position'])};",
                  f"rotation: {_json_value(keyframe['rotation_degrees'])};", f"scale: {_json_value(keyframe['scale'])};", ""]
    for index, placement in enumerate(payload["nested_placements"]):
        lines += [f"[placement.{index}]", f"asset_id: {_json_value(placement['asset_id'])};", f"kind: {_json_value(placement['kind'])};",
                  f"position: {_json_value(placement['position'])};", f"rotation: {_json_value(placement['rotation_degrees'])};",
                  f"scale: {_json_value(placement['scale'])};", f"enabled: {_json_value(placement['enabled'])};", ""]
    for index, trigger in enumerate(payload["triggers"]):
        lines += [f"[trigger.{index}]", f"type: {_json_value(trigger['type'])};", f"position: {_json_value(trigger['position'])};",
                  f"radius: {_json_value(trigger['radius'])};", f"action: {_json_value(trigger['action'])};",
                  f"target: {_json_value(trigger['target'])};", f"delay: {_json_value(trigger['delay'])};",
                  f"repeat: {_json_value(trigger['repeat'])};", f"cooldown: {_json_value(trigger['cooldown'])};",
                  f"runtime_status: {_json_value(trigger['runtime_status'])};", ""]
    for index, node in enumerate(payload["flow_nodes"]):
        lines += [f"[flow.{index}]", f"position: {_json_value(node['position'])};", f"direction: {_json_value(node['direction'])};",
                  f"strength: {_json_value(node['strength'])};", f"viscosity: {_json_value(node['viscosity'])};", ""]
    for index, slot in enumerate(payload["theme_slots"]):
        lines += [f"[theme.{index}]", f"semantic: {_json_value(slot['semantic'])};", f"color: {_json_value(slot['color'])};",
                  f"brush: {_json_value(slot['brush'])};", f"preset: {_json_value(slot['preset'])};", ""]
    return "\n".join(lines).rstrip() + "\n"


def write_runtime_factory_files(asset_dir: Path, document: PCPDocument) -> dict[str, Path]:
    payload = compile_runtime_factory(document)
    asset_name = slugify(document.asset_id)
    json_path = asset_dir / f"{asset_name}.pcp3factory.json"
    udata_path = asset_dir / f"{asset_name}.pcp3factory.udata"
    atomic_write_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(udata_path, runtime_factory_udata(payload))
    return {"json": json_path, "udata": udata_path}
