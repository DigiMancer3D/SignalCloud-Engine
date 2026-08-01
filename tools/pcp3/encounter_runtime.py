from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.pcp3.advanced_authoring import ensure_authoring
from tools.pcp3.io import atomic_write_text, slugify
from tools.pcp3.model import PCPDocument
from tools.pcp3.world_assembly import discover_exported_assets, ensure_world_assembly

ENCOUNTER_SCHEMA = "pcp3_encounter_runtime_v1"
SUPPORTED_TYPES = {"room", "raid", "boss", "mini_boss", "friendly", "enemy"}
START_CONDITIONS = ("world_enter", "proximity", "scanner", "interaction", "timer", "manual")
COMPLETION_POLICIES = ("all_waves_cleared", "timer", "manual")
RESET_POLICIES = ("zone_exit", "session", "manual")
REWARD_POLICIES = ("telemetry_only", "proof_hook", "xar_hook", "scrap_hook", "combined_hook")
MAX_WAVES = 16
MAX_ACTIVE_ENTITIES = 32
MAX_TOTAL_SPAWNS = 128
MAX_FRIENDLIES = 16
MAX_BOSS_PHASES = 8


@dataclass(frozen=True)
class EncounterIssue:
    severity: str
    code: str
    message: str
    hint: str = ""

    def to_json(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "message": self.message, "hint": self.hint}


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return number if math.isfinite(number) else float(default)


def _positive(value: Any, default: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, _finite(value, default)))


