from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
import json
import math
import time

from .io import atomic_write_text
from .model import ENVIRONMENT_LABELS, MODE_DEFAULTS, PCPDocument, SEMANTIC_FLAGS

VALIDATION_SCHEMA = "pcp3_validation_v1"


@dataclass(frozen=True)
class LayerTemplate:
    name: str
    group: str
    semantic: str
    required: bool = False
    description: str = ""


@dataclass(frozen=True)
class ModeProfile:
    key: str
    label: str
    purpose: str
    recommended_semantics: tuple[str, ...]
    layers: tuple[LayerTemplate, ...]
    required_metadata: tuple[str, ...] = ()
    recommended_metadata: tuple[str, ...] = ()
    future_systems: tuple[str, ...] = ()


@dataclass
class ValidationIssue:
    severity: str
    code: str
    message: str
    hint: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


PROFILES: dict[str, ModeProfile] = {
    "enemy": ModeProfile(
        "enemy", "Enemy", "Formed or formless hostile point entity.",
        ("enemy_body", "bone", "trigger", "light", "generic"),
        (
            LayerTemplate("Body", "Entity", "enemy_body", True, "Primary visible hostile form."),
            LayerTemplate("Bone Guides", "Rig", "bone", False, "Future skeletal and deformation anchors."),
            LayerTemplate("Attack Anchors", "Gameplay", "trigger", False, "Attack origins, cones, and effect anchors."),
            LayerTemplate("Signal Effects", "Effects", "light", False, "Glow, trails, and alert-state points."),
        ),
        ("representation",), ("movement_profile", "attack_profile", "perception_profile"),
        ("bone_graph", "animation_timeline", "behavior_graph", "attack_patterns"),
    ),
    "boss": ModeProfile(
        "boss", "Boss", "Very large multi-phase hostile point entity.",
        ("enemy_body", "bone", "trigger", "light", "generic"),
        (
            LayerTemplate("Core Body", "Entity", "enemy_body", True, "Persistent boss core."),
            LayerTemplate("Phase 1", "Phases", "enemy_body", True, "Initial visible phase."),
            LayerTemplate("Phase 2", "Phases", "enemy_body", False, "Second-phase additions or replacement points."),
            LayerTemplate("Bone Guides", "Rig", "bone", False, "Future large-scale rig anchors."),
            LayerTemplate("Attack Anchors", "Gameplay", "trigger", True, "Major attack and hazard origins."),
            LayerTemplate("Arena Effects", "Effects", "light", False, "Phase lighting and environmental effects."),
        ),
        ("representation", "phase_count"), ("movement_profile", "attack_profile", "arena_profile"),
        ("phase_graph", "bone_graph", "animation_timeline", "raid_hooks"),
    ),
    "mini_boss": ModeProfile(
        "mini_boss", "Mini-Boss", "Large elite hostile between normal enemies and bosses.",
        ("enemy_body", "bone", "trigger", "light", "generic"),
        (
            LayerTemplate("Body", "Entity", "enemy_body", True),
            LayerTemplate("Armor / Elite Form", "Entity", "enemy_body", False),
            LayerTemplate("Bone Guides", "Rig", "bone", False),
            LayerTemplate("Attack Anchors", "Gameplay", "trigger", True),
            LayerTemplate("Signal Effects", "Effects", "light", False),
        ),
        ("representation",), ("movement_profile", "attack_profile"),
        ("bone_graph", "animation_timeline", "behavior_graph"),
    ),
    "raid": ModeProfile(
        "raid", "Raid", "XX-large encounter layout that places pre-made bosses and mini-bosses.",
        ("floor", "wall", "portal", "trigger", "light", "generic"),
        (
            LayerTemplate("Arena Floor", "Arena", "floor", True),
            LayerTemplate("Arena Boundary", "Arena", "wall", True),
            LayerTemplate("Player Entry", "Gameplay", "portal", True),
            LayerTemplate("Boss Slots", "Gameplay", "trigger", True),
            LayerTemplate("Wave Triggers", "Gameplay", "trigger", False),
            LayerTemplate("Arena Lighting", "Effects", "light", False),
        ),
        ("encounter_id",), ("boss_asset_ids", "wave_count"),
        ("encounter_graph", "wave_timeline", "reward_table", "network_raid_rules"),
    ),
    "friendly": ModeProfile(
        "friendly", "User Friendly", "Friendly NPC or player-adjacent humanoid point entity.",
        ("friendly_body", "bone", "trigger", "light", "generic"),
        (
            LayerTemplate("Body", "Entity", "friendly_body", True),
            LayerTemplate("Bone Guides", "Rig", "bone", False),
            LayerTemplate("Outfit / Accessories", "Entity", "friendly_body", False),
            LayerTemplate("Interaction Anchor", "Gameplay", "trigger", True),
            LayerTemplate("Friendly Effects", "Effects", "light", False),
        ),
        ("character_role",), ("dialogue_profile", "movement_profile", "interaction_profile"),
        ("bone_graph", "animation_timeline", "dialogue_graph", "schedule_graph"),
    ),
    "environment_object": ModeProfile(
        "environment_object", "Environment Object", "Weapon, pickup, usable, light, prop, proof, or miscellaneous object.",
        ("generic", "weapon", "pickup", "light", "trigger"),
        (
            LayerTemplate("Geometry", "Object", "generic", True),
            LayerTemplate("Collision Guide", "Gameplay", "wall", False),
            LayerTemplate("Interaction Anchor", "Gameplay", "trigger", False),
            LayerTemplate("Light / Effect", "Effects", "light", False),
        ),
        ("object_class",), ("interaction_profile", "collision_profile"),
        ("usable_actions", "pickup_rules", "damage_profile", "light_profile"),
    ),
    "environment_theme": ModeProfile(
        "environment_theme", "Environment Theme", "Reusable room-part visual and semantic theme set.",
        ("wall", "floor", "ceiling", "portal", "light", "generic"),
        (
            LayerTemplate("Walls", "Architecture", "wall", True),
            LayerTemplate("Floors", "Architecture", "floor", True),
            LayerTemplate("Ceilings", "Architecture", "ceiling", True),
            LayerTemplate("Doors / Windows", "Architecture", "portal", False),
            LayerTemplate("Lights", "Lighting", "light", False),
            LayerTemplate("Theme Props", "Props", "generic", False),
        ),
        ("theme_id",), ("palette", "default_light_profile"),
        ("material_rules", "procedural_variants", "room_part_library"),
    ),
    "room": ModeProfile(
        "room", "Room", "Complete room shell with portals, lighting, objects, and triggers.",
        ("wall", "floor", "ceiling", "portal", "light", "trigger", "generic", "water_surface", "water_volume"),
        (
            LayerTemplate("Walls", "Architecture", "wall", True),
            LayerTemplate("Floor", "Architecture", "floor", True),
            LayerTemplate("Ceiling", "Architecture", "ceiling", True),
            LayerTemplate("Portals", "Connectivity", "portal", True),
            LayerTemplate("Lights", "Lighting", "light", False),
            LayerTemplate("Objects", "Contents", "generic", False),
            LayerTemplate("Triggers", "Gameplay", "trigger", False),
            LayerTemplate("Water Surface", "Liquid", "water_surface", False),
            LayerTemplate("Water Volume", "Liquid", "water_volume", False),
        ),
        ("room_id",), ("theme_asset_id", "safe_room", "logical_level"),
        ("portal_graph", "trigger_graph", "object_placements", "spawn_rules", "scanner_rules"),
    ),
    "liquid": ModeProfile(
        "liquid", "Liquid Maker", "Liquid surface, volume, flow, thickness, and interaction definition.",
        ("water_surface", "water_volume", "liquid_flow", "trigger", "light", "generic"),
        (
            LayerTemplate("Surface", "Liquid", "water_surface", True),
            LayerTemplate("Volume", "Liquid", "water_volume", True),
            LayerTemplate("Flow Guides", "Simulation", "liquid_flow", False),
            LayerTemplate("Boundary", "Simulation", "wall", False),
            LayerTemplate("Interaction Triggers", "Gameplay", "trigger", False),
            LayerTemplate("Liquid Effects", "Effects", "light", False),
        ),
        ("liquid_type",), ("viscosity", "flow_speed", "density", "damage_profile"),
        ("flow_field", "turbulence_field", "surface_response", "submerged_shader_profile"),
    ),
}


