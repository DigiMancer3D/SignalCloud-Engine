#!/usr/bin/env python3
"""Managed user material copies for Reception Tape authoring."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.asset_doctor.content_abi import write_asset_envelope

CORE_DIR = Path("content/core/materials")
USER_DIR = Path("content/user/materials/reception_tape")
CORE_GRAPH = CORE_DIR / "reception_tape_surfaces.texgraph"
USER_GRAPH = Path("content/user/materials/reception_tape_surfaces.texgraph")
LICENSE_ID = "LicenseRef-SignalCloud-User-Authored"
SURFACE_FILES = {
    "floor": "office_carpet.jmap",
    "wall": "office_wallpaper.jmap",
    "ceiling": "ceiling_tile.jmap",
}
ID_MAP = {
    "core.material.office_carpet": "user.material.reception_tape.office_carpet",
    "core.material.office_wallpaper": "user.material.reception_tape.office_wallpaper",
    "core.material.ceiling_tile": "user.material.reception_tape.ceiling_tile",
}


@dataclass(frozen=True, slots=True)
class ManagedMaterialSet:
    graph: Path
    files: dict[str, Path]
    created: bool


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def ensure_managed_material_set(project_root: Path) -> ManagedMaterialSet:
    root = Path(project_root).resolve()
    content = root / "content"
    created = False
    files: dict[str, Path] = {}
    for surface, filename in SURFACE_FILES.items():
        source = root / CORE_DIR / filename
        destination = root / USER_DIR / filename
        files[surface] = destination
        if not destination.exists():
            payload = json.loads(source.read_text(encoding="utf-8"))
            payload["asset_id"] = ID_MAP[str(payload.get("asset_id", ""))]
            payload["name"] = f"User {payload.get('name', filename)}"
            payload.setdefault("extensions", {})["managed_from"] = source.relative_to(root).as_posix()
            _atomic_json(destination, payload)
            created = True
        payload = json.loads(destination.read_text(encoding="utf-8"))
        write_asset_envelope(
            content,
            destination,
            asset_id=str(payload["asset_id"]),
            asset_type="jitter_map",
            family="materials",
            pack="user",
            license_id=LICENSE_ID,
            hot_reload="authoring-only",
        )

    graph_path = root / USER_GRAPH
    if not graph_path.exists():
        graph = json.loads((root / CORE_GRAPH).read_text(encoding="utf-8"))
        graph["asset_id"] = "user.texture_graph.reception_tape"
        graph["name"] = "User Reception Tape Surface Assignment"
        graph["materials"] = [(USER_DIR / filename).as_posix() for filename in SURFACE_FILES.values()]
        for rule in graph.get("rules", []):
            material = str(rule.get("material", ""))
            if material in ID_MAP:
                rule["material"] = ID_MAP[material]
            rule["id"] = "user-" + str(rule.get("id", "rule"))
        graph.setdefault("extensions", {})["managed_from"] = CORE_GRAPH.as_posix()
        _atomic_json(graph_path, graph)
        created = True
    graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
    write_asset_envelope(
        content,
        graph_path,
        asset_id=str(graph_payload["asset_id"]),
        asset_type="texture_graph",
        family="materials",
        pack="user",
        license_id=LICENSE_ID,
        hot_reload="authoring-only",
    )
    return ManagedMaterialSet(graph=graph_path, files=files, created=created)


def load_surface_pattern(project_root: Path, surface: str) -> tuple[Path, dict[str, Any]]:
    managed = ensure_managed_material_set(project_root)
    if surface not in managed.files:
        raise ValueError(f"unsupported surface: {surface}")
    path = managed.files[surface]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return path, dict(payload.get("pattern", {}))


def save_surface_pattern(project_root: Path, surface: str, pattern: dict[str, Any]) -> Path:
    root = Path(project_root).resolve()
    managed = ensure_managed_material_set(root)
    if surface not in managed.files:
        raise ValueError(f"unsupported surface: {surface}")
    path = managed.files[surface]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["pattern"] = dict(pattern)
    _atomic_json(path, payload)
    write_asset_envelope(
        root / "content",
        path,
        asset_id=str(payload["asset_id"]),
        asset_type="jitter_map",
        family="materials",
        pack="user",
        license_id=LICENSE_ID,
        hot_reload="authoring-only",
    )
    return path


def load_surface_definition_layers(project_root: Path, surface: str) -> tuple[Path, list[dict[str, Any]]]:
    managed = ensure_managed_material_set(project_root)
    if surface not in managed.files:
        raise ValueError(f"unsupported surface: {surface}")
    path = managed.files[surface]
    payload = json.loads(path.read_text(encoding="utf-8"))
    layers = payload.get("definition_layers", [])
    return path, [dict(item) for item in layers if isinstance(item, dict)]


def save_surface_definition_layers(project_root: Path, surface: str,
                                   layers: list[dict[str, Any]]) -> Path:
    root = Path(project_root).resolve()
    managed = ensure_managed_material_set(root)
    if surface not in managed.files:
        raise ValueError(f"unsupported surface: {surface}")
    path = managed.files[surface]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["definition_layers"] = [dict(item) for item in layers[:5]]
    _atomic_json(path, payload)
    write_asset_envelope(
        root / "content", path,
        asset_id=str(payload["asset_id"]), asset_type="jitter_map",
        family="materials", pack="user", license_id=LICENSE_ID,
        hot_reload="authoring-only",
    )
    return path
