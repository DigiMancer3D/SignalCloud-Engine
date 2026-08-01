from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from tools.pcp3.advanced_authoring import ensure_authoring
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.model import PCPDocument, SEMANTIC_FLAGS

WORLD_SCHEMA = "pcp3_world_assembly_v1"
WORLD_TYPES = {"room", "environment_theme", "liquid", "raid", "environment_object"}
PORTAL_KINDS = ("door", "window", "portal", "drop", "threshold")
RESET_POLICIES = ("zone_exit", "session", "manual")
MAX_PORTALS = 32
MAX_SPAWNS = 32
MAX_PLACEMENTS = 64
MAX_FLOW_NODES = 64
MAX_THEME_SLOTS = 64
MAX_REFERENCE_SCAN = 4096


@dataclass(frozen=True)
class WorldIssue:
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
        return float(default)
    return number if math.isfinite(number) else float(default)


def _vec3(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return [float(default[0]), float(default[1]), float(default[2])]
    return [_finite(value[index], default[index]) for index in range(3)]


def _positive(value: Any, default: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, _finite(value, default)))


def _integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _default_world(document: PCPDocument) -> dict[str, Any]:
    return {
        "schema": WORLD_SCHEMA,
        "enabled": False,
        "game_enabled": False,
        "stress_enabled": True,
        "world_id": "pcp3_world",
        "room_id": document.asset_id,
        "room_name": document.display_name,
        "host_zone": str(document.runtime.get("preview_zone", "Reception Tape")),
        "safe_room": False,
        "logical_level": 0,
        "theme_asset_id": "",
        "apply_theme": True,
        "execute_portals": False,
        "portal_interaction_required": True,
        "portal_cooldown": 0.8,
        "show_portal_debug": True,
        "show_bounds_debug": False,
        "liquid_runtime": document.environment_type == "liquid",
        "liquid_type": "water",
        "liquid_color": "#2F6F8F",
        "liquid_opacity": 0.72,
        "wave_amplitude": 0.06,
        "wave_frequency": 0.7,
        "flow_scale": 1.0,
        "max_portals": MAX_PORTALS,
        "max_placements": MAX_PLACEMENTS,
        "max_liquid_points": 150_000,
        "reset_policy": "zone_exit",
        "portals": [],
        "spawn_points": [],
        "future_attributes": {},
    }