def profile_for(environment_type: str) -> ModeProfile:
    return PROFILES.get(environment_type, PROFILES["environment_object"])


def point_budget(document: PCPDocument) -> int:
    return int(document.metadata.get("recommended_point_budget", MODE_DEFAULTS[document.environment_type]["point_budget"]))


def layer_matches(document: PCPDocument, template: LayerTemplate) -> bool:
    target_name = template.name.strip().casefold()
    return any(layer.name.strip().casefold() == target_name for layer in document.layers)


def missing_layers(document: PCPDocument, *, required_only: bool = False) -> list[LayerTemplate]:
    profile = profile_for(document.environment_type)
    return [
        template for template in profile.layers
        if (not required_only or template.required) and not layer_matches(document, template)
    ]


def apply_mode_template(document: PCPDocument, *, include_optional: bool = True) -> list[int]:
    profile = profile_for(document.environment_type)
    created: list[int] = []
    reusable = None
    if len(document.layers) == 1 and document.layers[0].name == "Base Points" and not any(True for _ in document.layer_points(document.layers[0].id)):
        reusable = document.layers[0]
    for template in profile.layers:
        if not include_optional and not template.required:
            continue
        if layer_matches(document, template):
            continue
        if reusable is not None:
            layer = reusable
            reusable = None
            layer.name = template.name
            layer.semantic = template.semantic
        else:
            layer = document.add_layer(template.name, template.semantic)
        layer.group = template.group
        layer.future_attributes["pcp3_mode_template"] = True
        layer.future_attributes["required"] = template.required
        layer.future_attributes["description"] = template.description
        created.append(layer.id)
    document.metadata["mode_profile"] = profile.key
    document.metadata["mode_profile_version"] = 1
    document.metadata.setdefault("future_mode_data", {})
    document.dirty = True
    return created


