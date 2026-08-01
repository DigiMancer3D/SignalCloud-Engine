from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tools.pcp3.io import atomic_write_text
from tools.pcp3.model import PCPDocument

AUTHORING_SCHEMA = "pcp3_advanced_authoring_v1"

CAPABILITIES: dict[str, tuple[str, ...]] = {
    "enemy": ("rig", "timeline", "gameplay"),
    "boss": ("rig", "timeline", "gameplay", "placement"),
    "mini_boss": ("rig", "timeline", "gameplay"),
    "raid": ("gameplay", "placement"),
    "friendly": ("rig", "timeline", "gameplay"),
    "environment_object": ("timeline", "gameplay", "placement", "theme"),
    "environment_theme": ("theme", "placement"),
    "room": ("gameplay", "placement", "theme", "flow"),
    "liquid": ("flow", "gameplay", "theme"),
}

DEFAULT_CLIP = {
    "name": "Default",
    "duration": 1.0,
    "fps": 30,
    "loop": True,
    "keyframes": [],
    "events": [],
}


@dataclass(frozen=True)
class AuthoringIssue:
    severity: str
    code: str
    message: str
    hint: str = ""

    def to_json(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }


def _vec3(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return [float(default[0]), float(default[1]), float(default[2])]
    output: list[float] = []
    for index in range(3):
        try:
            number = float(value[index])
        except (TypeError, ValueError):
            number = default[index]
        output.append(number if math.isfinite(number) else float(default[index]))
    return output


def _positive(value: Any, default: float, minimum: float = 0.0001) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    return max(minimum, number)


def _new_authoring() -> dict[str, Any]:
    return {
        "schema": AUTHORING_SCHEMA,
        "rig": {"bones": [], "anchors": []},
        "timelines": [copy.deepcopy(DEFAULT_CLIP)],
        "triggers": [],
        "placements": [],
        "flow": {"nodes": []},
        "theme": {"slots": []},
        "raid": {"waves": []},
        "future_attributes": {},
    }


def ensure_authoring(document: PCPDocument) -> dict[str, Any]:
    value = document.metadata.get("advanced_authoring")
    if not isinstance(value, dict):
        value = _new_authoring()
        document.metadata["advanced_authoring"] = value
    value.setdefault("schema", AUTHORING_SCHEMA)
    rig = value.setdefault("rig", {})
    if not isinstance(rig, dict):
        rig = {"bones": [], "anchors": []}
        value["rig"] = rig
    rig.setdefault("bones", [])
    rig.setdefault("anchors", [])
    timelines = value.setdefault("timelines", [copy.deepcopy(DEFAULT_CLIP)])
    if not isinstance(timelines, list):
        timelines = [copy.deepcopy(DEFAULT_CLIP)]
        value["timelines"] = timelines
    if not timelines:
        timelines.append(copy.deepcopy(DEFAULT_CLIP))
    value.setdefault("triggers", [])
    value.setdefault("placements", [])
    flow = value.setdefault("flow", {})
    if not isinstance(flow, dict):
        flow = {"nodes": []}
        value["flow"] = flow
    flow.setdefault("nodes", [])
    theme = value.setdefault("theme", {})
    if not isinstance(theme, dict):
        theme = {"slots": []}
        value["theme"] = theme
    theme.setdefault("slots", [])
    raid = value.setdefault("raid", {})
    if not isinstance(raid, dict):
        raid = {"waves": []}
        value["raid"] = raid
    raid.setdefault("waves", [])
    value.setdefault("future_attributes", {})
    return value


def capabilities_for(environment_type: str) -> tuple[str, ...]:
    return CAPABILITIES.get(environment_type, CAPABILITIES["environment_object"])


def next_identifier(records: Iterable[dict[str, Any]], prefix: str) -> str:
    used = {str(record.get("id", "")) for record in records if isinstance(record, dict)}
    index = 1
    while f"{prefix}_{index}" in used:
        index += 1
    return f"{prefix}_{index}"


def add_bone(authoring: dict[str, Any], name: str, parent: str, start: Any, end: Any) -> dict[str, Any]:
    bones = authoring["rig"]["bones"]
    clean_name = name.strip() or next_identifier(bones, "bone")
    if any(str(item.get("name", "")).casefold() == clean_name.casefold() for item in bones if isinstance(item, dict)):
        raise ValueError(f"A bone named {clean_name!r} already exists.")
    record = {
        "id": next_identifier(bones, "bone"),
        "name": clean_name,
        "parent": parent.strip(),
        "start": _vec3(start),
        "end": _vec3(end, (0.0, 1.0, 0.0)),
        "weight_channel": 0,
        "future_attributes": {},
    }
    bones.append(record)
    return record


def add_anchor(authoring: dict[str, Any], name: str, role: str, position: Any) -> dict[str, Any]:
    anchors = authoring["rig"]["anchors"]
    record = {
        "id": next_identifier(anchors, "anchor"),
        "name": name.strip() or next_identifier(anchors, "anchor"),
        "role": role.strip() or "generic",
        "position": _vec3(position),
        "future_attributes": {},
    }
    anchors.append(record)
    return record


def add_clip(authoring: dict[str, Any], name: str, duration: float = 1.0, fps: int = 30, loop: bool = True) -> dict[str, Any]:
    clips = authoring["timelines"]
    clean = name.strip() or next_identifier(clips, "clip")
    record = {
        "name": clean,
        "duration": _positive(duration, 1.0),
        "fps": max(1, min(240, int(fps))),
        "loop": bool(loop),
        "keyframes": [],
        "events": [],
        "future_attributes": {},
    }
    clips.append(record)
    return record


def add_keyframe(clip: dict[str, Any], time_value: float, target: str, position: Any, rotation: Any, scale: Any) -> dict[str, Any]:
    duration = _positive(clip.get("duration", 1.0), 1.0)
    time_value = max(0.0, min(duration, float(time_value)))
    keyframes = clip.setdefault("keyframes", [])
    record = {
        "id": next_identifier(keyframes, "key"),
        "time": time_value,
        "target": target.strip() or "root",
        "position": _vec3(position),
        "rotation_degrees": _vec3(rotation),
        "scale": _vec3(scale, (1.0, 1.0, 1.0)),
        "interpolation": "linear",
        "future_attributes": {},
    }
    keyframes.append(record)
    keyframes.sort(key=lambda item: (float(item.get("time", 0.0)), str(item.get("target", ""))))
    return record


def add_timeline_event(clip: dict[str, Any], time_value: float, event_type: str, action: str, payload: Any = None) -> dict[str, Any]:
    duration = _positive(clip.get("duration", 1.0), 1.0)
    events = clip.setdefault("events", [])
    record = {
        "id": next_identifier(events, "event"),
        "time": max(0.0, min(duration, float(time_value))),
        "type": event_type.strip() or "effect",
        "action": action.strip() or "none",
        "payload": payload if payload is not None else {},
    }
    events.append(record)
    events.sort(key=lambda item: float(item.get("time", 0.0)))
    return record


def sample_clip(clip: dict[str, Any], time_value: float, target: str = "root") -> dict[str, list[float]]:
    keyframes = [
        item for item in clip.get("keyframes", [])
        if isinstance(item, dict) and str(item.get("target", "root")) == target
    ]
    if not keyframes:
        return {"position": [0.0, 0.0, 0.0], "rotation_degrees": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}
    keyframes.sort(key=lambda item: float(item.get("time", 0.0)))
    time_value = float(time_value)
    if time_value <= float(keyframes[0].get("time", 0.0)):
        chosen = keyframes[0]
        return {"position": _vec3(chosen.get("position")), "rotation_degrees": _vec3(chosen.get("rotation_degrees")), "scale": _vec3(chosen.get("scale"), (1.0, 1.0, 1.0))}
    if time_value >= float(keyframes[-1].get("time", 0.0)):
        chosen = keyframes[-1]
        return {"position": _vec3(chosen.get("position")), "rotation_degrees": _vec3(chosen.get("rotation_degrees")), "scale": _vec3(chosen.get("scale"), (1.0, 1.0, 1.0))}
    left = keyframes[0]
    right = keyframes[-1]
    for index in range(1, len(keyframes)):
        candidate = keyframes[index]
        if float(candidate.get("time", 0.0)) >= time_value:
            left = keyframes[index - 1]
            right = candidate
            break
    left_time = float(left.get("time", 0.0))
    right_time = float(right.get("time", left_time + 1.0))
    amount = 0.0 if right_time <= left_time else (time_value - left_time) / (right_time - left_time)

    def lerp(a: list[float], b: list[float]) -> list[float]:
        return [a[index] + (b[index] - a[index]) * amount for index in range(3)]

    return {
        "position": lerp(_vec3(left.get("position")), _vec3(right.get("position"))),
        "rotation_degrees": lerp(_vec3(left.get("rotation_degrees")), _vec3(right.get("rotation_degrees"))),
        "scale": lerp(_vec3(left.get("scale"), (1.0, 1.0, 1.0)), _vec3(right.get("scale"), (1.0, 1.0, 1.0))),
    }


def add_trigger(authoring: dict[str, Any], trigger_type: str, position: Any, radius: float, action: str, target: str = "", delay: float = 0.0, repeat: bool = False, cooldown: float | None = None) -> dict[str, Any]:
    triggers = authoring["triggers"]
    record = {
        "id": next_identifier(triggers, "trigger"),
        "type": trigger_type.strip() or "proximity",
        "position": _vec3(position),
        "radius": _positive(radius, 1.0),
        "action": action.strip() or "none",
        "target": target.strip(),
        "delay": max(0.0, float(delay)),
        "repeat": bool(repeat),
        "conditions": [],
        "future_attributes": {},
    }
    if cooldown is not None:
        record["cooldown"] = max(0.05, min(60.0, float(cooldown)))
    triggers.append(record)
    return record


def add_placement(authoring: dict[str, Any], asset_id: str, kind: str, position: Any, rotation: Any, scale: float = 1.0, group: str = "") -> dict[str, Any]:
    placements = authoring["placements"]
    record = {
        "id": next_identifier(placements, "placement"),
        "asset_id": asset_id.strip() or "unassigned_asset",
        "kind": kind.strip() or "object",
        "position": _vec3(position),
        "rotation_degrees": _vec3(rotation),
        "scale": _positive(scale, 1.0),
        "group": group.strip(),
        "enabled": True,
        "future_attributes": {},
    }
    placements.append(record)
    return record


def add_flow_node(authoring: dict[str, Any], position: Any, vector: Any, strength: float = 1.0, viscosity: float = 1.0) -> dict[str, Any]:
    nodes = authoring["flow"]["nodes"]
    direction = _vec3(vector, (1.0, 0.0, 0.0))
    length = math.sqrt(sum(value * value for value in direction))
    if length < 1e-9:
        direction = [1.0, 0.0, 0.0]
    else:
        direction = [value / length for value in direction]
    record = {
        "id": next_identifier(nodes, "flow"),
        "position": _vec3(position),
        "direction": direction,
        "strength": max(0.0, float(strength)),
        "viscosity": max(0.0, float(viscosity)),
        "future_attributes": {},
    }
    nodes.append(record)
    return record


def add_theme_slot(authoring: dict[str, Any], semantic: str, color: str, brush: str = "", preset: str = "") -> dict[str, Any]:
    slots = authoring["theme"]["slots"]
    clean_semantic = semantic.strip() or "generic"
    for slot in slots:
        if isinstance(slot, dict) and str(slot.get("semantic", "")).casefold() == clean_semantic.casefold():
            slot.update({"color": color.strip() or "#D9CC94", "brush": brush.strip(), "preset": preset.strip()})
            return slot
    record = {
        "id": next_identifier(slots, "theme"),
        "semantic": clean_semantic,
        "color": color.strip() or "#D9CC94",
        "brush": brush.strip(),
        "preset": preset.strip(),
        "future_attributes": {},
    }
    slots.append(record)
    return record


def add_wave(authoring: dict[str, Any], index: int, asset_ids: list[str], count: int, delay: float = 0.0) -> dict[str, Any]:
    waves = authoring["raid"]["waves"]
    record = {
        "id": next_identifier(waves, "wave"),
        "index": max(1, int(index)),
        "asset_ids": [value.strip() for value in asset_ids if value.strip()],
        "count": max(1, int(count)),
        "delay": max(0.0, float(delay)),
        "future_attributes": {},
    }
    waves.append(record)
    waves.sort(key=lambda item: int(item.get("index", 0)))
    return record


def _validate_cycle(bones: list[dict[str, Any]]) -> bool:
    parent_map = {str(bone.get("name", "")): str(bone.get("parent", "")) for bone in bones}
    for name in parent_map:
        seen: set[str] = set()
        current = name
        while current:
            if current in seen:
                return True
            seen.add(current)
            current = parent_map.get(current, "")
    return False


def validate_authoring(document: PCPDocument) -> list[AuthoringIssue]:
    authoring = ensure_authoring(document)
    issues: list[AuthoringIssue] = []
    capabilities = capabilities_for(document.environment_type)
    bones = [item for item in authoring["rig"]["bones"] if isinstance(item, dict)]
    names = [str(item.get("name", "")).strip() for item in bones]
    duplicates = {name for name in names if name and names.count(name) > 1}
    if duplicates:
        issues.append(AuthoringIssue("error", "duplicate_bones", f"Duplicate bone names: {', '.join(sorted(duplicates))}"))
    known = set(names)
    missing_parents = sorted({str(item.get("parent", "")) for item in bones if str(item.get("parent", "")) and str(item.get("parent", "")) not in known})
    if missing_parents:
        issues.append(AuthoringIssue("error", "missing_bone_parent", f"Missing bone parents: {', '.join(missing_parents)}"))
    if _validate_cycle(bones):
        issues.append(AuthoringIssue("error", "bone_cycle", "The bone hierarchy contains a parent cycle."))
    for bone in bones:
        if _vec3(bone.get("start")) == _vec3(bone.get("end")):
            issues.append(AuthoringIssue("warning", "zero_length_bone", f"Bone {bone.get('name', '?')} has zero length."))

    clips = [item for item in authoring["timelines"] if isinstance(item, dict)]
    for clip in clips:
        duration = _positive(clip.get("duration", 1.0), 1.0)
        for keyframe in clip.get("keyframes", []):
            if not isinstance(keyframe, dict):
                continue
            time_value = float(keyframe.get("time", 0.0))
            if time_value < 0.0 or time_value > duration:
                issues.append(AuthoringIssue("error", "keyframe_time", f"Clip {clip.get('name', '?')} has a keyframe outside its duration."))

    for trigger in authoring["triggers"]:
        if not isinstance(trigger, dict):
            continue
        if not str(trigger.get("action", "")).strip() or str(trigger.get("action", "")) == "none":
            issues.append(AuthoringIssue("warning", "trigger_action", f"Trigger {trigger.get('id', '?')} has no action."))
        if float(trigger.get("radius", 0.0)) <= 0.0:
            issues.append(AuthoringIssue("error", "trigger_radius", f"Trigger {trigger.get('id', '?')} has an invalid radius."))

    for placement in authoring["placements"]:
        if isinstance(placement, dict) and str(placement.get("asset_id", "")) in {"", "unassigned_asset"}:
            issues.append(AuthoringIssue("warning", "placement_asset", f"Placement {placement.get('id', '?')} has no assigned asset."))

    for node in authoring["flow"]["nodes"]:
        if not isinstance(node, dict):
            continue
        direction = _vec3(node.get("direction"), (1.0, 0.0, 0.0))
        length = math.sqrt(sum(value * value for value in direction))
        if abs(length - 1.0) > 1e-3:
            issues.append(AuthoringIssue("warning", "flow_normalization", f"Flow node {node.get('id', '?')} direction is not normalized."))

    if "rig" in capabilities and not bones:
        issues.append(AuthoringIssue("info", "rig_empty", "This mode supports rigging, but no bones are authored yet."))
    if "timeline" in capabilities and not any(clip.get("keyframes") or clip.get("events") for clip in clips):
        issues.append(AuthoringIssue("info", "timeline_empty", "This mode supports animation timelines, but no keyframes or events are authored yet."))
    if "gameplay" in capabilities and not authoring["triggers"]:
        issues.append(AuthoringIssue("info", "triggers_empty", "This mode supports gameplay triggers, but none are authored yet."))
    if "flow" in capabilities and not authoring["flow"]["nodes"]:
        issues.append(AuthoringIssue("info", "flow_empty", "This mode supports liquid/flow authoring, but no flow nodes are authored yet."))
    if "theme" in capabilities and not authoring["theme"]["slots"]:
        issues.append(AuthoringIssue("info", "theme_empty", "This mode supports theme slots, but none are authored yet."))
    if not issues:
        issues.append(AuthoringIssue("pass", "authoring_ready", "Advanced authoring data passed validation."))
    return issues


def authoring_summary(document: PCPDocument) -> dict[str, int]:
    authoring = ensure_authoring(document)
    return {
        "bones": len(authoring["rig"]["bones"]),
        "anchors": len(authoring["rig"]["anchors"]),
        "clips": len(authoring["timelines"]),
        "keyframes": sum(len(clip.get("keyframes", [])) for clip in authoring["timelines"] if isinstance(clip, dict)),
        "events": sum(len(clip.get("events", [])) for clip in authoring["timelines"] if isinstance(clip, dict)),
        "triggers": len(authoring["triggers"]),
        "placements": len(authoring["placements"]),
        "flow_nodes": len(authoring["flow"]["nodes"]),
        "theme_slots": len(authoring["theme"]["slots"]),
        "raid_waves": len(authoring["raid"]["waves"]),
    }


def write_authoring_report(path: Path, document: PCPDocument, issues: list[AuthoringIssue] | None = None) -> Path:
    authoring = ensure_authoring(document)
    issues = issues if issues is not None else validate_authoring(document)
    payload = {
        "schema": AUTHORING_SCHEMA,
        "asset_id": document.asset_id,
        "environment_type": document.environment_type,
        "capabilities": list(capabilities_for(document.environment_type)),
        "summary": authoring_summary(document),
        "issues": [issue.to_json() for issue in issues],
        "data": authoring,
        "policy": "forgiving_preserve_unknown_until_pce_runtime_support",
    }
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path