def ensure_world_assembly(document: PCPDocument) -> dict[str, Any]:
    value = document.metadata.get("world_assembly")
    if not isinstance(value, dict):
        value = _default_world(document)
        document.metadata["world_assembly"] = value
    defaults = _default_world(document)
    for key, default in defaults.items():
        value.setdefault(key, default)
    value["schema"] = WORLD_SCHEMA
    value["world_id"] = slugify(str(value.get("world_id") or "pcp3_world"))
    value["room_id"] = slugify(str(value.get("room_id") or document.asset_id or "room"))
    value["room_name"] = str(value.get("room_name") or document.display_name or value["room_id"])
    value["host_zone"] = str(value.get("host_zone") or document.runtime.get("preview_zone", "Reception Tape"))
    value["logical_level"] = _integer(value.get("logical_level"), 0, -4096, 4096)
    value["portal_cooldown"] = _positive(value.get("portal_cooldown"), 0.8, 0.1, 30.0)
    value["liquid_opacity"] = _positive(value.get("liquid_opacity"), 0.72, 0.0, 1.0)
    value["wave_amplitude"] = _positive(value.get("wave_amplitude"), 0.06, 0.0, 5.0)
    value["wave_frequency"] = _positive(value.get("wave_frequency"), 0.7, 0.01, 20.0)
    value["flow_scale"] = _positive(value.get("flow_scale"), 1.0, 0.0, 100.0)
    value["max_portals"] = _integer(value.get("max_portals"), MAX_PORTALS, 1, MAX_PORTALS)
    value["max_placements"] = _integer(value.get("max_placements"), MAX_PLACEMENTS, 1, MAX_PLACEMENTS)
    value["max_liquid_points"] = _integer(value.get("max_liquid_points"), 150_000, 1_000, 500_000)
    if str(value.get("reset_policy", "zone_exit")) not in RESET_POLICIES:
        value["reset_policy"] = "zone_exit"
    if not isinstance(value.get("portals"), list):
        value["portals"] = []
    if not isinstance(value.get("spawn_points"), list):
        value["spawn_points"] = []
    if not isinstance(value.get("future_attributes"), dict):
        value["future_attributes"] = {}

    cleaned_portals: list[dict[str, Any]] = []
    for index, raw in enumerate(value["portals"][:MAX_PORTALS]):
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        record.setdefault("id", f"portal_{index + 1}")
        record["id"] = slugify(str(record.get("id") or f"portal_{index + 1}"))
        kind = str(record.get("kind", "door"))
        record["kind"] = kind if kind in PORTAL_KINDS else "door"
        record["position"] = _vec3(record.get("position"))
        record["size"] = [
            _positive((_vec3(record.get("size"), (1.2, 2.2, 0.4)))[0], 1.2, 0.05, 100.0),
            _positive((_vec3(record.get("size"), (1.2, 2.2, 0.4)))[1], 2.2, 0.05, 100.0),
            _positive((_vec3(record.get("size"), (1.2, 2.2, 0.4)))[2], 0.4, 0.05, 100.0),
        ]
        record["destination_asset_id"] = slugify(str(record.get("destination_asset_id", ""))) if record.get("destination_asset_id") else ""
        record["destination_portal_id"] = slugify(str(record.get("destination_portal_id", ""))) if record.get("destination_portal_id") else ""
        record["arrival_offset"] = _vec3(record.get("arrival_offset"), (0.0, 0.0, 1.4))
        record["arrival_yaw_degrees"] = _finite(record.get("arrival_yaw_degrees"), 0.0)
        record["interaction_required"] = bool(record.get("interaction_required", value["portal_interaction_required"]))
        record["one_way"] = bool(record.get("one_way", False))
        record["enabled"] = bool(record.get("enabled", True))
        record.setdefault("future_attributes", {})
        cleaned_portals.append(record)
    value["portals"] = cleaned_portals

    cleaned_spawns: list[dict[str, Any]] = []
    for index, raw in enumerate(value["spawn_points"][:MAX_SPAWNS]):
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        record["id"] = slugify(str(record.get("id") or f"spawn_{index + 1}"))
        record["role"] = str(record.get("role") or "default")
        record["position"] = _vec3(record.get("position"))
        record["yaw_degrees"] = _finite(record.get("yaw_degrees"), 0.0)
        record["enabled"] = bool(record.get("enabled", True))
        record.setdefault("future_attributes", {})
        cleaned_spawns.append(record)
    value["spawn_points"] = cleaned_spawns
    return value


def add_portal(
    document: PCPDocument,
    *,
    portal_id: str,
    kind: str,
    position: Any,
    size: Any,
    destination_asset_id: str = "",
    destination_portal_id: str = "",
    arrival_offset: Any = (0.0, 0.0, 1.4),
    arrival_yaw_degrees: float = 0.0,
    interaction_required: bool | None = None,
    one_way: bool = False,
) -> dict[str, Any]:
    world = ensure_world_assembly(document)
    if len(world["portals"]) >= int(world["max_portals"]):
        raise ValueError("The current guarded portal limit has been reached.")
    clean_id = slugify(portal_id or f"portal_{len(world['portals']) + 1}")
    if any(str(item.get("id", "")) == clean_id for item in world["portals"] if isinstance(item, dict)):
        raise ValueError(f"A portal named {clean_id!r} already exists.")
    record = {
        "id": clean_id,
        "kind": kind if kind in PORTAL_KINDS else "door",
        "position": _vec3(position),
        "size": _vec3(size, (1.2, 2.2, 0.4)),
        "destination_asset_id": slugify(destination_asset_id) if destination_asset_id else "",
        "destination_portal_id": slugify(destination_portal_id) if destination_portal_id else "",
        "arrival_offset": _vec3(arrival_offset, (0.0, 0.0, 1.4)),
        "arrival_yaw_degrees": _finite(arrival_yaw_degrees),
        "interaction_required": world["portal_interaction_required"] if interaction_required is None else bool(interaction_required),
        "one_way": bool(one_way),
        "enabled": True,
        "future_attributes": {},
    }
    world["portals"].append(record)
    document.dirty = True
    return record


