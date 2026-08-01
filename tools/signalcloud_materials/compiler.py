#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_JMAP = "signalcloud_jitter_map_v1"
SCHEMA_TEXGRAPH = "signalcloud_texture_graph_v1"
LAYER_ORDER = ("HD Light", "HD Texture", "Outer Light", "Outer Texture", "Inner Texture")
LAYER_DEFAULTS = {
    "HD Light": 0.21,
    "HD Texture": 0.28,
    "Outer Light": 0.34,
    "Outer Texture": 0.47,
    "Inner Texture": 0.57,
}
LAYERS = set(LAYER_ORDER) | {"Normal"}
CHARACTERS = {"smooth", "bumpy", "rocky"}
SURFACES = {"floor", "wall", "ceiling"}
BLENDS = {"linear_mix", "multiply", "screen", "exact"}
PATTERN_MODES = {"legacy", "fiber_rows", "wallpaper_breakup", "flat_tiles"}


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(lo, min(hi, number))


def _u32(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def _vec3(value: Any, default: tuple[float, float, float]) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        return list(default)
    return [_clamp(item, 0.0, 1.0, default[i]) for i, item in enumerate(value)]


def _safe_resolve(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    root = root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"path escapes project root: {relative}")
    return candidate


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _q(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class MaterialCompileResult:
    output: Path
    material_count: int
    assignment_count: int
    selected_budget: int
    warning_count: int
    signature: str


def compile_material_runtime(project_root: Path, graph_relative: str = "content/core/materials/reception_tape_surfaces.texgraph",
                             output_relative: str = "user_data/studio/material_runtime.udata") -> MaterialCompileResult:
    root = Path(project_root).resolve()
    requested_graph = graph_relative
    managed_graph = root / "content/user/materials/reception_tape_surfaces.texgraph"
    if graph_relative == "content/core/materials/reception_tape_surfaces.texgraph" and managed_graph.is_file():
        graph_relative = managed_graph.relative_to(root).as_posix()
    graph_path = _safe_resolve(root, graph_relative)
    graph = _json(graph_path)
    if graph.get("schema") != SCHEMA_TEXGRAPH:
        raise ValueError(f"unsupported texture graph schema: {graph.get('schema')!r}")
    graph_mode = str(graph.get("mode", "auto")).lower()
    if graph_mode not in {"auto", "guided", "author"}:
        graph_mode = "auto"
    refs = graph.get("materials", [])
    if not isinstance(refs, list) or not refs:
        raise ValueError("texture graph must declare material files")

    warnings: list[str] = []
    materials: list[dict[str, Any]] = []
    id_to_index: dict[str, int] = {}
    for ref in refs[:32]:
        path = _safe_resolve(root, str(ref))
        doc = _json(path)
        if doc.get("schema") != SCHEMA_JMAP:
            raise ValueError(f"unsupported jitter-map schema in {ref}")
        asset_id = str(doc.get("asset_id", "")).strip()
        if not asset_id or asset_id in id_to_index:
            raise ValueError(f"invalid or duplicate material asset_id: {asset_id!r}")
        jitter = doc.get("jitter", {}) if isinstance(doc.get("jitter"), dict) else {}
        opacity = doc.get("opacity", {}) if isinstance(doc.get("opacity"), dict) else {}
        palette = doc.get("palette", {}) if isinstance(doc.get("palette"), dict) else {}
        runtime = doc.get("runtime", {}) if isinstance(doc.get("runtime"), dict) else {}
        pattern = doc.get("pattern", {}) if isinstance(doc.get("pattern"), dict) else {}
        layers = doc.get("definition_layers", []) if isinstance(doc.get("definition_layers"), list) else []
        layer_name = "HD Texture"
        layer_values = {name: 0.0 for name in LAYER_ORDER}
        seen_layers: set[str] = set()
        for raw_layer in layers[:8]:
            if not isinstance(raw_layer, dict):
                warnings.append(f"{asset_id}: non-object definition layer skipped")
                continue
            name = str(raw_layer.get("name", "HD Texture"))
            if name == "Normal":
                continue
            if name not in LAYERS:
                warnings.append(f"{asset_id}: unknown definition layer skipped")
                continue
            if name in seen_layers:
                warnings.append(f"{asset_id}: duplicate definition layer merged")
            seen_layers.add(name)
            layer_values[name] = _clamp(raw_layer.get("opacity"), 0.0, 1.0, LAYER_DEFAULTS[name])
        if seen_layers:
            layer_name = next(name for name in LAYER_ORDER if name in seen_layers)
        else:
            layer_values["HD Texture"] = LAYER_DEFAULTS["HD Texture"]
        layer_opacity = max(layer_values.values())
        character = str(doc.get("character", "bumpy")).lower()
        if character not in CHARACTERS:
            warnings.append(f"{asset_id}: unknown character defaulted")
            character = "bumpy"
        blend = str(palette.get("blend", "linear_mix")).lower()
        if blend not in BLENDS:
            warnings.append(f"{asset_id}: unknown blend defaulted")
            blend = "linear_mix"
        pattern_mode = str(pattern.get("mode", "legacy")).lower()
        if pattern_mode not in PATTERN_MODES:
            warnings.append(f"{asset_id}: unknown pattern mode defaulted")
            pattern_mode = "legacy"
        components = {
            key: _clamp(opacity.get(key), 0.0, 1.0, 1.0)
            for key in ("point", "cluster", "object", "surface", "local_area", "room", "global", "runtime_effect")
        }
        effective_opacity = layer_opacity
        for value in components.values():
            effective_opacity *= value
        material = {
            "id": asset_id,
            "name": str(doc.get("name", asset_id))[:96],
            "source": str(path.relative_to(root)),
            "character": character,
            "definition_layer": layer_name,
            "definition_layers": [layer_values[name] for name in LAYER_ORDER],
            "definition_layer_count": sum(value > 0.0 for value in layer_values.values()),
            "jG": _clamp(jitter.get("jG"), 0.001, 4.0, 0.05),
            "jL": _clamp(jitter.get("jL"), 0.0, 2.0, 0.02),
            "jC": _clamp(jitter.get("jC"), 0.01, 8.0, 0.3),
            "jS": _clamp(jitter.get("jS"), 0.02, 16.0, 0.8),
            "runtime_amplitude": _clamp(jitter.get("runtime_amplitude"), 0.0, 0.35, 0.04),
            "seed": _u32(jitter.get("seed"), 0, 0xFFFFFFFF, 1),
            "source_color": _vec3(palette.get("source"), (0.48, 0.42, 0.31)),
            "accent_color": _vec3(palette.get("accent"), (0.68, 0.58, 0.40)),
            "detail_color": _vec3(palette.get("detail"), (0.24, 0.20, 0.15)),
            "palette_id": str(palette.get("palette_id", asset_id))[:96],
            "blend": blend,
            "variation": _clamp(palette.get("variation"), 0.0, 0.35, 0.06),
            "exact_match": bool(palette.get("exact_match", False)),
            "effective_opacity": max(0.02, min(1.0, effective_opacity)),
            "point_budget_cost": _u32(runtime.get("point_budget_cost"), 0, 4096, 256),
            "pattern_mode": pattern_mode,
            "primary_spacing": _clamp(pattern.get("primary_spacing"), 0.08, 12.0, 0.8),
            "secondary_spacing": _clamp(pattern.get("secondary_spacing"), 0.08, 12.0, 1.2),
            "breakup_scale": _clamp(pattern.get("breakup_scale"), 0.2, 24.0, 3.0),
            "breakup_strength": _clamp(pattern.get("breakup_strength"), 0.0, 1.0, 0.0),
            "displacement_weight": _clamp(pattern.get("displacement_weight"), 0.0, 1.0, 1.0),
            "color_weight": _clamp(pattern.get("color_weight"), 0.0, 1.0, 0.68),
            "line_width": _clamp(pattern.get("line_width"), 0.02, 0.48, 0.18),
            "opacity_components": components,
        }
        id_to_index[asset_id] = len(materials)
        materials.append(material)

    rules = graph.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("texture graph rules must be a list")
    normalized_rules: list[dict[str, Any]] = []
    for raw in rules[:64]:
        if not isinstance(raw, dict):
            warnings.append("non-object texture rule skipped")
            continue
        material_id = str(raw.get("material", ""))
        surface = str(raw.get("surface", "")).lower()
        if material_id not in id_to_index or surface not in SURFACES:
            warnings.append(f"invalid texture rule skipped: {raw.get('id', '<unnamed>')}")
            continue
        normalized_rules.append({
            "id": str(raw.get("id", f"rule-{len(normalized_rules)}"))[:96],
            "zone": str(raw.get("zone", "*"))[:128],
            "surface": surface,
            "material_index": id_to_index[material_id],
            "priority": _u32(raw.get("priority"), 0, 10000, 100),
            "seed": _u32(raw.get("seed"), 0, 0xFFFFFFFF, 1),
            "locked": bool(raw.get("locked", False)),
            "opacity": _clamp(raw.get("opacity"), 0.0, 1.0, 1.0),
            "tags": [str(item)[:48] for item in raw.get("tags", [])[:12]] if isinstance(raw.get("tags"), list) else [],
        })
    normalized_rules.sort(key=lambda r: (not r["locked"], -r["priority"], r["id"]))

    budget = graph.get("runtime_budget", {}) if isinstance(graph.get("runtime_budget"), dict) else {}
    max_active = _u32(budget.get("max_active_materials"), 1, 8, 3)
    max_points = _u32(budget.get("max_point_budget"), 64, 8192, 1536)
    selected_indices: list[int] = []
    selected_budget = 0
    for rule in normalized_rules:
        idx = rule["material_index"]
        if idx in selected_indices:
            continue
        cost = materials[idx]["point_budget_cost"]
        if len(selected_indices) >= max_active or selected_budget + cost > max_points:
            continue
        selected_indices.append(idx)
        selected_budget += cost
    for index, material in enumerate(materials):
        material["budget_active"] = index in selected_indices

    signature_source = json.dumps({"graph": graph, "materials": materials, "rules": normalized_rules}, sort_keys=True, separators=(",", ":"))
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()[:16]
    out = _safe_resolve(root, output_relative)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["@udata 1", "", "[meta]",
             f"schema: {_q('signalcloud_material_runtime_v1')};",
             f"source_graph: {_q(str(graph_path.relative_to(root)))};",
             f"graph_id: {_q(str(graph.get('asset_id', 'core.texture_graph.reception_tape')))};",
             f"mode: {_q(graph_mode)};",
             f"material_count: {len(materials)};",
             f"assignment_count: {len(normalized_rules)};",
             f"warning_count: {len(warnings)};",
             f"signature: {_q(signature)};", "", "[budget]",
             f"max_active_materials: {max_active};",
             f"max_point_budget: {max_points};",
             f"selected_materials: {len(selected_indices)};",
             f"selected_point_budget: {selected_budget};"]
    for index, material in enumerate(materials):
        lines += ["", f"[material.{index}]",
                  f"id: {_q(material['id'])};", f"name: {_q(material['name'])};",
                  f"source: {_q(material['source'])};", f"character: {_q(material['character'])};",
                  f"definition_layer: {_q(material['definition_layer'])};",
                  f"definition_layer_count: {material['definition_layer_count']};",
                  f"definition_hd_light: {material['definition_layers'][0]:.6f};",
                  f"definition_hd_texture: {material['definition_layers'][1]:.6f};",
                  f"definition_outer_light: {material['definition_layers'][2]:.6f};",
                  f"definition_outer_texture: {material['definition_layers'][3]:.6f};",
                  f"definition_inner_texture: {material['definition_layers'][4]:.6f};",
                  f"jG: {material['jG']:.6f};", f"jL: {material['jL']:.6f};",
                  f"jC: {material['jC']:.6f};", f"jS: {material['jS']:.6f};",
                  f"runtime_amplitude: {material['runtime_amplitude']:.6f};",
                  f"seed: {material['seed']};", f"source_color: {_j(material['source_color'])};",
                  f"accent_color: {_j(material['accent_color'])};", f"detail_color: {_j(material['detail_color'])};",
                  f"palette_id: {_q(material['palette_id'])};", f"blend: {_q(material['blend'])};",
                  f"variation: {material['variation']:.6f};", f"exact_match: {_j(material['exact_match'])};",
                  f"effective_opacity: {material['effective_opacity']:.6f};",
                  f"opacity_components: {_j(material['opacity_components'])};",
                  f"point_budget_cost: {material['point_budget_cost']};",
                  f"pattern_mode: {_q(material['pattern_mode'])};",
                  f"primary_spacing: {material['primary_spacing']:.6f};",
                  f"secondary_spacing: {material['secondary_spacing']:.6f};",
                  f"breakup_scale: {material['breakup_scale']:.6f};",
                  f"breakup_strength: {material['breakup_strength']:.6f};",
                  f"displacement_weight: {material['displacement_weight']:.6f};",
                  f"color_weight: {material['color_weight']:.6f};",
                  f"line_width: {material['line_width']:.6f};",
                  f"budget_active: {_j(material['budget_active'])};"]
    for index, rule in enumerate(normalized_rules):
        lines += ["", f"[assignment.{index}]", f"id: {_q(rule['id'])};",
                  f"zone: {_q(rule['zone'])};", f"surface: {_q(rule['surface'])};",
                  f"material_index: {rule['material_index']};", f"priority: {rule['priority']};",
                  f"seed: {rule['seed']};", f"locked: {_j(rule['locked'])};",
                  f"opacity: {rule['opacity']:.6f};", f"tags: {_j(rule['tags'])};"]
    lines += ["", "[warnings]", f"items: {_j(warnings)};", ""]
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(out)
    return MaterialCompileResult(out, len(materials), len(normalized_rules), selected_budget, len(warnings), signature)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile SignalCloud .jmap/.texgraph content into a bounded native runtime sidecar.")
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--graph", default="content/core/materials/reception_tape_surfaces.texgraph")
    parser.add_argument("--output", default="user_data/studio/material_runtime.udata")
    args = parser.parse_args()
    result = compile_material_runtime(Path(args.project_root), args.graph, args.output)
    print(f"Material runtime: {result.material_count} materials | {result.assignment_count} assignments | budget {result.selected_budget} | warnings {result.warning_count} | sig {result.signature}")
    print(result.output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