def _integer(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _vec3(value: Any, default: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return [float(default[0]), float(default[1]), float(default[2])]
    return [_finite(value[i], default[i]) for i in range(3)]


def _defaults(document: PCPDocument) -> dict[str, Any]:
    world = ensure_world_assembly(document)
    return {
        "schema": ENCOUNTER_SCHEMA,
        "enabled": False,
        "game_enabled": False,
        "stress_enabled": True,
        "encounter_id": slugify(document.asset_id or "encounter"),
        "host_zone": str(world.get("host_zone") or document.runtime.get("preview_zone", "Reception Tape")),
        "start_condition": "world_enter",
        "start_position": [0.0, 0.0, 0.0],
        "start_radius": 8.0,
        "start_delay": 0.0,
        "completion_policy": "all_waves_cleared",
        "completion_seconds": 30.0,
        "completion_delay": 1.0,
        "inter_wave_delay": 1.3,
        "entity_lifetime": 8.0,
        "reset_policy": "zone_exit",
        "reward_policy": "telemetry_only",
        "reward_proofs": 0,
        "reward_xar": 0,
        "reward_scrap": 0,
        "show_debug": True,
        "console_events": True,
        "max_waves": MAX_WAVES,
        "max_active_entities": 16,
        "max_total_spawns": 64,
        "max_friendlies": 8,
        "max_boss_phases": 4,
        "wave_overrides": {},
        "boss_phases": [],
        "future_attributes": {},
    }


def ensure_encounter_runtime(document: PCPDocument) -> dict[str, Any]:
    value = document.metadata.get("encounter_runtime")
    if not isinstance(value, dict):
        value = _defaults(document)
        document.metadata["encounter_runtime"] = value
    defaults = _defaults(document)
    for key, default in defaults.items():
        value.setdefault(key, default)
    value["schema"] = ENCOUNTER_SCHEMA
    value["encounter_id"] = slugify(str(value.get("encounter_id") or document.asset_id or "encounter"))
    value["host_zone"] = str(value.get("host_zone") or document.runtime.get("preview_zone", "Reception Tape"))
    if value.get("start_condition") not in START_CONDITIONS:
        value["start_condition"] = "world_enter"
    if value.get("completion_policy") not in COMPLETION_POLICIES:
        value["completion_policy"] = "all_waves_cleared"
    if value.get("reset_policy") not in RESET_POLICIES:
        value["reset_policy"] = "zone_exit"
    if value.get("reward_policy") not in REWARD_POLICIES:
        value["reward_policy"] = "telemetry_only"
    value["start_position"] = _vec3(value.get("start_position"))
    value["start_radius"] = _positive(value.get("start_radius"), 8.0, 0.1, 500.0)
    value["start_delay"] = _positive(value.get("start_delay"), 0.0, 0.0, 600.0)
    value["completion_seconds"] = _positive(value.get("completion_seconds"), 30.0, 0.1, 3600.0)
    value["completion_delay"] = _positive(value.get("completion_delay"), 1.0, 0.0, 60.0)
    value["inter_wave_delay"] = _positive(value.get("inter_wave_delay"), 1.3, 0.0, 60.0)
    value["entity_lifetime"] = _positive(value.get("entity_lifetime"), 8.0, 0.25, 600.0)
    value["reward_proofs"] = _integer(value.get("reward_proofs"), 0, 0, 999)
    value["reward_xar"] = _integer(value.get("reward_xar"), 0, 0, 99999)
    value["reward_scrap"] = _integer(value.get("reward_scrap"), 0, 0, 9999)
    value["max_waves"] = _integer(value.get("max_waves"), MAX_WAVES, 1, MAX_WAVES)
    value["max_active_entities"] = _integer(value.get("max_active_entities"), 16, 1, MAX_ACTIVE_ENTITIES)
    value["max_total_spawns"] = _integer(value.get("max_total_spawns"), 64, 1, MAX_TOTAL_SPAWNS)
    value["max_friendlies"] = _integer(value.get("max_friendlies"), 8, 0, MAX_FRIENDLIES)
    value["max_boss_phases"] = _integer(value.get("max_boss_phases"), 4, 0, MAX_BOSS_PHASES)
    if not isinstance(value.get("wave_overrides"), dict):
        value["wave_overrides"] = {}
    if not isinstance(value.get("boss_phases"), list):
        value["boss_phases"] = []
    if not isinstance(value.get("future_attributes"), dict):
        value["future_attributes"] = {}
    cleaned: list[dict[str, Any]] = []
    for index, raw in enumerate(value["boss_phases"][: value["max_boss_phases"]]):
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        record["id"] = slugify(str(record.get("id") or f"phase_{index + 1}"))
        record["name"] = str(record.get("name") or f"Phase {index + 1}")
        record["progress_threshold"] = max(0.0, min(1.0, _finite(record.get("progress_threshold"), index / max(1, value["max_boss_phases"]))))
        record["clip"] = str(record.get("clip") or "Default")
        record["movement_profile"] = str(record.get("movement_profile") or "stationary")
        record["theme_target"] = str(record.get("theme_target") or "")
        record["effect_anchor"] = str(record.get("effect_anchor") or "")
        record["future_attributes"] = record.get("future_attributes") if isinstance(record.get("future_attributes"), dict) else {}
        cleaned.append(record)
    cleaned.sort(key=lambda item: float(item["progress_threshold"]))
    value["boss_phases"] = cleaned
    return value


def add_boss_phase(document: PCPDocument, name: str, progress_threshold: float, clip: str = "Default", movement_profile: str = "stationary", theme_target: str = "", effect_anchor: str = "") -> dict[str, Any]:
    settings = ensure_encounter_runtime(document)
    if len(settings["boss_phases"]) >= settings["max_boss_phases"]:
        raise ValueError("The guarded boss-phase limit has been reached.")
    record = {
        "id": slugify(name or f"phase_{len(settings['boss_phases']) + 1}"),
        "name": name.strip() or f"Phase {len(settings['boss_phases']) + 1}",
        "progress_threshold": max(0.0, min(1.0, float(progress_threshold))),
        "clip": clip.strip() or "Default",
        "movement_profile": movement_profile.strip() or "stationary",
        "theme_target": theme_target.strip(),
        "effect_anchor": effect_anchor.strip(),
        "future_attributes": {},
    }
    settings["boss_phases"].append(record)
    settings["boss_phases"].sort(key=lambda item: float(item.get("progress_threshold", 0.0)))
    document.dirty = True
    return record


def _compiled_waves(document: PCPDocument, settings: dict[str, Any]) -> list[dict[str, Any]]:
    authoring = ensure_authoring(document)
    result: list[dict[str, Any]] = []
    total = 0
    for ordinal, raw in enumerate(authoring.get("raid", {}).get("waves", [])[: settings["max_waves"]]):
        if not isinstance(raw, dict):
            continue
        wave_id = slugify(str(raw.get("id") or f"wave_{ordinal + 1}"))
        overrides = settings["wave_overrides"].get(wave_id, {})
        if not isinstance(overrides, dict):
            overrides = {}
        asset_ids = [slugify(str(value)) for value in raw.get("asset_ids", []) if str(value).strip()]
        count = _integer(raw.get("count"), 1, 1, settings["max_total_spawns"])
        count = min(count, settings["max_total_spawns"] - total)
        if count <= 0:
            break
        total += count
        result.append({
            "id": wave_id,
            "index": _integer(raw.get("index"), ordinal + 1, 0, 999),
            "asset_ids": asset_ids,
            "count": count,
            "delay": _positive(raw.get("delay"), 0.0, 0.0, 600.0),
            "active_seconds": _positive(overrides.get("active_seconds"), settings["entity_lifetime"], 0.25, 600.0),
            "spawn_role": str(overrides.get("spawn_role") or "encounter"),
            "spread_radius": _positive(overrides.get("spread_radius"), 3.0, 0.0, 100.0),
            "completion_policy": str(overrides.get("completion_policy") or "lifetime"),
            "future_attributes": raw.get("future_attributes", {}),
        })
    result.sort(key=lambda item: (int(item["index"]), item["id"]))
    return result


def _friendly_placements(document: PCPDocument, settings: dict[str, Any]) -> list[dict[str, Any]]:
    authoring = ensure_authoring(document)
    output: list[dict[str, Any]] = []
    for raw in authoring.get("placements", []):
        if not isinstance(raw, dict) or not raw.get("enabled", True):
            continue
        kind = str(raw.get("kind", "")).casefold()
        if kind not in {"friendly", "user_friendly", "ally", "helper"}:
            continue
        output.append({
            "id": slugify(str(raw.get("id") or f"friendly_{len(output) + 1}")),
            "asset_id": slugify(str(raw.get("asset_id") or "")),
            "position": _vec3(raw.get("position")),
            "rotation_degrees": _vec3(raw.get("rotation_degrees")),
            "scale": _positive(raw.get("scale"), 1.0, 0.001, 1000.0),
            "group": str(raw.get("group") or "friendlies"),
            "enabled": True,
        })
        if len(output) >= settings["max_friendlies"]:
            break
    return output


def validate_encounter_runtime(document: PCPDocument, project_root: Path | None = None) -> list[EncounterIssue]:
    settings = ensure_encounter_runtime(document)
    issues: list[EncounterIssue] = []
    waves = _compiled_waves(document, settings)
    if settings["enabled"] and document.environment_type not in SUPPORTED_TYPES:
        issues.append(EncounterIssue("error", "unsupported_type", f"{document.environment_type} is not an active encounter host type."))
    if settings["enabled"] and not (settings["game_enabled"] or settings["stress_enabled"]):
        issues.append(EncounterIssue("warning", "no_target", "Encounter Runtime is enabled without a Game or Stress target."))
    if settings["enabled"] and not waves:
        issues.append(EncounterIssue("warning", "no_waves", "No raid waves are authored. Friendlies and boss-phase evidence can still compile."))
    known = discover_exported_assets(project_root) if project_root is not None else {}
    for wave in waves:
        if not wave["asset_ids"]:
            issues.append(EncounterIssue("warning", "wave_no_assets", f"Wave {wave['id']} has no entity assets."))
        for asset_id in wave["asset_ids"]:
            if project_root is not None and asset_id not in known:
                issues.append(EncounterIssue("warning", "wave_asset_missing", f"Wave {wave['id']} references missing asset {asset_id}."))
    for placement in _friendly_placements(document, settings):
        if not placement["asset_id"]:
            issues.append(EncounterIssue("warning", "friendly_no_asset", f"Friendly placement {placement['id']} has no asset ID."))
        elif project_root is not None and placement["asset_id"] not in known:
            issues.append(EncounterIssue("warning", "friendly_asset_missing", f"Friendly placement {placement['id']} references missing asset {placement['asset_id']}."))
    if settings["reward_policy"] != "telemetry_only" and not any((settings["reward_proofs"], settings["reward_xar"], settings["reward_scrap"])):
        issues.append(EncounterIssue("warning", "empty_reward", "A guarded reward hook is selected but all reward quantities are zero."))
    if settings["enabled"]:
        issues.append(EncounterIssue("info", "encounter_compilable", "Encounter data is bounded and compilable. Rewards remain telemetry-only hooks until game approval."))
    return issues


def compile_encounter_runtime(document: PCPDocument, project_root: Path | None = None) -> dict[str, Any]:
    settings = ensure_encounter_runtime(document)
    waves = _compiled_waves(document, settings)
    friendlies = _friendly_placements(document, settings)
    issues = validate_encounter_runtime(document, project_root)
    enabled = bool(settings["enabled"] and document.environment_type in SUPPORTED_TYPES)
    return {
        "schema": ENCOUNTER_SCHEMA,
        "asset_id": document.asset_id,
        "environment_type": document.environment_type,
        "enabled": enabled,
        "targets": {"game": bool(settings["game_enabled"]), "stress": bool(settings["stress_enabled"])},
        "encounter": {
            "id": settings["encounter_id"],
            "host_zone": settings["host_zone"],
            "start_condition": settings["start_condition"],
            "start_position": settings["start_position"],
            "start_radius": settings["start_radius"],
            "start_delay": settings["start_delay"],
            "completion_policy": settings["completion_policy"],
            "completion_seconds": settings["completion_seconds"],
            "completion_delay": settings["completion_delay"],
            "inter_wave_delay": settings["inter_wave_delay"],
            "entity_lifetime": settings["entity_lifetime"],
            "reset_policy": settings["reset_policy"],
        },
        "waves": waves,
        "boss_phases": list(settings["boss_phases"]),
        "friendlies": friendlies,
        "reward": {
            "policy": settings["reward_policy"],
            "proofs": settings["reward_proofs"],
            "xar": settings["reward_xar"],
            "scrap": settings["reward_scrap"],
            "execution": "telemetry_hook_no_save_mutation",
        },
        "debug": {"show": bool(settings["show_debug"]), "console_events": bool(settings["console_events"])},
        "limits": {
            "max_waves": settings["max_waves"],
            "max_active_entities": settings["max_active_entities"],
            "max_total_spawns": settings["max_total_spawns"],
            "max_friendlies": settings["max_friendlies"],
            "max_boss_phases": settings["max_boss_phases"],
            "max_reference_depth": 1,
        },
        "support": {
            "waves": "bounded_lifetime_scheduler",
            "boss_phases": "progress_visual_state_and_telemetry",
            "friendlies": "persistent_guarded_reference_placements",
            "completion": "wave_or_timer_state_machine",
            "rewards": "proof_xar_scrap_telemetry_hooks_only",
            "damage": "blocked",
            "save_mutation": "blocked",
            "unrestricted_ai": "blocked",
        },
        "issues": [issue.to_json() for issue in issues],
        "future_attributes": settings.get("future_attributes", {}),
        "policy": "guarded_encounter_scheduler_no_damage_economy_or_save_mutation",
    }


def _json_value(value: Any) -> str:
    return json.dumps({"value": value}, separators=(",", ":"), ensure_ascii=False)


def encounter_runtime_udata(payload: dict[str, Any]) -> str:
    encounter = payload["encounter"]
    reward = payload["reward"]
    limits = payload["limits"]
    debug = payload["debug"]
    lines = ["@udata 1", "", "[encounter]"]
    for key, value in (
        ("schema", payload["schema"]), ("enabled", payload["enabled"]),
        ("game_enabled", payload["targets"]["game"]), ("stress_enabled", payload["targets"]["stress"]),
        ("encounter_id", encounter["id"]), ("host_zone", encounter["host_zone"]),
        ("start_condition", encounter["start_condition"]), ("start_position", encounter["start_position"]),
        ("start_radius", encounter["start_radius"]), ("start_delay", encounter["start_delay"]),
        ("completion_policy", encounter["completion_policy"]), ("completion_seconds", encounter["completion_seconds"]),
        ("completion_delay", encounter["completion_delay"]), ("inter_wave_delay", encounter["inter_wave_delay"]),
        ("entity_lifetime", encounter["entity_lifetime"]), ("reset_policy", encounter["reset_policy"]),
        ("show_debug", debug["show"]), ("console_events", debug["console_events"]),
        ("max_waves", limits["max_waves"]), ("max_active_entities", limits["max_active_entities"]),
        ("max_total_spawns", limits["max_total_spawns"]), ("max_friendlies", limits["max_friendlies"]),
        ("max_boss_phases", limits["max_boss_phases"]),
    ):
        lines.append(f"{key}: {_json_value(value)};")
    lines += ["", "[reward]"]
    for key in ("policy", "proofs", "xar", "scrap", "execution"):
        lines.append(f"{key}: {_json_value(reward[key])};")
    lines.append("")
    for index, wave in enumerate(payload["waves"]):
        lines += [f"[wave.{index}]"]
        for key in ("id", "index", "asset_ids", "count", "delay", "active_seconds", "spawn_role", "spread_radius", "completion_policy"):
            lines.append(f"{key}: {_json_value(wave[key])};")
        lines.append("")
    for index, phase in enumerate(payload["boss_phases"]):
        lines += [f"[boss_phase.{index}]"]
        for key in ("id", "name", "progress_threshold", "clip", "movement_profile", "theme_target", "effect_anchor"):
            lines.append(f"{key}: {_json_value(phase.get(key, ''))};")
        lines.append("")
    for index, friendly in enumerate(payload["friendlies"]):
        lines += [f"[friendly.{index}]"]
        for key in ("id", "asset_id", "position", "rotation_degrees", "scale", "group", "enabled"):
            lines.append(f"{key}: {_json_value(friendly[key])};")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_encounter_runtime_files(asset_dir: Path, document: PCPDocument, project_root: Path | None = None) -> dict[str, Path]:
    payload = compile_encounter_runtime(document, project_root)
    name = slugify(document.asset_id)
    json_path = asset_dir / f"{name}.pcp3encounter.json"
    udata_path = asset_dir / f"{name}.pcp3encounter.udata"
    atomic_write_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(udata_path, encounter_runtime_udata(payload))
    return {"json": json_path, "udata": udata_path}


def simulate_encounter(payload: dict[str, Any], duration: float = 20.0, step: float = 0.25, *, scanner: bool = True, interaction: bool = True, viewer_distance: float = 0.0) -> list[dict[str, Any]]:
    """Deterministic authoring-side scheduler used by tests and the dry-run UI."""
    events: list[dict[str, Any]] = []
    if not payload.get("enabled"):
        return events
    encounter = payload["encounter"]
    condition = encounter["start_condition"]
    condition_ok = condition in {"world_enter", "timer"} or (condition == "scanner" and scanner) or (condition == "interaction" and interaction) or (condition == "proximity" and viewer_distance <= encounter["start_radius"])
    if not condition_ok or condition == "manual":
        return events
    start = encounter["start_delay"]
    events.append({"time": start, "kind": "encounter_started", "wave": -1})
    active_until: list[float] = []
    cursor = start
    total_spawned = 0
    for wave_index, wave in enumerate(payload["waves"]):
        cursor += float(wave["delay"])
        if wave_index > 0:
            cursor += float(encounter["inter_wave_delay"])
        events.append({"time": cursor, "kind": "wave_started", "wave": wave_index})
        count = min(int(wave["count"]), int(payload["limits"]["max_total_spawns"]) - total_spawned)
        for instance in range(max(0, count)):
            asset_ids = wave["asset_ids"] or [""]
            events.append({"time": cursor, "kind": "spawn", "wave": wave_index, "instance": instance, "asset_id": asset_ids[instance % len(asset_ids)]})
            active_until.append(cursor + float(wave["active_seconds"]))
            total_spawned += 1
        cursor = max([cursor, *active_until])
        active_until = [value for value in active_until if value > cursor]
        events.append({"time": cursor, "kind": "wave_cleared", "wave": wave_index})
    complete_time = cursor + float(encounter["completion_delay"])
    if encounter["completion_policy"] == "timer":
        complete_time = start + float(encounter["completion_seconds"])
    if encounter["completion_policy"] != "manual" and complete_time <= duration + step:
        events.append({"time": complete_time, "kind": "encounter_completed", "wave": len(payload["waves"]) - 1})
        events.append({"time": complete_time, "kind": "reward_hook", **payload["reward"]})
    return [event for event in events if float(event["time"]) <= duration + 1e-9]