def add_spawn_point(document: PCPDocument, name: str, role: str, position: Any, yaw_degrees: float = 0.0) -> dict[str, Any]:
    world = ensure_world_assembly(document)
    if len(world["spawn_points"]) >= MAX_SPAWNS:
        raise ValueError("The current guarded spawn-point limit has been reached.")
    clean_id = slugify(name or f"spawn_{len(world['spawn_points']) + 1}")
    record = {
        "id": clean_id,
        "role": role.strip() or "default",
        "position": _vec3(position),
        "yaw_degrees": _finite(yaw_degrees),
        "enabled": True,
        "future_attributes": {},
    }
    world["spawn_points"].append(record)
    document.dirty = True
    return record


def _extract_udata_string(text: str, section: str, key: str) -> str:
    current = ""
    pattern = re.compile(r'^\s*"value"\s*:\s*"(.*?)"\s*}\s*;?\s*$')
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            continue
        if current != section or not line.startswith(key + ":"):
            continue
        value = line.split(":", 1)[1].strip().rstrip(";")
        match = pattern.match(value)
        if match:
            return bytes(match.group(1), "utf-8").decode("unicode_escape")
        try:
            payload = json.loads(value)
            if isinstance(payload, dict):
                return str(payload.get("value", ""))
        except json.JSONDecodeError:
            return ""
    return ""


def discover_exported_assets(project_root: Path) -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    base = project_root / "content" / "pcp3_assets"
    if not base.exists():
        return assets
    count = 0
    for path in sorted(base.rglob("*.udata")):
        if any(path.name.endswith(suffix) for suffix in (
            ".pcp3factory.udata", ".pcp3interaction.udata", ".pcp3entity.udata", ".pcp3world.udata"
        )):
            continue
        if count >= MAX_REFERENCE_SCAN:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _extract_udata_string(text, "header", "data_type") != "pcp3_asset":
            continue
        asset_id = _extract_udata_string(text, "header", "asset_id")
        if not asset_id:
            continue
        assets[asset_id] = {
            "asset_id": asset_id,
            "display_name": _extract_udata_string(text, "header", "display_name"),
            "environment_type": _extract_udata_string(text, "header", "asset_kind"),
            "preview_zone": _extract_udata_string(text, "runtime", "preview_zone"),
            "udata_path": path,
            "asset_dir": path.parent,
        }
        count += 1
    return assets


def _semantic_point_count(document: PCPDocument, names: Iterable[str]) -> int:
    flags = {SEMANTIC_FLAGS.get(name, -1) for name in names}
    return sum(1 for point in document.points if point.flags in flags)


