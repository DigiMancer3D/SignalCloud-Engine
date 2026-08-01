from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import TupdRecipe, TupdResult, TupdResultInstance

KNOWN_KEYS = {
    "schema", "schema_major", "schema_minor", "recipe_revision", "recipe_id", "label", "mode",
    "base_item_id", "inputs", "consumed_inputs", "required_interfaces", "optional_interfaces",
    "connections", "forced_connections", "validation_rules", "test_actions", "cost_xar",
    "repair_percent", "stability_penalty", "weight_penalty", "malfunction_policy",
    "result_id", "result_kind", "result_name", "result_interfaces", "result_sockets", "result_tags",
    "point_budget", "preview_shape", "preview_color", "receipt_policy",
}


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def recipe_from_dict(data: dict[str, Any]) -> TupdRecipe:
    recipe = TupdRecipe(
        schema=str(data.get("schema", "signalcloud.tupd-recipe")),
        schema_major=int(data.get("schema_major", 1)),
        schema_minor=int(data.get("schema_minor", 1)),
        recipe_revision=int(data.get("recipe_revision", 1)),
        recipe_id=str(data.get("recipe_id", "starter.tupd-draft")),
        label=str(data.get("label", "Tupd Draft")),
        mode=str(data.get("mode", "modification")),
        base_item_id=str(data.get("base_item_id", "weapon.service-pistol")),
        inputs=_strings(data.get("inputs")),
        consumed_inputs=_strings(data.get("consumed_inputs")),
        required_interfaces=_strings(data.get("required_interfaces")),
        optional_interfaces=_strings(data.get("optional_interfaces")),
        connections=_strings(data.get("connections")),
        forced_connections=_strings(data.get("forced_connections")),
        validation_rules=_strings(data.get("validation_rules")),
        test_actions=_strings(data.get("test_actions")) or ["inspect", "handle", "primary", "collision"],
        cost_xar=int(data.get("cost_xar", 0)),
        repair_percent=float(data.get("repair_percent", 0.0)),
        stability_penalty=float(data.get("stability_penalty", 0.0)),
        weight_penalty=float(data.get("weight_penalty", 0.0)),
        malfunction_policy=str(data.get("malfunction_policy", "none")),
        result=TupdResult(
            result_id=str(data.get("result_id", "tupd.result")),
            result_kind=str(data.get("result_kind", "object")),
            display_name=str(data.get("result_name", data.get("result_id", "Tupd Result"))),
            interfaces=_strings(data.get("result_interfaces")),
            sockets=_strings(data.get("result_sockets")),
            tags=_strings(data.get("result_tags")),
            point_budget=int(data.get("point_budget", 1200)),
        ),
        preview_shape=str(data.get("preview_shape", "assembly")),
        preview_color=str(data.get("preview_color", "#45d8ef")),
        receipt_policy=str(data.get("receipt_policy", "deterministic")),
        extensions={key: value for key, value in data.items() if key not in KNOWN_KEYS},
    )
    recipe.normalize()
    return recipe


def recipe_to_dict(recipe: TupdRecipe) -> dict[str, Any]:
    recipe.normalize()
    data: dict[str, Any] = {
        "schema": recipe.schema,
        "schema_major": recipe.schema_major,
        "schema_minor": recipe.schema_minor,
        "recipe_revision": recipe.recipe_revision,
        "recipe_id": recipe.recipe_id,
        "label": recipe.label,
        "mode": recipe.mode,
        "base_item_id": recipe.base_item_id,
        "inputs": recipe.inputs,
        "consumed_inputs": recipe.consumed_inputs,
        "required_interfaces": recipe.required_interfaces,
        "optional_interfaces": recipe.optional_interfaces,
        "connections": recipe.connections,
        "forced_connections": recipe.forced_connections,
        "validation_rules": recipe.validation_rules,
        "test_actions": recipe.test_actions,
        "cost_xar": recipe.cost_xar,
        "repair_percent": recipe.repair_percent,
        "stability_penalty": recipe.stability_penalty,
        "weight_penalty": recipe.weight_penalty,
        "malfunction_policy": recipe.malfunction_policy,
        "result_id": recipe.result.result_id,
        "result_kind": recipe.result.result_kind,
        "result_name": recipe.result.display_name,
        "result_interfaces": recipe.result.interfaces,
        "result_sockets": recipe.result.sockets,
        "result_tags": recipe.result.tags,
        "point_budget": recipe.result.point_budget,
        "preview_shape": recipe.preview_shape,
        "preview_color": recipe.preview_color,
        "receipt_policy": recipe.receipt_policy,
    }
    data.update(recipe.extensions)
    return data


