from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tools.pcp3.advanced_authoring import ensure_authoring, sample_clip
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.model import PCPDocument, PCPPoint

ENTITY_SCHEMA = "pcp3_entity_runtime_v1"
SUPPORTED_ENTITY_TYPES = {"enemy", "boss", "mini_boss", "friendly"}
MOVEMENT_PROFILES = (
    "stationary",
    "hover",
    "patrol_line",
    "face_viewer",
    "approach_viewer",
    "friendly_follow",
)
ENTITY_KINDS = ("enemy", "boss", "mini_boss", "friendly")
STATE_NAMES = ("idle", "move", "alert", "attack")
MAX_BONES = 64
MAX_ANCHORS = 64
MAX_BONE_KEYS = 512


@dataclass(frozen=True)
class EntityIssue:
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


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _vec3(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return [float(default[0]), float(default[1]), float(default[2])]
    return [_finite(value[index], default[index]) for index in range(3)]


def _default_kind(document: PCPDocument) -> str:
    return document.environment_type if document.environment_type in ENTITY_KINDS else "enemy"


def ensure_entity_runtime(document: PCPDocument) -> dict[str, Any]:
    value = document.metadata.get("entity_runtime")
    if not isinstance(value, dict):
        value = {}
        document.metadata["entity_runtime"] = value
    clips = [
        str(clip.get("name", "Default"))
        for clip in ensure_authoring(document).get("timelines", [])
        if isinstance(clip, dict)
    ] or ["Default"]
    defaults = {
        "schema": ENTITY_SCHEMA,
        "enabled": False,
        "game_enabled": False,
        "stress_enabled": True,
        "entity_kind": _default_kind(document),
        "movement_profile": "stationary",
        "movement_speed": 1.5,
        "movement_radius": 6.0,
        "hover_height": 0.35,
        "hover_period": 2.0,
        "detection_radius": 10.0,
        "attack_radius": 2.5,
        "attack_cooldown": 1.3,
        "transition_seconds": 0.18,
        "bone_deformation": True,
        "show_rig_debug": True,
        "show_anchor_debug": True,
        "show_state_debug": True,
        "max_deformed_points": 250_000,
        "state_clips": {
            "idle": clips[0],
            "move": clips[0],
            "alert": clips[0],
            "attack": clips[0],
        },
        "attack_anchor": "",
        "effect_anchor": "",
        "future_attributes": {},
    }
    for key, default in defaults.items():
        value.setdefault(key, default)
    if not isinstance(value.get("state_clips"), dict):
        value["state_clips"] = dict(defaults["state_clips"])
    for state in STATE_NAMES:
        value["state_clips"].setdefault(state, clips[0])
    value["schema"] = ENTITY_SCHEMA
    value["entity_kind"] = str(value.get("entity_kind", _default_kind(document)))
    if value["entity_kind"] not in ENTITY_KINDS:
        value["entity_kind"] = _default_kind(document)
    movement = str(value.get("movement_profile", "stationary"))
    value["movement_profile"] = movement if movement in MOVEMENT_PROFILES else "stationary"
    value["movement_speed"] = max(0.0, min(20.0, _finite(value.get("movement_speed"), 1.5)))
    value["movement_radius"] = max(0.0, min(100.0, _finite(value.get("movement_radius"), 6.0)))
    value["hover_height"] = max(0.0, min(10.0, _finite(value.get("hover_height"), 0.35)))
    value["hover_period"] = max(0.1, min(60.0, _finite(value.get("hover_period"), 2.0)))
    value["detection_radius"] = max(0.1, min(500.0, _finite(value.get("detection_radius"), 10.0)))
    value["attack_radius"] = max(0.1, min(value["detection_radius"], _finite(value.get("attack_radius"), 2.5)))
    value["attack_cooldown"] = max(0.1, min(60.0, _finite(value.get("attack_cooldown"), 1.3)))
    value["transition_seconds"] = max(0.0, min(5.0, _finite(value.get("transition_seconds"), 0.18)))
    try:
        max_points = int(value.get("max_deformed_points", 250_000))
    except (TypeError, ValueError):
        max_points = 250_000
    value["max_deformed_points"] = max(1_000, min(500_000, max_points))
    value.setdefault("future_attributes", {})
    return value


def assign_bone_channels(document: PCPDocument) -> dict[str, int]:
    """Assign stable, unique 0..63 channels while preserving valid existing values."""
    authoring = ensure_authoring(document)
    bones = [bone for bone in authoring["rig"]["bones"] if isinstance(bone, dict)][:MAX_BONES]
    used: set[int] = set()
    mapping: dict[str, int] = {}
    next_channel = 0
    for bone in bones:
        name = str(bone.get("name", "")).strip()
        try:
            channel = int(bone.get("weight_channel", -1))
        except (TypeError, ValueError):
            channel = -1
        if channel < 0 or channel >= MAX_BONES or channel in used:
            while next_channel in used and next_channel < MAX_BONES:
                next_channel += 1
            channel = min(next_channel, MAX_BONES - 1)
        used.add(channel)
        bone["weight_channel"] = channel
        if name:
            mapping[name] = channel
    return mapping


def _clip_by_name(authoring: dict[str, Any], name: str) -> dict[str, Any]:
    clips = [clip for clip in authoring.get("timelines", []) if isinstance(clip, dict)]
    for clip in clips:
        if str(clip.get("name", "")) == name:
            return clip
    return clips[0] if clips else {"name": "Default", "duration": 1.0, "loop": True, "keyframes": [], "events": []}


def _bone_parent_indices(bones: list[dict[str, Any]]) -> list[int]:
    index_by_name = {str(bone.get("name", "")): index for index, bone in enumerate(bones)}
    return [index_by_name.get(str(bone.get("parent", "")), -1) for bone in bones]


def validate_entity_runtime(document: PCPDocument) -> list[EntityIssue]:
    settings = ensure_entity_runtime(document)
    authoring = ensure_authoring(document)
    issues: list[EntityIssue] = []
    if document.environment_type not in SUPPORTED_ENTITY_TYPES:
        issues.append(EntityIssue(
            "warning",
            "unsupported_environment",
            f"{document.environment_type!r} is not an entity environment type; entity execution remains disabled until converted.",
            "Use Enemy, Boss, Mini-Boss, or User Friendly.",
        ))
    if settings["enabled"] and not (settings["game_enabled"] or settings["stress_enabled"]):
        issues.append(EntityIssue("error", "no_target", "Entity Runtime is enabled but neither Game nor Stress is selected."))
    bones = [bone for bone in authoring["rig"]["bones"] if isinstance(bone, dict)]
    if settings["bone_deformation"] and not bones:
        issues.append(EntityIssue("warning", "no_bones", "Bone deformation is enabled but no rig bones are authored."))
    mapping = assign_bone_channels(document)
    if len(set(mapping.values())) != len(mapping):
        issues.append(EntityIssue("error", "duplicate_channels", "Bone weight channels are not unique."))
    if len(bones) > MAX_BONES:
        issues.append(EntityIssue("warning", "bone_limit", f"Only the first {MAX_BONES} bones can execute in the current runtime."))
    weighted = sum(1 for point in document.points if int(round(point.attribute1)) == 41 or 1000 <= int(round(point.attribute1)) < 1000 + MAX_BONES)
    if settings["bone_deformation"] and bones and weighted == 0:
        issues.append(EntityIssue(
            "warning",
            "no_weighted_points",
            "The rig has bones, but no points carry a bone-weight channel.",
            "Use the 3D Brush Editor Bone Weight channel and select a bone.",
        ))
    clip_names = {str(clip.get("name", "")) for clip in authoring.get("timelines", []) if isinstance(clip, dict)}
    for state, clip_name in settings["state_clips"].items():
        if clip_name not in clip_names:
            issues.append(EntityIssue("warning", "missing_state_clip", f"State {state!r} references missing clip {clip_name!r}."))
    anchors = [anchor for anchor in authoring["rig"]["anchors"] if isinstance(anchor, dict)]
    anchor_names = {str(anchor.get("name", "")) for anchor in anchors}
    for key in ("attack_anchor", "effect_anchor"):
        name = str(settings.get(key, ""))
        if name and name not in anchor_names:
            issues.append(EntityIssue("warning", "missing_anchor", f"Configured {key.replace('_', ' ')} {name!r} does not exist."))
    if settings["attack_radius"] > settings["detection_radius"]:
        issues.append(EntityIssue("error", "radius_order", "Attack radius cannot exceed detection radius."))
    if not issues:
        issues.append(EntityIssue("pass", "entity_ready", "Entity Runtime passed guarded validation."))
    return issues


def compile_entity_runtime(document: PCPDocument) -> dict[str, Any]:
    settings = ensure_entity_runtime(document)
    authoring = ensure_authoring(document)
    channel_map = assign_bone_channels(document)
    bones = [bone for bone in authoring["rig"]["bones"] if isinstance(bone, dict)][:MAX_BONES]
    parents = _bone_parent_indices(bones)
    compiled_bones = []
    for index, bone in enumerate(bones):
        compiled_bones.append({
            "name": str(bone.get("name", f"bone_{index}")),
            "parent_index": parents[index],
            "start": _vec3(bone.get("start")),
            "end": _vec3(bone.get("end"), (0.0, 1.0, 0.0)),
            "weight_channel": int(bone.get("weight_channel", index)),
        })
    anchors = []
    for anchor in [a for a in authoring["rig"]["anchors"] if isinstance(a, dict)][:MAX_ANCHORS]:
        anchors.append({
            "name": str(anchor.get("name", "anchor")),
            "role": str(anchor.get("role", "generic")),
            "position": _vec3(anchor.get("position")),
        })
    states: dict[str, Any] = {}
    bone_keys: list[dict[str, Any]] = []
    for state in STATE_NAMES:
        clip = _clip_by_name(authoring, str(settings["state_clips"].get(state, "Default")))
        state_record = {
            "clip": str(clip.get("name", "Default")),
            "duration": max(0.001, _finite(clip.get("duration"), 1.0)),
            "loop": bool(clip.get("loop", True)),
        }
        states[state] = state_record
        for keyframe in [key for key in clip.get("keyframes", []) if isinstance(key, dict)]:
            target = str(keyframe.get("target", "root"))
            if target not in channel_map:
                continue
            if len(bone_keys) >= MAX_BONE_KEYS:
                break
            bone_keys.append({
                "state": state,
                "bone_channel": channel_map[target],
                "time": max(0.0, min(state_record["duration"], _finite(keyframe.get("time")))),
                "position": _vec3(keyframe.get("position")),
                "rotation_degrees": _vec3(keyframe.get("rotation_degrees")),
                "scale": _vec3(keyframe.get("scale"), (1.0, 1.0, 1.0)),
            })
    payload = {
        "schema": ENTITY_SCHEMA,
        "asset_id": document.asset_id,
        "environment_type": document.environment_type,
        "enabled": bool(settings["enabled"] and document.environment_type in SUPPORTED_ENTITY_TYPES),
        "targets": {"game": bool(settings["game_enabled"]), "stress": bool(settings["stress_enabled"])},
        "entity_kind": settings["entity_kind"],
        "movement": {
            "profile": settings["movement_profile"],
            "speed": settings["movement_speed"],
            "radius": settings["movement_radius"],
            "hover_height": settings["hover_height"],
            "hover_period": settings["hover_period"],
        },
        "senses": {
            "detection_radius": settings["detection_radius"],
            "attack_radius": settings["attack_radius"],
            "attack_cooldown": settings["attack_cooldown"],
        },
        "transition_seconds": settings["transition_seconds"],
        "bone_deformation": bool(settings["bone_deformation"]),
        "debug": {
            "rig": bool(settings["show_rig_debug"]),
            "anchors": bool(settings["show_anchor_debug"]),
            "state": bool(settings["show_state_debug"]),
        },
        "max_deformed_points": settings["max_deformed_points"],
        "state_clips": states,
        "bones": compiled_bones,
        "bone_keyframes": bone_keys,
        "anchors": anchors,
        "attack_anchor": str(settings.get("attack_anchor", "")),
        "effect_anchor": str(settings.get("effect_anchor", "")),
        "support": {
            "root_movement_profiles": "game_and_stress",
            "distance_state_machine": "idle_move_alert_attack",
            "per_bone_weighted_deformation": "one_weight_channel_per_point",
            "bone_hierarchy": "bounded_parent_chain",
            "attack_effect_anchors": "debug_and_telemetry_only",
            "damage": "blocked",
            "unrestricted_ai": "blocked",
            "animation_blending": "single_state_clip_with_guarded_transition",
        },
        "future_attributes": settings.get("future_attributes", {}),
        "policy": "guarded_entity_visual_runtime_no_damage_or_save_mutation",
    }
    return payload


def _json_value(value: Any) -> str:
    return json.dumps({"value": value}, separators=(",", ":"), ensure_ascii=False)


def entity_runtime_udata(payload: dict[str, Any]) -> str:
    lines = ["@udata 1", "", "[entity]"]
    lines += [
        f"schema: {_json_value(payload['schema'])};",
        f"enabled: {_json_value(payload['enabled'])};",
        f"game_enabled: {_json_value(payload['targets']['game'])};",
        f"stress_enabled: {_json_value(payload['targets']['stress'])};",
        f"entity_kind: {_json_value(payload['entity_kind'])};",
        f"movement_profile: {_json_value(payload['movement']['profile'])};",
        f"movement_speed: {_json_value(payload['movement']['speed'])};",
        f"movement_radius: {_json_value(payload['movement']['radius'])};",
        f"hover_height: {_json_value(payload['movement']['hover_height'])};",
        f"hover_period: {_json_value(payload['movement']['hover_period'])};",
        f"detection_radius: {_json_value(payload['senses']['detection_radius'])};",
        f"attack_radius: {_json_value(payload['senses']['attack_radius'])};",
        f"attack_cooldown: {_json_value(payload['senses']['attack_cooldown'])};",
        f"transition_seconds: {_json_value(payload['transition_seconds'])};",
        f"bone_deformation: {_json_value(payload['bone_deformation'])};",
        f"show_rig_debug: {_json_value(payload['debug']['rig'])};",
        f"show_anchor_debug: {_json_value(payload['debug']['anchors'])};",
        f"show_state_debug: {_json_value(payload['debug']['state'])};",
        f"max_deformed_points: {_json_value(payload['max_deformed_points'])};",
        f"attack_anchor: {_json_value(payload['attack_anchor'])};",
        f"effect_anchor: {_json_value(payload['effect_anchor'])};",
        "",
    ]
    for state, record in payload["state_clips"].items():
        lines += [
            f"[state.{state}]",
            f"clip: {_json_value(record['clip'])};",
            f"duration: {_json_value(record['duration'])};",
            f"loop: {_json_value(record['loop'])};",
            "",
        ]
    for index, bone in enumerate(payload["bones"]):
        lines += [
            f"[bone.{index}]",
            f"name: {_json_value(bone['name'])};",
            f"parent_index: {_json_value(bone['parent_index'])};",
            f"start: {_json_value(bone['start'])};",
            f"end: {_json_value(bone['end'])};",
            f"weight_channel: {_json_value(bone['weight_channel'])};",
            "",
        ]
    for index, key in enumerate(payload["bone_keyframes"]):
        lines += [
            f"[bone_keyframe.{index}]",
            f"state: {_json_value(key['state'])};",
            f"bone_channel: {_json_value(key['bone_channel'])};",
            f"time: {_json_value(key['time'])};",
            f"position: {_json_value(key['position'])};",
            f"rotation: {_json_value(key['rotation_degrees'])};",
            f"scale: {_json_value(key['scale'])};",
            "",
        ]
    for index, anchor in enumerate(payload["anchors"]):
        lines += [
            f"[anchor.{index}]",
            f"name: {_json_value(anchor['name'])};",
            f"role: {_json_value(anchor['role'])};",
            f"position: {_json_value(anchor['position'])};",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def write_entity_runtime_files(asset_dir: Path, document: PCPDocument) -> dict[str, Path]:
    payload = compile_entity_runtime(document)
    asset_name = slugify(document.asset_id)
    json_path = asset_dir / f"{asset_name}.pcp3entity.json"
    udata_path = asset_dir / f"{asset_name}.pcp3entity.udata"
    atomic_write_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(udata_path, entity_runtime_udata(payload))
    return {"json": json_path, "udata": udata_path}


def _rotate_xyz(point: list[float], degrees: list[float]) -> list[float]:
    x, y, z = point
    rx, ry, rz = [math.radians(value) for value in degrees]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return [x, y, z]


def sample_bone_transform(payload: dict[str, Any], state: str, channel: int, time_value: float) -> dict[str, list[float]]:
    keys = [
        key for key in payload.get("bone_keyframes", [])
        if key.get("state") == state and int(key.get("bone_channel", -1)) == int(channel)
    ]
    if not keys:
        return {"position": [0.0, 0.0, 0.0], "rotation_degrees": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]}
    keys.sort(key=lambda item: float(item.get("time", 0.0)))
    state_info = payload.get("state_clips", {}).get(state, {})
    duration = max(0.001, _finite(state_info.get("duration"), 1.0))
    t = max(0.0, float(time_value))
    if state_info.get("loop", True):
        t = t % duration
    if t <= float(keys[0]["time"]):
        return {name: list(keys[0][name]) for name in ("position", "rotation_degrees", "scale")}
    if t >= float(keys[-1]["time"]):
        return {name: list(keys[-1][name]) for name in ("position", "rotation_degrees", "scale")}
    left, right = keys[0], keys[-1]
    for index in range(1, len(keys)):
        if float(keys[index]["time"]) >= t:
            left, right = keys[index - 1], keys[index]
            break
    span = max(1e-6, float(right["time"]) - float(left["time"]))
    amount = max(0.0, min(1.0, (t - float(left["time"])) / span))
    return {
        name: [float(left[name][i]) + (float(right[name][i]) - float(left[name][i])) * amount for i in range(3)]
        for name in ("position", "rotation_degrees", "scale")
    }


def deform_point(point: PCPPoint, payload: dict[str, Any], state: str, time_value: float) -> tuple[float, float, float]:
    marker = int(round(point.attribute1))
    if marker == 41:
        channel = 0
    elif 1000 <= marker < 1000 + MAX_BONES:
        channel = marker - 1000
    else:
        return (point.x, point.y, point.z)
    weight = max(0.0, min(1.0, float(point.attribute0)))
    if weight <= 0.0:
        return (point.x, point.y, point.z)
    bones = {int(bone["weight_channel"]): bone for bone in payload.get("bones", [])}
    bone = bones.get(channel)
    if bone is None:
        return (point.x, point.y, point.z)
    transform = sample_bone_transform(payload, state, channel, time_value)
    start = [float(value) for value in bone["start"]]
    local = [point.x - start[0], point.y - start[1], point.z - start[2]]
    local = [local[index] * float(transform["scale"][index]) for index in range(3)]
    rotated = _rotate_xyz(local, transform["rotation_degrees"])
    target = [start[index] + rotated[index] + float(transform["position"][index]) for index in range(3)]
    original = [point.x, point.y, point.z]
    result = [original[index] + (target[index] - original[index]) * weight for index in range(3)]
    return (result[0], result[1], result[2])


def choose_entity_state(payload: dict[str, Any], viewer_distance: float, time_value: float) -> str:
    attack = float(payload.get("senses", {}).get("attack_radius", 2.5))
    detection = float(payload.get("senses", {}).get("detection_radius", 10.0))
    cooldown = max(0.1, float(payload.get("senses", {}).get("attack_cooldown", 1.3)))
    if viewer_distance <= attack and (float(time_value) % cooldown) <= min(0.25, cooldown * 0.25):
        return "attack"
    if viewer_distance <= attack:
        return "alert"
    if viewer_distance <= detection:
        return "move"
    return "idle"