def validate_world_assembly(document: PCPDocument, project_root: Path | None = None) -> list[WorldIssue]:
    world = ensure_world_assembly(document)
    authoring = ensure_authoring(document)
    issues: list[WorldIssue] = []
    assets = discover_exported_assets(project_root) if project_root is not None else {}

    if document.environment_type not in WORLD_TYPES:
        issues.append(WorldIssue(
            "warning", "environment_type",
            f"{document.environment_type!r} is not a primary world-assembly type.",
            "Room, Environment Theme, Liquid Maker, Raid, and Environment Object are the intended Phase 9 inputs.",
        ))
    if world["enabled"] and not (world["game_enabled"] or world["stress_enabled"]):
        issues.append(WorldIssue("error", "no_target", "World Assembly is enabled but neither Game nor Stress is selected."))
    if not world["room_id"]:
        issues.append(WorldIssue("error", "room_id", "Room ID cannot be empty."))
    if not world["host_zone"]:
        issues.append(WorldIssue("error", "host_zone", "A host SignalCloud zone is required."))
    if str(document.runtime.get("preview_zone", "")) != world["host_zone"]:
        issues.append(WorldIssue(
            "info", "host_zone_mismatch",
            "World host zone differs from the asset Runtime preview zone.",
            "Export will normalize the Runtime preview zone to the selected host zone.",
        ))

    portal_ids: set[str] = set()
    for index, portal in enumerate(world["portals"]):
        portal_id = str(portal.get("id", ""))
        if not portal_id:
            issues.append(WorldIssue("error", "portal_id", f"Portal {index + 1} has no ID."))
        elif portal_id in portal_ids:
            issues.append(WorldIssue("error", "portal_duplicate", f"Portal ID {portal_id!r} is duplicated."))
        portal_ids.add(portal_id)
        if any(not math.isfinite(float(value)) for value in portal.get("position", [])):
            issues.append(WorldIssue("error", "portal_position", f"Portal {portal_id or index + 1} has a non-finite position."))
        if any(float(value) <= 0.0 for value in portal.get("size", [1, 1, 1])):
            issues.append(WorldIssue("error", "portal_size", f"Portal {portal_id or index + 1} requires positive width, height, and depth."))
        destination = str(portal.get("destination_asset_id", ""))
        destination_portal = str(portal.get("destination_portal_id", ""))
        if world["execute_portals"] and portal.get("enabled", True) and not destination:
            issues.append(WorldIssue("warning", "portal_unlinked", f"Portal {portal_id!r} has no destination asset and remains evidence-only."))
        if destination and destination == document.asset_id and destination_portal and destination_portal not in portal_ids and destination_portal not in {
            str(item.get("id", "")) for item in world["portals"] if isinstance(item, dict)
        }:
            issues.append(WorldIssue("warning", "portal_destination_missing", f"Portal {portal_id!r} references missing local portal {destination_portal!r}."))
        if destination and project_root is not None and destination != document.asset_id and destination not in assets:
            issues.append(WorldIssue("warning", "portal_asset_missing", f"Portal {portal_id!r} references unexported asset {destination!r}."))

    if len(world["portals"]) > int(world["max_portals"]):
        issues.append(WorldIssue("error", "portal_limit", "The authored portal count exceeds the guarded runtime limit."))

    placements = [item for item in authoring.get("placements", []) if isinstance(item, dict) and bool(item.get("enabled", True))]
    if len(placements) > int(world["max_placements"]):
        issues.append(WorldIssue("warning", "placement_limit", f"Only the first {world['max_placements']} enabled placements will compile."))
    for placement in placements[: int(world["max_placements"])]:
        asset_id = str(placement.get("asset_id", ""))
        if not asset_id:
            issues.append(WorldIssue("warning", "placement_empty", "A placement has no referenced asset ID."))
        elif project_root is not None and asset_id != document.asset_id and asset_id not in assets:
            issues.append(WorldIssue("warning", "placement_missing", f"Placement references unexported asset {asset_id!r}."))

    if world["safe_room"]:
        hostile = [item for item in placements if str(item.get("kind", "")) in {"enemy", "boss", "mini_boss"}]
        if hostile:
            issues.append(WorldIssue("warning", "safe_room_hostile", "Safe Room contains hostile placements; they remain preserved but should be disabled or moved."))

    if world["theme_asset_id"] and project_root is not None and world["theme_asset_id"] not in assets:
        issues.append(WorldIssue("warning", "theme_missing", f"Theme asset {world['theme_asset_id']!r} is not exported."))
    if world["apply_theme"] and not authoring.get("theme", {}).get("slots") and not world["theme_asset_id"]:
        issues.append(WorldIssue("info", "theme_empty", "Theme application is enabled, but no local theme slots or theme asset reference are authored."))

    water_count = _semantic_point_count(document, ("water_surface", "water_volume"))
    flow_nodes = [item for item in authoring.get("flow", {}).get("nodes", []) if isinstance(item, dict)]
    if world["liquid_runtime"] and water_count == 0:
        issues.append(WorldIssue("warning", "liquid_points", "Liquid Runtime is enabled, but the asset contains no water-surface or water-volume semantic points."))
    if world["liquid_runtime"] and not flow_nodes:
        issues.append(WorldIssue("info", "liquid_flow", "Liquid Runtime has no authored flow nodes; only wave animation and tint will be available."))

    if not world["spawn_points"]:
        issues.append(WorldIssue("info", "spawn_point", "No authored spawn point exists; destination portals will use asset origin or destination-portal position."))

    if not issues:
        issues.append(WorldIssue("pass", "world_ready", "World Assembly passed guarded validation."))
    elif not any(issue.severity == "error" for issue in issues):
        issues.append(WorldIssue("pass", "world_compilable", "World Assembly is compilable under the guarded Phase 9 policy."))
    return issues