def load_recipe(path: Path) -> TupdRecipe:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Tupd recipe must be a JSON object")
    if data.get("schema", "signalcloud.tupd-recipe") != "signalcloud.tupd-recipe":
        raise ValueError(f"Unsupported Tupd schema: {data.get('schema')}")
    return recipe_from_dict(data)


def save_recipe_atomic(path: Path, recipe: TupdRecipe) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(recipe_to_dict(recipe), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    load_recipe(temporary)
    temporary.replace(path)
    return path


def instance_from_dict(data: dict[str, Any]) -> TupdResultInstance:
    instance = TupdResultInstance(
        schema=str(data.get("schema", "signalcloud.tupd-instance")),
        schema_major=int(data.get("schema_major", 1)),
        schema_minor=int(data.get("schema_minor", 0)),
        instance_id=str(data.get("instance_id", "")),
        recipe_id=str(data.get("recipe_id", "")),
        recipe_revision=int(data.get("recipe_revision", 1)),
        result_id=str(data.get("result_id", "")),
        result_kind=str(data.get("result_kind", "object")),
        display_name=str(data.get("display_name", "")),
        base_item_id=str(data.get("base_item_id", "")),
        condition=float(data.get("condition", 0.0)),
        weight=float(data.get("weight", 0.0)),
        stability_percent=float(data.get("stability_percent", 100.0)),
        point_budget=int(data.get("point_budget", 1200)),
        interfaces=_strings(data.get("interfaces")),
        sockets=_strings(data.get("sockets")),
        tags=_strings(data.get("tags")),
        applied_parts=_strings(data.get("applied_parts")),
        connections=_strings(data.get("connections")),
        forced_connections=_strings(data.get("forced_connections")),
        test_actions=_strings(data.get("test_actions")),
        malfunction_policy=str(data.get("malfunction_policy", "none")),
        equipped=bool(data.get("equipped", False)),
        spawned=bool(data.get("spawned", False)),
        broken=bool(data.get("broken", False)),
        test_count=int(data.get("test_count", 0)),
        last_action=str(data.get("last_action", "")),
        last_outcome=str(data.get("last_outcome", "")),
        signature=str(data.get("signature", "")),
    )
    if instance.schema != "signalcloud.tupd-instance":
        raise ValueError(f"Unsupported Tupd instance schema: {instance.schema}")
    instance.normalize()
    if not instance.instance_id or not instance.recipe_id or not instance.result_id:
        raise ValueError("Tupd instance requires instance_id, recipe_id, and result_id")
    return instance


def instance_to_dict(instance: TupdResultInstance) -> dict[str, Any]:
    instance.normalize()
    return {
        "schema": instance.schema,
        "schema_major": instance.schema_major,
        "schema_minor": instance.schema_minor,
        "instance_id": instance.instance_id,
        "recipe_id": instance.recipe_id,
        "recipe_revision": instance.recipe_revision,
        "result_id": instance.result_id,
        "result_kind": instance.result_kind,
        "display_name": instance.display_name,
        "base_item_id": instance.base_item_id,
        "condition": instance.condition,
        "weight": instance.weight,
        "stability_percent": instance.stability_percent,
        "point_budget": instance.point_budget,
        "interfaces": instance.interfaces,
        "sockets": instance.sockets,
        "tags": instance.tags,
        "applied_parts": instance.applied_parts,
        "connections": instance.connections,
        "forced_connections": instance.forced_connections,
        "test_actions": instance.test_actions,
        "malfunction_policy": instance.malfunction_policy,
        "equipped": instance.equipped,
        "spawned": instance.spawned,
        "broken": instance.broken,
        "test_count": instance.test_count,
        "last_action": instance.last_action,
        "last_outcome": instance.last_outcome,
        "signature": instance.signature,
    }


def load_result_instance(path: Path) -> TupdResultInstance:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Tupd instance must be a JSON object")
    return instance_from_dict(data)


def save_result_instance_atomic(path: Path, instance: TupdResultInstance) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(instance_to_dict(instance), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    load_result_instance(temporary)
    temporary.replace(path)
    return path