def _metadata_value(document: PCPDocument, key: str) -> Any:
    if key in document.metadata:
        return document.metadata[key]
    return document.settings.future_attributes.get(key)


def validate_document(document: PCPDocument) -> list[ValidationIssue]:
    profile = profile_for(document.environment_type)
    issues: list[ValidationIssue] = []
    if not document.asset_id.strip() or document.asset_id == "untitled_asset":
        issues.append(ValidationIssue("warning", "asset_id", "Asset ID is still untitled.", "Set a unique database-safe asset ID before export."))
    if not document.display_name.strip() or document.display_name == "Untitled Asset":
        issues.append(ValidationIssue("warning", "display_name", "Display name is still untitled."))
    if not document.author.creator_name.strip():
        issues.append(ValidationIssue("warning", "creator_name", "Creator name is empty.", "Fill the Certificate tab for mod-community provenance."))
    if not document.points:
        issues.append(ValidationIssue("warning", "empty_cloud", "The asset contains no point geometry."))
    nonfinite = 0
    invalid_radius = 0
    for point in document.points:
        values = (point.x, point.y, point.z, point.radius, point.r, point.g, point.b, point.a, point.density)
        if not all(math.isfinite(value) for value in values):
            nonfinite += 1
        if point.radius <= 0.0 or not math.isfinite(point.radius):
            invalid_radius += 1
    if nonfinite:
        issues.append(ValidationIssue("error", "nonfinite_points", f"{nonfinite:,} point records contain non-finite values.", "Repair or erase these records before runtime use."))
    if invalid_radius:
        issues.append(ValidationIssue("error", "invalid_radius", f"{invalid_radius:,} point records have an invalid radius."))

    budget = point_budget(document)
    count = len(document.points)
    if count > budget:
        issues.append(ValidationIssue("warning", "point_budget", f"Point count {count:,} exceeds the {profile.label} recommendation of {budget:,}.", "The asset remains valid, but runtime LOD/streaming may be required."))
    elif count > int(budget * 0.85):
        issues.append(ValidationIssue("info", "point_budget_near", f"Point count is {count / max(1, budget):.0%} of the recommended budget."))

    for template in missing_layers(document, required_only=True):
        issues.append(ValidationIssue("warning", "missing_required_layer", f"Recommended required layer is missing: {template.name}.", f"Use Apply Mode Template to add the {template.semantic} layer."))

    semantics = {layer.semantic for layer in document.layers}
    point_semantics = {name for name, flag in SEMANTIC_FLAGS.items() if any(point.flags == flag for point in document.points)}
    combined = semantics | point_semantics
    if document.points and not any(semantic in combined for semantic in profile.recommended_semantics):
        issues.append(ValidationIssue("warning", "semantic_profile", f"No points or layers use the recommended {profile.label} semantics."))

    for key in profile.required_metadata:
        value = _metadata_value(document, key)
        if value in (None, "", [], {}):
            issues.append(ValidationIssue("info", "missing_mode_metadata", f"Mode metadata is not set: {key}.", "The field is preserved for future engine support and does not block current export."))

    preview_position = document.runtime.get("preview_position")
    if not isinstance(preview_position, list) or len(preview_position) != 3:
        issues.append(ValidationIssue("error", "preview_position", "Runtime preview position must contain three coordinates."))
    else:
        try:
            if not all(math.isfinite(float(value)) for value in preview_position):
                raise ValueError
        except (TypeError, ValueError):
            issues.append(ValidationIssue("error", "preview_position", "Runtime preview position contains an invalid coordinate."))
    try:
        scale = float(document.runtime.get("preview_scale", 1.0))
        if not math.isfinite(scale) or scale <= 0.0:
            raise ValueError
    except (TypeError, ValueError):
        issues.append(ValidationIssue("error", "preview_scale", "Runtime preview scale must be a positive finite number."))

    if not issues:
        issues.append(ValidationIssue("pass", "ready", "No current mode-profile issues were found."))
    return issues


def validation_counts(issues: Iterable[ValidationIssue]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0, "pass": 0}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts


def validation_report(document: PCPDocument, issues: list[ValidationIssue] | None = None) -> dict[str, Any]:
    issues = issues if issues is not None else validate_document(document)
    profile = profile_for(document.environment_type)
    return {
        "schema": VALIDATION_SCHEMA,
        "generated_epoch": int(time.time()),
        "project_id": document.project_id,
        "asset_id": document.asset_id,
        "display_name": document.display_name,
        "environment_type": document.environment_type,
        "environment_label": ENVIRONMENT_LABELS.get(document.environment_type, document.environment_type),
        "profile_purpose": profile.purpose,
        "point_count": len(document.points),
        "recommended_point_budget": point_budget(document),
        "layer_count": len(document.layers),
        "counts": validation_counts(issues),
        "issues": [issue.to_dict() for issue in issues],
        "future_systems_preserved": list(profile.future_systems),
        "policy": "forgiving_export_preserve_unknown",
    }


def write_validation_report(path: Path, document: PCPDocument, issues: list[ValidationIssue] | None = None) -> Path:
    report = validation_report(document, issues)
    atomic_write_text(path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    return path