def _reference_summary(document: PCPDocument, project_root: Path | None) -> dict[str, Any]:
    assets = discover_exported_assets(project_root) if project_root is not None else {}
    world = ensure_world_assembly(document)
    authoring = ensure_authoring(document)
    referenced = {
        str(item.get("asset_id", ""))
        for item in authoring.get("placements", [])
        if isinstance(item, dict) and str(item.get("asset_id", ""))
    }
    referenced.update(
        str(item.get("destination_asset_id", ""))
        for item in world["portals"]
        if isinstance(item, dict) and str(item.get("destination_asset_id", ""))
    )
    if world["theme_asset_id"]:
        referenced.add(str(world["theme_asset_id"]))
    return {
        "known_asset_count": len(assets),
        "referenced_asset_ids": sorted(referenced),
        "resolved_asset_ids": sorted(asset_id for asset_id in referenced if asset_id == document.asset_id or asset_id in assets),
        "missing_asset_ids": sorted(asset_id for asset_id in referenced if asset_id != document.asset_id and asset_id not in assets),
    }


def compile_world_assembly(document: PCPDocument, project_root: Path | None = None) -> dict[str, Any]:
    world = ensure_world_assembly(document)
    authoring = ensure_authoring(document)
    lower, upper = document.bounds()
    portals = []
    for portal in world["portals"][: int(world["max_portals"])]:
        portals.append({
            "id": str(portal.get("id", "")),
            "kind": str(portal.get("kind", "door")),
            "position": _vec3(portal.get("position")),
            "size": _vec3(portal.get("size"), (1.2, 2.2, 0.4)),
            "destination_asset_id": str(portal.get("destination_asset_id", "")),
            "destination_portal_id": str(portal.get("destination_portal_id", "")),
            "arrival_offset": _vec3(portal.get("arrival_offset"), (0.0, 0.0, 1.4)),
            "arrival_yaw_degrees": _finite(portal.get("arrival_yaw_degrees")),
            "interaction_required": bool(portal.get("interaction_required", world["portal_interaction_required"])),
            "one_way": bool(portal.get("one_way", False)),
            "enabled": bool(portal.get("enabled", True)),
        })
    spawns = [
        {
            "id": str(item.get("id", "")),
            "role": str(item.get("role", "default")),
            "position": _vec3(item.get("position")),
            "yaw_degrees": _finite(item.get("yaw_degrees")),
            "enabled": bool(item.get("enabled", True)),
        }
        for item in world["spawn_points"][:MAX_SPAWNS]
        if isinstance(item, dict)
    ]
    placements = []
    for item in [p for p in authoring.get("placements", []) if isinstance(p, dict) and bool(p.get("enabled", True))][: int(world["max_placements"])]:
        placements.append({
            "asset_id": str(item.get("asset_id", "")),
            "kind": str(item.get("kind", "object")),
            "position": _vec3(item.get("position")),
            "rotation_degrees": _vec3(item.get("rotation")),
            "scale": _positive(item.get("scale"), 1.0, 0.001, 1000.0),
            "group": str(item.get("group", "")),
            "enabled": True,
        })
    flow_nodes = []
    for item in [n for n in authoring.get("flow", {}).get("nodes", []) if isinstance(n, dict)][:MAX_FLOW_NODES]:
        direction = _vec3(item.get("direction", item.get("vector")), (1.0, 0.0, 0.0))
        length = math.sqrt(sum(component * component for component in direction))
        if length <= 1.0e-8:
            direction = [1.0, 0.0, 0.0]
        else:
            direction = [component / length for component in direction]
        flow_nodes.append({
            "position": _vec3(item.get("position")),
            "direction": direction,
            "strength": _finite(item.get("strength"), 1.0),
            "viscosity": max(0.0, _finite(item.get("viscosity"), 1.0)),
        })
    theme_slots = [
        {
            "semantic": str(item.get("semantic", "generic")),
            "color": str(item.get("color", "#D9CC94")),
            "brush": str(item.get("brush", "")),
            "preset": str(item.get("preset", "")),
        }
        for item in [s for s in authoring.get("theme", {}).get("slots", []) if isinstance(s, dict)][:MAX_THEME_SLOTS]
    ]
    water_surface_count = _semantic_point_count(document, ("water_surface",))
    water_volume_count = _semantic_point_count(document, ("water_volume",))
    payload = {
        "schema": WORLD_SCHEMA,
        "asset_id": document.asset_id,
        "environment_type": document.environment_type,
        "enabled": bool(world["enabled"]),
        "targets": {"game": bool(world["game_enabled"]), "stress": bool(world["stress_enabled"])},
        "world": {
            "world_id": str(world["world_id"]),
            "room_id": str(world["room_id"]),
            "room_name": str(world["room_name"]),
            "host_zone": str(world["host_zone"]),
            "safe_room": bool(world["safe_room"]),
            "logical_level": int(world["logical_level"]),
            "bounds_min": list(lower),
            "bounds_max": list(upper),
            "reset_policy": str(world["reset_policy"]),
        },
        "portal_policy": {
            "execute": bool(world["execute_portals"]),
            "default_interaction_required": bool(world["portal_interaction_required"]),
            "cooldown": float(world["portal_cooldown"]),
            "show_debug": bool(world["show_portal_debug"]),
            "show_bounds_debug": bool(world["show_bounds_debug"]),
        },
        "portals": portals,
        "spawn_points": spawns,
        "placements": placements,
        "theme": {
            "apply": bool(world["apply_theme"]),
            "theme_asset_id": str(world["theme_asset_id"]),
            "slots": theme_slots,
        },
        "liquid": {
            "enabled": bool(world["liquid_runtime"]),
            "type": str(world["liquid_type"]),
            "color": str(world["liquid_color"]),
            "opacity": float(world["liquid_opacity"]),
            "wave_amplitude": float(world["wave_amplitude"]),
            "wave_frequency": float(world["wave_frequency"]),
            "flow_scale": float(world["flow_scale"]),
            "surface_points": water_surface_count,
            "volume_points": water_volume_count,
            "flow_nodes": flow_nodes,
        },
        "limits": {
            "max_portals": int(world["max_portals"]),
            "max_placements": int(world["max_placements"]),
            "max_liquid_points": int(world["max_liquid_points"]),
            "max_reference_depth": 1,
        },
        "references": _reference_summary(document, project_root),
        "support": {
            "room_bundle": "game_and_stress_rendering",
            "one_level_asset_placements": "bounded_existing_factory_loader",
            "semantic_theme": "game_and_stress",
            "portal_handoff": "game_interaction_guarded",
            "portal_debug": "game_scanner_and_stress",
            "liquid_wave_and_tint": "game_and_stress_visual",
            "liquid_physics_force": "deferred",
            "collision_mesh_generation": "deferred",
            "dynamic_navigation_rebuild": "deferred",
            "deep_world_nesting": "blocked",
        },
        "policy": "guarded_world_assembly_one_level_no_arbitrary_code",
        "future_attributes": world.get("future_attributes", {}),
    }
    return payload


def _json_value(value: Any) -> str:
    return json.dumps({"value": value}, separators=(",", ":"), ensure_ascii=False)


def world_assembly_udata(payload: dict[str, Any]) -> str:
    world = payload["world"]
    portal_policy = payload["portal_policy"]
    liquid = payload["liquid"]
    lines = ["@udata 1", "", "[world]"]
    lines += [
        f"schema: {_json_value(payload['schema'])};",
        f"enabled: {_json_value(payload['enabled'])};",
        f"game_enabled: {_json_value(payload['targets']['game'])};",
        f"stress_enabled: {_json_value(payload['targets']['stress'])};",
        f"world_id: {_json_value(world['world_id'])};",
        f"room_id: {_json_value(world['room_id'])};",
        f"room_name: {_json_value(world['room_name'])};",
        f"host_zone: {_json_value(world['host_zone'])};",
        f"safe_room: {_json_value(world['safe_room'])};",
        f"logical_level: {_json_value(world['logical_level'])};",
        f"bounds_min: {_json_value(world['bounds_min'])};",
        f"bounds_max: {_json_value(world['bounds_max'])};",
        f"reset_policy: {_json_value(world['reset_policy'])};",
        f"execute_portals: {_json_value(portal_policy['execute'])};",
        f"portal_interaction_required: {_json_value(portal_policy['default_interaction_required'])};",
        f"portal_cooldown: {_json_value(portal_policy['cooldown'])};",
        f"show_portal_debug: {_json_value(portal_policy['show_debug'])};",
        f"show_bounds_debug: {_json_value(portal_policy['show_bounds_debug'])};",
        f"max_portals: {_json_value(payload['limits']['max_portals'])};",
        f"max_placements: {_json_value(payload['limits']['max_placements'])};",
        f"max_liquid_points: {_json_value(payload['limits']['max_liquid_points'])};",
        "",
        "[liquid]",
        f"enabled: {_json_value(liquid['enabled'])};",
        f"type: {_json_value(liquid['type'])};",
        f"color: {_json_value(liquid['color'])};",
        f"opacity: {_json_value(liquid['opacity'])};",
        f"wave_amplitude: {_json_value(liquid['wave_amplitude'])};",
        f"wave_frequency: {_json_value(liquid['wave_frequency'])};",
        f"flow_scale: {_json_value(liquid['flow_scale'])};",
        f"surface_points: {_json_value(liquid['surface_points'])};",
        f"volume_points: {_json_value(liquid['volume_points'])};",
        "",
        "[theme]",
        f"apply: {_json_value(payload['theme']['apply'])};",
        f"theme_asset_id: {_json_value(payload['theme']['theme_asset_id'])};",
        "",
    ]
    for index, portal in enumerate(payload["portals"]):
        lines += [
            f"[portal.{index}]",
            f"id: {_json_value(portal['id'])};",
            f"kind: {_json_value(portal['kind'])};",
            f"position: {_json_value(portal['position'])};",
            f"size: {_json_value(portal['size'])};",
            f"destination_asset_id: {_json_value(portal['destination_asset_id'])};",
            f"destination_portal_id: {_json_value(portal['destination_portal_id'])};",
            f"arrival_offset: {_json_value(portal['arrival_offset'])};",
            f"arrival_yaw_degrees: {_json_value(portal['arrival_yaw_degrees'])};",
            f"interaction_required: {_json_value(portal['interaction_required'])};",
            f"one_way: {_json_value(portal['one_way'])};",
            f"enabled: {_json_value(portal['enabled'])};",
            "",
        ]
    for index, spawn in enumerate(payload["spawn_points"]):
        lines += [
            f"[spawn.{index}]",
            f"id: {_json_value(spawn['id'])};",
            f"role: {_json_value(spawn['role'])};",
            f"position: {_json_value(spawn['position'])};",
            f"yaw_degrees: {_json_value(spawn['yaw_degrees'])};",
            f"enabled: {_json_value(spawn['enabled'])};",
            "",
        ]
    for index, placement in enumerate(payload["placements"]):
        lines += [
            f"[world_placement.{index}]",
            f"asset_id: {_json_value(placement['asset_id'])};",
            f"kind: {_json_value(placement['kind'])};",
            f"position: {_json_value(placement['position'])};",
            f"rotation: {_json_value(placement['rotation_degrees'])};",
            f"scale: {_json_value(placement['scale'])};",
            f"group: {_json_value(placement['group'])};",
            f"enabled: {_json_value(placement['enabled'])};",
            "",
        ]
    for index, slot in enumerate(payload["theme"]["slots"]):
        lines += [
            f"[world_theme.{index}]",
            f"semantic: {_json_value(slot['semantic'])};",
            f"color: {_json_value(slot['color'])};",
            f"brush: {_json_value(slot['brush'])};",
            f"preset: {_json_value(slot['preset'])};",
            "",
        ]
    for index, node in enumerate(payload["liquid"]["flow_nodes"]):
        lines += [
            f"[world_flow.{index}]",
            f"position: {_json_value(node['position'])};",
            f"direction: {_json_value(node['direction'])};",
            f"strength: {_json_value(node['strength'])};",
            f"viscosity: {_json_value(node['viscosity'])};",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def write_world_assembly_files(asset_dir: Path, document: PCPDocument, project_root: Path | None = None) -> dict[str, Path]:
    payload = compile_world_assembly(document, project_root)
    name = slugify(document.asset_id)
    json_path = asset_dir / f"{name}.pcp3world.json"
    udata_path = asset_dir / f"{name}.pcp3world.udata"
    atomic_write_text(json_path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    atomic_write_text(udata_path, world_assembly_udata(payload))
    return {"json": json_path, "udata": udata_path}


def write_world_reference_report(path: Path, document: PCPDocument, project_root: Path) -> Path:
    payload = compile_world_assembly(document, project_root)
    report = {
        "schema": "pcp3_world_reference_audit_v1",
        "asset_id": document.asset_id,
        "room_id": payload["world"]["room_id"],
        "host_zone": payload["world"]["host_zone"],
        "references": payload["references"],
        "portal_count": len(payload["portals"]),
        "placement_count": len(payload["placements"]),
        "theme_slot_count": len(payload["theme"]["slots"]),
        "flow_node_count": len(payload["liquid"]["flow_nodes"]),
        "policy": payload["policy"],
    }
    atomic_write_text(path, json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return path
